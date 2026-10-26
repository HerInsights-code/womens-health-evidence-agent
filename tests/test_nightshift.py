import pytest

from app.adapters import nightshift


@pytest.mark.parametrize(
    "raw, expected",
    [
        ("http://127.0.0.1:8088", "http://127.0.0.1:8088/v1"),
        ("http://127.0.0.1:8088/v1", "http://127.0.0.1:8088/v1"),
        ("http://127.0.0.1:8088/v1/", "http://127.0.0.1:8088/v1"),
        ("http://127.0.0.1:8088/v1/chat/completions", "http://127.0.0.1:8088/v1"),
        ("http://127.0.0.1:8088/v1/models", "http://127.0.0.1:8088/v1"),
        ("http://127.0.0.1:8088/healthz", "http://127.0.0.1:8088/v1"),
        ("127.0.0.1:8088", "http://127.0.0.1:8088/v1"),
        ("http://127.0.0.1:8088/v1/v1", "http://127.0.0.1:8088/v1"),
        ("http://127.0.0.1:8088/v1/v1/models", "http://127.0.0.1:8088/v1"),
        ("localhost:8088/v1", "http://localhost:8088/v1"),
    ],
)
def test_normalize_base_url(raw, expected):
    assert nightshift.normalize_base_url(raw) == expected


def test_placeholder_token_is_rejected(monkeypatch):
    monkeypatch.setenv("METERLESS_RUNTIME_TOKEN", "rt-local")
    monkeypatch.setenv("METERLESS_BASE_URL", "http://127.0.0.1:8088/v1")
    monkeypatch.setenv("METERLESS_MODEL", "meterless/auto")
    with pytest.raises(ValueError, match="rt-local"):
        nightshift.status()
    with pytest.raises(ValueError, match="rt-local"):
        nightshift.chat([{"role": "user", "content": "ready"}])


@pytest.mark.integration
def test_live_chat_returns_a_string():
    if nightshift.status() == "offline":
        pytest.skip("Nightshift is not running")
    reply, routed_model = nightshift.chat(
        [{"role": "user", "content": "Reply with the single word ready."}]
    )
    assert isinstance(reply, str)
    assert reply.strip()
    assert isinstance(routed_model, str)
    assert routed_model.strip()

def test_wrong_token_is_unauthorized_not_offline(monkeypatch):
    """Contract done-condition: a bad token must not look like a down service."""
    if nightshift.status() == "offline":
        pytest.skip("Nightshift is not running")
    monkeypatch.setenv("METERLESS_RUNTIME_TOKEN", "not-a-real-token-at-all")
    assert nightshift.status() == "unauthorized"