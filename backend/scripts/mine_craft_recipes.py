"""Manual craft-mining entry point; promotion always remains approval-gated."""

from __future__ import annotations

import argparse
import json

from backend.aios.miner import CraftMiner


def main() -> int:
    """Read generation/rating rows from JSON and print a draft."""
    parser = argparse.ArgumentParser(description="Distill craft-only recipe drafts")
    parser.add_argument("input", help="JSON file containing recent rated generation events")
    args = parser.parse_args()
    with open(args.input, encoding="utf-8") as handle:
        events = json.load(handle)
    draft = CraftMiner().mine(events)
    print(json.dumps(draft.to_dict() if draft else {"status": "no_eligible_draft"}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
