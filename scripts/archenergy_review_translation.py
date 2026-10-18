# SPDX-License-Identifier: GPL-3.0-or-later
# © 2026 ArchEnergy s.r.o.
"""Track human/editorial review of every Czech entry before installation."""
import argparse
import hashlib
import json
from pathlib import Path
import sys
from check_czech_translation import load_catalog, placeholders

ROOT = Path(__file__).resolve().parents[1]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--show", type=int)
    parser.add_argument("--count", type=int, default=100)
    parser.add_argument("--source-only", action="store_true")
    parser.add_argument("--install", action="store_true")
    args = parser.parse_args()
    sys.stdout.reconfigure(encoding="utf-8")
    keys = set()
    for path in (ROOT / "i18n").glob("*.json"):
        if path.stem not in {"en", "cs"}:
            keys.update(load_catalog(path))
    keys = sorted(keys)
    digest = hashlib.sha256(json.dumps(keys, ensure_ascii=False, separators=(",", ":")).encode("utf-8")).hexdigest()
    draft = json.loads((ROOT / "output/archenergy/cs-machine-draft.json").read_text(encoding="utf-8"))
    reviewed = {}
    for batch in sorted((ROOT / "output/archenergy/czech-review").glob("*.json")):
        data = json.loads(batch.read_text(encoding="utf-8"))
        if data["key_digest"] != digest:
            raise ValueError(f"Zdrojové klíče se změnily: {batch.name}")
        for index, value in data["values"].items():
            index = int(index)
            if index in reviewed or not 0 <= index < len(keys):
                raise ValueError(f"Duplicitní/neplatný index {index}: {batch.name}")
            key = keys[index]
            if (not isinstance(value, str) or not value.strip() or
                    placeholders(key) != placeholders(value) or key.count("\n") != value.count("\n")):
                raise ValueError(f"Neplatný překlad nebo placeholdery: {index} {key}")
            reviewed[index] = value
    if args.show is not None:
        print("key_digest:", digest)
        for index in range(args.show, min(args.show + args.count, len(keys))):
            key = keys[index]
            entry = [index, key] if args.source_only else [index, key, reviewed.get(index, draft[key])]
            print(json.dumps(entry, ensure_ascii=False))
    else:
        remaining = [i for i in range(len(keys)) if i not in reviewed]
        report = {"required": len(keys), "reviewed": len(reviewed), "remaining": len(remaining),
                  "first_unreviewed": remaining[0] if remaining else None, "key_digest": digest}
        print(json.dumps(report, ensure_ascii=False, indent=2))
        (ROOT / "output/archenergy/czech-review-status.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
        if args.install:
            if remaining:
                raise ValueError("Nelze instalovat katalog před kontrolou všech textů.")
            catalog = {"_comment": "Český překlad EnergySketch / IngeTrazo, stavební terminologie; © 2026 ArchEnergy s.r.o.; GPL-3.0-or-later."}
            catalog.update({key: reviewed[index] for index, key in enumerate(keys)})
            (ROOT / "i18n/cs.json").write_text(json.dumps(catalog, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
