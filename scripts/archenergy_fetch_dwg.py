# SPDX-License-Identifier: GPL-3.0-or-later
# © 2026 ArchEnergy s.r.o.
"""Fetch the exact official LibreDWG package pinned by upstream Windows CI."""
from pathlib import Path
import hashlib
import json
import urllib.request
import zipfile

ROOT = Path(__file__).resolve().parents[1]
VERSION = "0.14.8597"
SHA = "7fee5c67c4f451f0542c0d6a3b12e91e99b15faf363fbf8b98ad84bac17ddfa2"
URL = f"https://github.com/LibreDWG/libredwg/releases/download/{VERSION}/libredwg-{VERSION}-win64.zip"


def main():
    path = ROOT / ".venv/build-downloads" / f"libredwg-{VERSION}-win64.zip"
    path.parent.mkdir(parents=True, exist_ok=True)
    if not path.is_file():
        req = urllib.request.Request(URL, headers={"User-Agent": "EnergySketch-internal-build"})
        with urllib.request.urlopen(req, timeout=90) as response:
            path.write_bytes(response.read())
    if hashlib.sha256(path.read_bytes()).hexdigest() != SHA:
        raise ValueError("LibreDWG archive differs from upstream's pinned SHA256")
    extracted = []
    with zipfile.ZipFile(path) as archive:
        bad = archive.testzip()
        if bad:
            raise ValueError(f"Corrupt zip entry {bad}")
        for name in ("dwg2dxf.exe", "libredwg-0.dll", "libiconv-2.dll"):
            data = archive.read(name)
            if not data.startswith(b"MZ"):
                raise ValueError(f"Not a Windows PE file: {name}")
            target = ROOT / "vendor/libredwg/bin" / name
            target.write_bytes(data)
            extracted.append({"name": name, "bytes": len(data), "sha256": hashlib.sha256(data).hexdigest()})
    report = {"url": URL, "archive_sha256": SHA, "verified_against": ".github/workflows/build-windows.yml", "files": extracted}
    (ROOT / "output/archenergy/libredwg-build-download.json").write_text(
        json.dumps(report, indent=2)+"\n", encoding="utf-8")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
