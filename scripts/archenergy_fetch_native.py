# SPDX-License-Identifier: GPL-3.0-or-later
# © 2026 ArchEnergy s.r.o.
"""Fetch the unmodified Rust kernel from the verified upstream Windows release.

The kernel sources are exactly rust/ingetrazo_core at v0.5.11. Only the
abi3 Python package is extracted; the upstream application is not installed.
"""
from pathlib import Path
import hashlib
import json
import urllib.request
import zipfile

ROOT = Path(__file__).resolve().parents[1]
TAG = 'v0.5.11'
URL = f'https://github.com/ingelibre/ingetrazo/releases/download/{TAG}/ingetrazo-windows.zip'
SHA256 = 'c26c72d6bda4d250bdb5d50a1317d7ed75679c3327d8d5faaf30b0d02cb3beec'


def main():
    archive = ROOT / '.venv/build-downloads/ingetrazo-windows-0.5.11.zip'
    archive.parent.mkdir(parents=True, exist_ok=True)
    if not archive.is_file():
        request = urllib.request.Request(URL, headers={'User-Agent':'EnergySketch-build'})
        with urllib.request.urlopen(request, timeout=60) as response, archive.open('wb') as output:
            while chunk := response.read(1024 * 1024):
                output.write(chunk)
    with archive.open('rb') as stream:
        assert hashlib.file_digest(stream, 'sha256').hexdigest() == SHA256, 'Upstream archive SHA256 mismatch'
    target = ROOT / 'vendor/native-windows-0511'
    extracted = []
    with zipfile.ZipFile(archive) as source:
        for info in source.infolist():
            parts = Path(info.filename).parts
            if 'ingetrazo_core' not in parts or info.is_dir():
                continue
            relative = Path(*parts[parts.index('ingetrazo_core'):])
            assert '..' not in relative.parts and relative.suffix in ('.py', '.pyd'), relative
            data = source.read(info)
            if relative.suffix == '.pyd':
                assert data.startswith(b'MZ'), relative
            # The frozen archive stores the wrapper in PYZ. Its abi3 kernel
            # exports PyInit_ingetrazo_core and can be imported directly.
            dest = target / (relative.name if relative.suffix == '.pyd' else relative)
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_bytes(data)
            extracted.append({'archive_path':info.filename, 'path':str(dest.relative_to(target)), 'sha256':hashlib.sha256(data).hexdigest(), 'bytes':len(data)})
    assert any(item['path'].endswith('.pyd') for item in extracted), 'No native kernel in archive'
    report = {'upstream_tag':TAG, 'url':URL, 'archive_sha256':SHA256, 'files':extracted}
    (ROOT / 'output/archenergy/upgrade-0511-native.json').write_text(json.dumps(report, indent=2)+'\n', encoding='utf-8')
    print(json.dumps(report, indent=2))


if __name__ == '__main__':
    main()
