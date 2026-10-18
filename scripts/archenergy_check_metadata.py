# SPDX-License-Identifier: GPL-3.0-or-later
# © 2026 ArchEnergy s.r.o.
"""Compare free parser metadata against separate installed-SDK oracle fixtures."""
import hashlib
import json
from pathlib import Path
import sys

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from plugins.archcontrol.adapter import parse_skp


def main():
    results=[]
    for manifest in sorted((ROOT / '.venv/skp-metadata-fixtures').glob('*-manifest.json')):
        for item in json.loads(manifest.read_text(encoding='utf-8')):
            path=Path(item['path'])
            before=hashlib.sha256(path.read_bytes()).hexdigest()
            data=parse_skp(path).plugin_data['archcontrol']
            value=data['model_dictionaries'].get('ArchControl_LiveModel',{}).get('metadata')
            actual=json.loads(value) if isinstance(value,str) else value
            ok=abs(data['north_angle']-item['north_angle'])<1e-9 and actual==item['model_dictionary'] and 'north_angle' not in data['import']['unverified'] and 'model_dictionaries' not in data['import']['unverified']
            assert ok,(path.name,data['north_angle'],actual)
            assert before==item['sha256']==hashlib.sha256(path.read_bytes()).hexdigest()
            results.append({'fixture':path.name,'north_angle':data['north_angle'],'metadata_matches':True,'sha256':before,'unchanged':True})
    oracle=json.loads((ROOT / 'output/archenergy/reference-model-shadow-oracle.json').read_text(encoding='utf-8'))
    source=Path(oracle['source'])
    data=parse_skp(source).plugin_data['archcontrol']
    assert data['north_angle']==oracle['model_north_angle']
    assert hashlib.sha256(source.read_bytes()).hexdigest()==oracle['source_sha256']
    report={'ok':bool(results),'fixtures':results,'customer_sha256':oracle['source_sha256'],
            'customer_north':data['north_angle'],'customer_model_dictionary_names':sorted(data['model_dictionaries']),
            'source_unchanged':True,'runtime_sdk_required':False,'verified_layout':'v17 shadow schema 7 / root metadata container'}
    (ROOT / 'output/archenergy/skp-metadata-oracle-comparison.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(json.dumps({'ok':True,'fixtures':len(results),'customer_north':data['north_angle'],'source_unchanged':True}))


if __name__=='__main__':
    main()
