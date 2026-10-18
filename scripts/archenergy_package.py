# SPDX-License-Identifier: GPL-3.0-or-later
# © 2026 ArchEnergy s.r.o.
"""Package the verified local build with documentation and a CRC-checked ZIP."""
import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import sys
import zipfile

ROOT = Path(__file__).resolve().parents[1]


def digest(path):
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-commit", required=True, help="Commit used to build the actual EXE.")
    parser.add_argument("--dist-root", type=Path, default=ROOT / "dist",
                        help="Use a separate output folder while an older build is open.")
    args = parser.parse_args()
    source_commit = subprocess.check_output(
        ["git", "rev-parse", "--verify", args.source_commit + "^{commit}"], cwd=ROOT, text=True).strip()
    dist_root = args.dist_root.resolve()
    folder = dist_root / "EnergySketch"
    evidence = ROOT / "output" / "archenergy"
    audits = [json.loads((evidence / name).read_text(encoding="utf-8"))
              for name in ("energy-frozen-bundle-check.json", "energy-frozen-opengl-render.json")]
    assert all(audit["ok"] and audit["frozen"] for audit in audits), "Frozen audits must pass first"
    assert all(item["byte_identical"] for phase in audits[0]["csv_acceptance"].values()
               for item in phase.values()), "All six frozen CSV comparisons must pass"
    for name in ("ARCHENERGY.md", "LICENSE", "AUTHORS", "NOTICE"):
        shutil.copy2(ROOT / name, folder / name)
    shutil.copy2(ROOT / "ARCHENERGY.md", folder / "_internal" / "ARCHENERGY.md")
    assert (folder / "_internal/plugins/archcontrol/RUBY_SORT_LICENSE.txt").is_file()
    files = [path for path in folder.rglob("*") if path.is_file() and path.name != "BUILD-MANIFEST.json"]
    forbidden = {"sketchupapi.dll", "x64-msvcrt-ruby220.dll", "icuuc.dll", "icudt78.dll"}
    assert not any(path.name.lower() in forbidden for path in files)
    manifest = {"product": "EnergySketch", "publisher": "ArchEnergy s.r.o.",
                "source_commit": source_commit, "created_utc": datetime.now(timezone.utc).isoformat(),
                "whole_directory_required": True,
                "csv_acceptance": "All three byte-identical to fresh Ruby references, before and after IGZ reload",
                "files_before_manifest": len(files), "bytes_before_manifest": sum(p.stat().st_size for p in files),
                "executables": {name: {"bytes": (folder / name).stat().st_size, "sha256": digest(folder / name)}
                                for name in ("EnergySketch.exe", "EnergySketch-mcp.exe")},
                "audits": {"bundle": "energy-frozen-bundle-check.json",
                           "opengl": "energy-frozen-opengl-render.json", "passed": True}}
    encoded = json.dumps(manifest, ensure_ascii=False, indent=2) + "\n"
    (folder / "BUILD-MANIFEST.json").write_text(encoded, encoding="utf-8")
    (evidence / "energy-build-manifest.json").write_text(encoded, encoding="utf-8")
    archive = dist_root / "EnergySketch-interni-0.1.zip"
    with zipfile.ZipFile(archive, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=6) as target:
        for path in sorted(folder.rglob("*")):
            if path.is_file():
                target.write(path, path.relative_to(folder.parent))
    with zipfile.ZipFile(archive) as target:
        assert target.testzip() is None, "ZIP CRC validation failed"
        count = len(target.namelist())
    report = {"ok": True, "archive": str(archive), "bytes": archive.stat().st_size,
              "sha256": digest(archive), "files": count, "crc_all_passed": True,
              "source_commit": source_commit, "executables": manifest["executables"]}
    (evidence / "energy-package-audit.json").write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    if sys.platform == "win32":
        subprocess.run(["powershell.exe", "-NoProfile", "-NonInteractive",
                        "-ExecutionPolicy", "Bypass", "-File",
                        str(ROOT / "scripts/archenergy_launcher.ps1"),
                        "-Executable", str(folder / "EnergySketch.exe")], check=True,
                       creationflags=subprocess.CREATE_NO_WINDOW)
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
