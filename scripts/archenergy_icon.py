# SPDX-License-Identifier: GPL-3.0-or-later
# © 2026 ArchEnergy s.r.o.
"""Install Petr's supplied icon/logo assets unchanged; never regenerate them."""
from pathlib import Path
import hashlib
import json
import shutil

ROOT = Path(__file__).resolve().parents[1]


def main():
    brand = ROOT / "brand/energysketch"
    icons = ROOT / "resources/icons"
    assets = [("windows/energysketch.ico", "energysketch.ico"),
              ("svg/energysketch-ikona-aplikace-svetla.svg", "energysketch.svg"),
              ("svg/energysketch-logo.svg", "energysketch-logo.svg"),
              ("svg/energysketch-logo-bile.svg", "energysketch-logo-dark.svg")]
    assets += [(f"png/energysketch-ikona-aplikace-svetla-{size}.png", f"energysketch_{size}.png")
               for size in (16, 32, 48, 64, 128, 256, 512)]
    for source, target in assets:
        if not (brand / source).is_file():
            raise FileNotFoundError(brand / source)
    report = []
    for source, target in assets:
        shutil.copyfile(brand / source, icons / target)
        original = (brand / source).read_bytes()
        assert original == (icons / target).read_bytes()
        report.append({"source": source, "resource": target,
                       "sha256": hashlib.sha256(original).hexdigest()})
    output = ROOT / "output/archenergy/approved-brand-assets.json"
    output.write_text(json.dumps({"ok": True, "unchanged_copies": report}, indent=2), encoding="utf-8")
    print(f"Copied {len(assets)} approved assets unchanged; original brand folder untouched.")


if __name__ == "__main__":
    main()
