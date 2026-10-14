"""Finite, explicit candidate operations. Never spawns or calls a model service."""
import argparse
import asyncio
import json
from pathlib import Path
import sys

from .runtime import CheckpointPersistenceError, Journal, advance


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-dir", required=True, type=Path)
    parser.add_argument("--timeout", type=float, default=12)
    sub = parser.add_subparsers(dest="command", required=True)
    for name in ("init", "dispatched", "submit"):
        sub.add_parser(name).add_argument("--file", type=Path, required=True)
    sub.add_parser("advance")
    sub.add_parser("pending")
    sub.add_parser("status")
    sub.add_parser("readback").add_argument("--request-id", required=True)
    args = parser.parse_args(argv)
    if not 0 < args.timeout <= 30:
        parser.error("Timeout must be in (0, 30]")
    journal = None
    try:
        journal = Journal(args.run_dir)
        with journal.lock():
            if args.command == "init":
                registry = json.loads(Path(__file__).parents[1].joinpath("native_roles.json").read_text())
                journal.initialize(json.loads(args.file.read_text()), registry)
                result = {"status": "initialized", "activated_live": False}
            elif args.command == "advance":
                async def bounded():
                    return await asyncio.wait_for(advance(journal), args.timeout)
                result = asyncio.run(bounded())
            elif args.command in ("dispatched", "submit"):
                getattr(journal, args.command)(json.loads(args.file.read_text()))
                result = {"status": "receipt_recorded" if args.command == "dispatched" else "output_readback_recorded",
                          "provenance_authenticated": False}
            elif args.command == "pending":
                result = {"pending": journal.pending()}
            elif args.command == "readback":
                result = journal.readback(args.request_id)
            else:
                result = {"status": journal.get("status"), "final": journal.get("final"),
                          "pending_count": len(journal.pending()), "activated_live": False}
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0
    except (CheckpointPersistenceError, ValueError, OSError, TimeoutError) as error:
        print(json.dumps({"status": "blocked_or_failed", "error": str(error), "live_ai_proven": False}), file=sys.stderr)
        return 2
    finally:
        if journal is not None:
            journal.close()


if __name__ == "__main__":
    raise SystemExit(main())
