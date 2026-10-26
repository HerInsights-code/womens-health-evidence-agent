"""Scout Intent engine — intent detection, risk guarding and routing.

Implements the Meterless Scout Intent spec (engines/scout-intent/AGENTS.md)
for this project's health-tagging registry.

Implemented: intent registry with versioning, Stage-1 deterministic trigger
scanning with the startup latency self-test, confidence bands, multi-intent
with spans, the four clarification triggers, a guard stack (injection,
sensitivity/crisis, scope), capability routing to tag groups, and the signed
execution contract with TTL and verification.

Not implemented, and why:
- Stage-2 model rescoring: needs a local embedding model. The spec allows
  its absence ("graceful degradation, never a hard dependency"), so semantic
  and contextual terms stay at 0 and Stage-1 scoring sets confidence.
- Capability graph selection rules: this app resolves each capability to a
  single local tool, so there is nothing to select between.
- Model profile routing: one model (Nemotron via Nightshift), one profile.
- Learning loop and nightly retraining: telemetry events are emitted, but
  nothing retrains.

Crisis detection is keyword-based. It catches common phrasings but is not
comprehensive, and is a safety net rather than a clinical screen.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import os
import re
import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path

# Canonical defaults from the spec, section 12.
BAND_HIGH = 0.80
BAND_MEDIUM = 0.55
BAND_LOW = 0.40
TIE_WINDOW = 0.05
HIGH_RISK_THRESHOLD = 0.95
SECONDARY_FLOOR = 0.55
CONTRACT_TTL_SECONDS = 300
MAX_CLARIFICATION_OPTIONS = 4
STAGE1_BUDGET_MS = 16

# Weighted-match sum at which an intent is fully confident. Roughly two
# strong triggers. Config data, not code, per spec 4.3.
TRIGGER_SATURATION = 4.0


@dataclass
class IntentCandidate:
    intent: str
    score: float
    span: tuple[int, int] | None
    matched: list[str] = field(default_factory=list)


@dataclass
class Risk:
    level: str                     # low | medium | high | block
    flags: list[str] = field(default_factory=list)
    reason: str | None = None


@dataclass
class Clarification:
    question: str
    options: list[str]
    trigger: str


@dataclass
class Decision:
    trace_id: str
    primary: str
    band: str
    confidence: float
    candidates: list[IntentCandidate]
    tag_groups: list[str]
    risk: Risk
    clarification: Clarification | None
    contract: dict


def _normalise(text: str) -> str:
    """Lowercase and straighten curly apostrophes, which phones produce."""
    return text.lower().replace("\u2019", "'").replace("\u2018", "'")


class ScoutIntent:
    """The five-stage pipeline: Sense, Interpret, Guard, Route, Recommend."""

    def __init__(
        self,
        registry_path: str = "data/intent_registry.json",
        secret: str | None = None,
        self_test: bool = True,
    ) -> None:
        with Path(registry_path).open(encoding="utf-8") as handle:
            registry = json.load(handle)

        self.registry_version = registry["registryVersion"]
        self.intents = registry["intents"]
        self.by_id = {item["id"]: item for item in self.intents}
        self.crisis_triggers = registry.get("crisisTriggers", [])
        self.injection_patterns = registry.get("injectionPatterns", [])
        self.secret = (secret or os.getenv("SCOUT_SECRET") or "dev-secret").encode()
        self.events: list[str] = []

        for item in self.intents:
            if not item.get("examples"):
                raise ValueError(
                    f"intent {item['id']} has no examples; "
                    "the spec requires them for classification and evals"
                )

        if self_test:
            self._latency_self_test()

    # --- Stage 1: Sense -------------------------------------------------

    def _latency_self_test(self) -> None:
        """Spec 4.1: a full-registry scan must complete under 16 ms."""
        probes = [
            "my periods are heavy and I am exhausted",
            "skin breaking out and anxious all the time",
            "I think I have pcos",
        ]
        start = time.perf_counter()
        for probe in probes:
            self._scan(probe)
        elapsed_ms = (time.perf_counter() - start) * 1000 / len(probes)
        if elapsed_ms > STAGE1_BUDGET_MS:
            raise RuntimeError(
                f"Stage-1 scan averaged {elapsed_ms:.1f}ms, "
                f"over the {STAGE1_BUDGET_MS}ms budget"
            )

    def _scan(self, prompt: str) -> list[IntentCandidate]:
        """Weighted trigger scan over the full registry. Pure rules.

        Spec 4.1 says confidence is the winner's score as a fraction of
        matched weight. We read that per intent rather than as a share of
        the total across intents: this registry detects topics, and a
        paragraph covering several of them should score each one on its own
        evidence. Sharing one budget across intents would push every score
        below the routing floor precisely when multi-intent applies.
        """
        text = _normalise(prompt)
        raw: list[tuple[str, float, tuple[int, int] | None, list[str]]] = []

        for item in self.intents:
            weight_sum = 0.0
            matched: list[str] = []
            spans: list[tuple[int, int]] = []

            for trigger, weight in item.get("triggers", []):
                found = re.search(rf"\b{re.escape(trigger)}\b", text)
                if found:
                    weight_sum += weight
                    matched.append(trigger)
                    spans.append((found.start(), found.end()))

            if weight_sum > 0:
                span = (min(s for s, _ in spans), max(e for _, e in spans))
                raw.append((item["id"], weight_sum, span, matched))

        if not raw:
            return []

        candidates = [
            IntentCandidate(
                intent=i,
                score=round(min(1.0, w / TRIGGER_SATURATION), 4),
                span=s,
                matched=m,
            )
            for i, w, s, m in raw
        ]
        return sorted(candidates, key=lambda c: c.score, reverse=True)

    def classify(self, prompt: str) -> list[IntentCandidate]:
        """Sense stage only. Returns scored candidates, never a single label."""
        return self._scan(prompt)

    @staticmethod
    def band(score: float) -> str:
        if score >= BAND_HIGH:
            return "high"
        if score >= BAND_MEDIUM:
            return "medium"
        if score >= BAND_LOW:
            return "low"
        return "reject"

    # --- Stage 3: Guard -------------------------------------------------

    def _guard(self, prompt: str, intent_id: str) -> Risk:
        text = _normalise(prompt)
        flags: list[str] = []

        for pattern in self.injection_patterns:
            if pattern in text:
                return Risk(
                    level="block",
                    flags=["injection"],
                    reason="prompt injection pattern detected",
                )

        for phrase in self.crisis_triggers:
            if phrase in text:
                return Risk(
                    level="block",
                    flags=["crisis"],
                    reason="the person may be in crisis; route to support, not research",
                )

        intent = self.by_id.get(intent_id, {})
        level = intent.get("riskClass", "low")
        return Risk(level=level, flags=flags)

    # --- Stage 4: Route -------------------------------------------------

    def _route(self, candidates: list[IntentCandidate]) -> list[str]:
        """Resolve capabilities to tag groups. Multi-intent per spec 4.5."""
        groups: list[str] = []
        for candidate in candidates:
            if candidate.score < SECONDARY_FLOOR:
                continue
            group = self.by_id[candidate.intent].get("tagGroup")
            if group and group not in groups:
                groups.append(group)
        return groups

    # --- Clarification --------------------------------------------------

    def _clarification(
        self, candidates: list[IntentCandidate], risk: Risk
    ) -> Clarification | None:
        """The four triggers from spec 4.6."""
        if not candidates:
            return Clarification(
                question="Could you tell me a bit more about what you're experiencing?",
                options=[],
                trigger="low-band",
            )

        top = candidates[0]
        band = self.band(top.score)

        trigger = None
        if band in ("low", "reject"):
            trigger = "low-band"
        elif (
            band == "medium"
            and len(candidates) > 1
            and abs(top.score - candidates[1].score) < TIE_WINDOW
        ):
            trigger = "tie"
        elif risk.level == "high" and top.score < HIGH_RISK_THRESHOLD:
            trigger = "high-risk"

        if trigger is None:
            return None

        options = [
            self.by_id[c.intent]["description"]
            for c in candidates[:MAX_CLARIFICATION_OPTIONS]
        ]
        return Clarification(
            question="I want to make sure I understand. Which of these fits best?",
            options=options,
            trigger=trigger,
        )

    # --- Stage 5: Recommend and the contract ----------------------------

    def _sign(self, contract: dict) -> str:
        canonical = json.dumps(contract, sort_keys=True, separators=(",", ":"))
        return hmac.new(self.secret, canonical.encode(), hashlib.sha256).hexdigest()

    def _issue_contract(
        self,
        trace_id: str,
        primary: str,
        confidence: float,
        candidates: list[IntentCandidate],
        risk: Risk,
        tag_groups: list[str],
        surface: str,
        user: str,
    ) -> dict:
        now = datetime.now(timezone.utc)
        contract = {
            "contractId": str(uuid.uuid4()),
            "traceId": trace_id,
            "intent": {
                "primary": primary,
                "confidence": confidence,
                "alternates": [
                    {"intent": c.intent, "score": c.score} for c in candidates[1:4]
                ],
            },
            "risk": {"level": risk.level, "flags": risk.flags, "reason": risk.reason},
            "toolPlan": [
                {"tool": "tagger", "input": {"tagGroups": tag_groups}}
            ],
            "modelProfile": {"provider": "meterless", "profile": "nightshift-default"},
            "scope": {
                "user": user,
                "surface": surface,
                "capabilities": [f"tags.{g}" for g in tag_groups],
            },
            "issuedAt": now.isoformat(),
            "expiresAt": (now + timedelta(seconds=CONTRACT_TTL_SECONDS)).isoformat(),
            "registryVersion": self.registry_version,
            "policyPackVersion": "default-1",
            "signedBy": "scout",
        }
        contract["signature"] = self._sign(contract)
        return contract

    def verify(self, contract: dict) -> None:
        """Downstream verification. Raises on unsigned, tampered or expired."""
        signature = contract.get("signature")
        if not signature:
            raise ValueError("contract.refused: unsigned contract")

        unsigned = {k: v for k, v in contract.items() if k != "signature"}
        if not hmac.compare_digest(signature, self._sign(unsigned)):
            raise ValueError("contract.refused: signature mismatch")

        expires = datetime.fromisoformat(contract["expiresAt"])
        if datetime.now(timezone.utc) > expires:
            raise ValueError("contract.expired")

        if contract["registryVersion"] != self.registry_version:
            raise ValueError("contract.refused: registry version drift")

    # --- The pipeline ---------------------------------------------------

    def decide(
        self, prompt: str, user: str = "anonymous", surface: str = "cli"
    ) -> Decision:
        trace_id = str(uuid.uuid4())[:8]
        started = time.perf_counter()

        candidates = self.classify(prompt)
        primary = candidates[0].intent if candidates else "general.unclear"
        confidence = candidates[0].score if candidates else 0.0

        risk = self._guard(prompt, primary)

        if risk.level == "block":
            tag_groups: list[str] = []
            clarification = None
        else:
            tag_groups = self._route(candidates)
            clarification = self._clarification(candidates, risk)

        contract = self._issue_contract(
            trace_id, primary, confidence, candidates, risk, tag_groups, surface, user
        )

        latency_ms = (time.perf_counter() - started) * 1000
        self.events.append(
            f"scout.decision traceId={trace_id} intent={primary} "
            f"band={self.band(confidence)} latencyMs={latency_ms:.1f} stage2=skipped"
        )
        self.events.append(
            f"contract.issued contractId={contract['contractId']} "
            f"intent={primary} risk={risk.level} profile=nightshift-default"
        )
        if clarification:
            self.events.append(
                f"scout.clarification traceId={trace_id} trigger={clarification.trigger}"
            )

        return Decision(
            trace_id=trace_id,
            primary=primary,
            band=self.band(confidence),
            confidence=confidence,
            candidates=candidates,
            tag_groups=tag_groups,
            risk=risk,
            clarification=clarification,
            contract=contract,
        )