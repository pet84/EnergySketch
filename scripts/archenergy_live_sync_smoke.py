# SPDX-License-Identifier: GPL-3.0-or-later
# © 2026 ArchEnergy s.r.o.
"""Full native APP sync and floor reports, isolated state and in-memory credentials."""
import argparse
import json
from pathlib import Path
import subprocess
import sys
import urllib.request

sys.path.insert(0,str(Path(__file__).resolve().parent))
from archenergy_live_app_smoke import ROOT,wait_for,QApplication,configure_profile,MainWindow,History,PanelService,ExtensionApp,live_controller,live_snapshot
from core.scene import Scene


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--app-source',type=Path,required=True)
    args = ap.parse_args()
    qa = ROOT / '.venv/live-app-qa'
    process = subprocess.Popen(['node',str(ROOT / 'scripts/archenergy_live_server_fixture.mjs'),
        str(args.app_source),str(qa),'--reverse','--full-sync'],stdin=subprocess.PIPE,stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,text=True,encoding='utf-8',creationflags=subprocess.CREATE_NO_WINDOW)
    controller = window = None
    try:
        line = process.stdout.readline()
        if not line:
            raise RuntimeError(process.stderr.read()[:500])
        handshake = json.loads(line)
        app = QApplication([])
        configure_profile()
        from main import _init_language
        _init_language()
        window = MainWindow(defer_extensions=True)
        scene = Scene()
        window.viewport.scene,window.viewport.history = scene,History(scene)
        service = PanelService(ExtensionApp(window,'archcontrol'))
        controller = live_controller(service)
        controller.connect_app(handshake['origin'],handshake.pop('code'))
        def status():
            with urllib.request.urlopen(handshake['origin']+'/qa/status',timeout=5) as response:
                return json.load(response)
        def enqueue(action,**params):
            request = urllib.request.Request(handshake['origin']+'/qa/enqueue',
                json.dumps({'action':action,**params}).encode(),{'Content-Type':'application/json'},method='POST')
            try:
                with urllib.request.urlopen(request,timeout=5) as response:
                    return json.load(response)
            except urllib.error.HTTPError as error:
                raise RuntimeError(error.read().decode())
        wait_for(lambda:controller.session.revision==1 or controller.session.paused)
        assert controller.session.revision==1,controller.session.status
        stages = []
        def complete(action,**params):
            prior = {c['id'] for c in status()['commands']}
            enqueue(action,requestId='qa-full-'+action+'-'+str(len(stages)),**params)
            def finished():
                return any(c['id'] not in prior and c['status'] in ('confirmed','mismatch','rejected') for c in status()['commands']) or controller.session.paused
            wait_for(finished)
            outcomes = [c for c in status()['commands'] if c['id'] not in prior]
            assert outcomes and outcomes[-1]['status']=='confirmed',(outcomes,controller.session.status,status()['sync'])
            stages.append({'stage':action,**params,'command':outcomes[-1],'revision':controller.session.revision})
        complete('import_model')
        before = live_snapshot(scene,controller._identities)
        complete('sync_model',edit='color')
        colored = live_snapshot(scene,controller._identities)
        assert set(colored)==set(before),'Material changes must keep native face IDs'
        complete('floor-report')
        before_reports = live_snapshot(scene,controller._identities)
        report_ids = {key for key,e in before_reports.items() if e.get('binding',{}).get('zoneId','').startswith('epcp_')}
        assert report_ids
        complete('floor-report-layout')
        after = live_snapshot(scene,controller._identities)
        assert report_ids=={key for key,e in after.items() if e.get('binding',{}).get('zoneId','').startswith('epcp_')}
        assert all(after[key]==e for key,e in before_reports.items() if key not in report_ids)
        complete('sync_model',edit='move')
        complete('sync_model',edit='remove')
        result = {'ok':True,'server':'Original APP modules, read-only; own isolated localhost state',
                  'stages':stages,'final':status(),'report_native_ids_preserved':True,'unrelated_entities_unchanged':True}
        (ROOT / 'output/archenergy/live-full-sync-app-protocol.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
        print(json.dumps({'ok':True,'stages':[s['stage']+':'+s.get('edit','') for s in stages],
                          'revision':controller.session.revision,'report_faces':len(report_ids)}))
    finally:
        if controller is not None:
            controller.shutdown()
        if window is not None:
            window._saved_version=window.viewport.scene.version
            window.close()
        if process.poll() is None:
            process.stdin.write('stop\n')
            process.stdin.flush()
            process.wait(timeout=15)


if __name__=='__main__':
    main()
