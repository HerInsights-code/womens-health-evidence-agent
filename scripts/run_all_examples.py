"""Run every input example through the full pipeline and save the outputs."""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from run import run

ROOT = Path(__file__).resolve().parent.parent
IN_DIR = ROOT / "input_examples"
OUT_DIR = ROOT / "output_examples"


def main() -> None:
    OUT_DIR.mkdir(exist_ok=True)
    files = sorted(IN_DIR.glob("*.json"))
    if not files:
        print(f"no input examples in {IN_DIR}")
        return

    for path in files:
        payload = json.loads(path.read_text(encoding="utf-8"))
        query = payload["input"]["query"]
        print(f"\n=== {path.name}")
        print(f"    {query[:90]}")

        try:
            result = run(query)
        except Exception as error:
            result = {
                "status": "error",
                "error": {"type": type(error).__name__, "message": str(error)[:200]},
            }

        result = {
            "run_id": payload.get("run_id", path.stem),
            "input": {"query": query},
            **result,
        }
        out_path = OUT_DIR / f"updated_output_from_{path.name}"
        out_path.write_text(json.dumps(result, indent=2), encoding="utf-8")

        status = result.get("status")
        if status == "success":
            print(f"    tags: {result['tags']}")
            print(f"    matched {len(result['matches'])} articles")
        else:
            print(f"    status: {status}")
        print(f"    -> {out_path.name}")


if __name__ == "__main__":
    main()