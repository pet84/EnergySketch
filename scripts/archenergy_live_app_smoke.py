# SPDX-License-Identifier: GPL-3.0-or-later
# © 2026 ArchEnergy s.r.o.
"""Real APP protocol against an isolated loopback fixture, never a live project."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import urllib.request
import zipfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
os.environ["QT_QPA_PLATFORM"] = "offscreen"
os.environ["APPDATA"] = tempfile.mkdtemp(prefix="energysketch-live-app-")
from PySide6.QtCore import QEventLoop, QTimer
from PySide6.QtWidgets import QApplication
from core.archenergy import configure_profile
from core.history import History
from plugins.archcontrol.adapter import parse_skp, PanelService, live_controller, live_snapshot, face_records
from views.main_window import MainWindow
from views.extension_api import ExtensionApp


def wait_for(predicate,timeout=20000):
    loop = QEventLoop()
    timer = QTimer()
    timer.setInterval(20)
    timer.timeout.connect(lambda:loop.quit() if predicate() else None)
    timer.start()
    QTimer.singleShot(timeout,loop.quit)
    if not predicate():
        loop.exec()
    timer.stop()
    if not predicate():
        raise RuntimeError("Local APP protocol did not reach the expected revision")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("model",type=Path)
    ap.add_argument("--app-source",type=Path,required=True)
    ap.add_argument("--reverse",action="store_true")
    args = ap.parse_args()
    source_hash = hashlib.sha256(args.model.read_bytes()).hexdigest()
    qa = ROOT / ".venv/live-app-qa"
    qa.mkdir(parents=True,exist_ok=True)
    process = subprocess.Popen(["node",str(ROOT / "scripts/archenergy_live_server_fixture.mjs"),
                                str(args.app_source),str(qa),*( ["--reverse"] if args.reverse else [])],
                               stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.PIPE,
                               text=True,encoding="utf-8",creationflags=subprocess.CREATE_NO_WINDOW)
    controller = window = None
    try:
        line = process.stdout.readline()
        if not line:
            raise RuntimeError("Local APP fixture failed: " + process.stderr.read()[:500])
        handshake = json.loads(line)  # code stays only in process memory
        app = QApplication([])
        configure_profile()
        from main import _init_language
        _init_language()
        window = MainWindow(defer_extensions=True)
        scene = parse_skp(args.model)
        window.viewport.scene,window.viewport.history = scene,History(scene)
        service = PanelService(ExtensionApp(window,"archcontrol"))
        controller = live_controller(service)
        code = handshake.pop("code")
        controller.connect_app(handshake["origin"],code)
        wait_for(lambda:controller.session.revision == 1 or controller.session.paused)
        if controller.session.revision != 1:
            raise RuntimeError(controller.session.status)
        def status():
            with urllib.request.urlopen(handshake["origin"]+"/qa/status",timeout=5) as response:
                return json.load(response)
        first = status()
        expected_count = len(live_snapshot(scene,controller._identities))
        assert first["entities"] == expected_count and first["firstRetryIdentical"]
        pid = next(rec.pid for rec in face_records(scene) if rec.visible)
        service.set_faces_hidden([pid],True)
        controller.on_change()
        wait_for(lambda:controller.session.revision == 2 or controller.session.paused)
        assert controller.session.revision == 2,controller.session.status
        second = status()
        assert second["summary"]["hidden"] > first["summary"]["hidden"]
        assert window.viewport.history.undo()
        controller.on_change()
        wait_for(lambda:controller.session.revision == 3 or controller.session.paused)
        assert controller.session.revision == 3,controller.session.status
        third = status()
        assert third["summary"] == first["summary"]
        reverse_results = []
        if args.reverse:
            for i,action in enumerate(("box","pyramid","colors","import_model"),1):
                request_id = f"energysketch-qa-{action}-{i}"
                request = urllib.request.Request(handshake["origin"]+"/qa/enqueue",
                    json.dumps({"action":action,"requestId":request_id}).encode(),
                    {"Content-Type":"application/json"},method="POST")
                with urllib.request.urlopen(request,timeout=5) as response:
                    response.read()
                def completed():
                    return any(c["id"] == request_id and c["status"] in ("confirmed","mismatch","rejected") for c in status()["commands"])
                wait_for(completed)
                outcome = next(c for c in status()["commands"] if c["id"] == request_id)
                if outcome["status"] != "confirmed":
                    raise RuntimeError(f"Local {action} command: " + json.dumps(outcome,ensure_ascii=False))
                reverse_results.append(outcome)
        from formats import igz
        saved = qa / "qa-no-credentials.igz"
        igz.save_scene(scene,saved)
        if zipfile.is_zipfile(saved):
            with zipfile.ZipFile(saved) as archive:
                contents = [archive.read(name) for name in archive.namelist()]
        else:
            contents = [saved.read_bytes()]
        token = controller.session._token.encode()
        assert all(token not in value and code.encode() not in value for value in contents)
        controller.pause()
        wait_for(lambda:status()["presence"] == "paused")
        assert hashlib.sha256(args.model.read_bytes()).hexdigest() == source_hash
        result = {"ok":True,"server":"Existing APP modules imported read-only in isolated localhost fixture",
                  "model_sha256":source_hash,"source_file_unchanged":True,
                  "initial":first,"after_hide":second,"after_undo":third,
                  "credentials_absent_from_igz":True,"pause_heartbeat":True,
                  "reverse_commands_enabled":args.reverse,"reverse_commands":reverse_results}
        target = "reference-model-live-reverse-app-protocol.json" if args.reverse else "reference-model-live-app-protocol.json"
        (ROOT / "output/archenergy" / target).write_text(
            json.dumps(result,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
        print(json.dumps({"ok":True,"initial_entities":expected_count,"revisions":controller.session.revision,
                          "reverse_commands":[c["action"] for c in reverse_results],
                          "retry_identical":True,"source_unchanged":True,
                          "credentials_absent_from_igz":True},indent=2))
    finally:
        if controller is not None:
            controller.shutdown()
        if window is not None:
            window._saved_version = window.viewport.scene.version
            window.close()
        if process.poll() is None:
            process.stdin.write("stop\n")
            process.stdin.flush()
            process.wait(timeout=15)


if __name__ == "__main__":
    main()
