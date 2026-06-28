"""
Build FlavorDB2 entity index by scanning IDs 1–1000.
Writes Main/flavordb/entity_index.json.

Run once from repo root:
    python Main/flavordb/build_index.py

~18 min at 1 req/sec. Use --max-id 200 for a quick partial index (~3 min).
"""
import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from client import fetch_entity

OUTPUT = Path("Main/flavordb/entity_index.json")


def build(max_id: int = 1000, resume: bool = True) -> dict[str, int]:
    existing: dict[str, int] = {}
    scanned_ids: set[int] = set()

    if resume and OUTPUT.exists():
        existing = json.loads(OUTPUT.read_text())
        sidecar = OUTPUT.with_suffix(".scanned.json")
        if sidecar.exists():
            scanned_ids = set(json.loads(sidecar.read_text()))
        print(f"Resuming: {len(existing)} entities already indexed, {len(scanned_ids)} IDs scanned")

    cache: dict = {}
    found = 0

    for eid in range(1, max_id + 1):
        if eid in scanned_ids:
            continue
        data = fetch_entity(eid, cache)
        scanned_ids.add(eid)
        if data:
            name = data.get("entity_alias_readable", "").strip().lower()
            if name:
                existing[name] = eid
                found += 1
                print(f"  [{eid:4d}] {name}")
        # save checkpoint every 50
        if eid % 50 == 0:
            OUTPUT.write_text(json.dumps(existing, indent=2))
            OUTPUT.with_suffix(".scanned.json").write_text(json.dumps(sorted(scanned_ids)))
            print(f"  checkpoint @ id={eid}: {len(existing)} entities total")

    OUTPUT.write_text(json.dumps(existing, indent=2))
    OUTPUT.with_suffix(".scanned.json").write_text(json.dumps(sorted(scanned_ids)))
    print(f"\nDone. {found} new entities found. Total: {len(existing)}.")
    return existing


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Build FlavorDB2 entity index")
    parser.add_argument("--max-id", type=int, default=1000, help="Highest entity ID to scan (default: 1000)")
    parser.add_argument("--no-resume", action="store_true", help="Start fresh, ignore existing index")
    args = parser.parse_args()
    build(max_id=args.max_id, resume=not args.no_resume)
