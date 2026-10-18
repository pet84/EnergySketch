# SPDX-License-Identifier: GPL-3.0-or-later
# © 2026 ArchEnergy s.r.o.
"""Local HTTP fixture only: background network, retries, redirects and model scope."""
from contextlib import contextmanager
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import threading
import time
from PySide6.QtCore import QEventLoop, QTimer
from PySide6.QtGui import QVector3D as V
from core.history import AddFaceCommand, History
from core.scene import Scene
from plugins.archcontrol.live import Request
from plugins.archcontrol.live_transport import post
from plugins.archcontrol.adapter import PanelService, live_controller

# Fake fixture credentials, never a real pairing or APP account.
TOKEN = "1"*64


@contextmanager
def server(retry=False, redirect=None):
    state = {"revision":0,"requests":[],"entities":{},"retry":retry}
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass

        def do_POST(self):
            raw = self.rfile.read(int(self.headers["Content-Length"]))
            body = json.loads(raw)
            state["requests"].append({"path":self.path,"body":raw,
                                      "auth":self.headers.get("Authorization"),
                                      "cookie":self.headers.get("Cookie"),
                                      "origin":self.headers.get("Origin")})
            if redirect:
                self.send_response(302)
                self.send_header("Location",redirect)
                self.end_headers()
                return
            status = 200
            if self.path.endswith("/pair"):
                response = {"token":TOKEN,"projectId":"project","connectionId":"connection","revision":0}
            elif self.headers.get("Authorization") != "Bearer " + TOKEN:
                status,response = 401,{}
            elif self.path.endswith("/batch"):
                if state["retry"]:
                    state["retry"] = False
                    status,response = 503,{}
                else:
                    assert body["baseRevision"] == state["revision"]
                    state["revision"] += 1
                    if body["reset"]:
                        state["entities"].clear()
                    for key in body["removed"]:
                        state["entities"].pop(key,None)
                    for entity in body["upserts"]:
                        state["entities"][entity["id"]] = entity
                    response = {"revision":state["revision"],"connectionId":"connection"}
            else:
                response = {"revision":state["revision"],"connectionId":"connection"}
            data = json.dumps(response).encode()
            self.send_response(status)
            self.send_header("Content-Type","application/json")
            self.send_header("Content-Length",str(len(data)))
            self.end_headers()
            self.wfile.write(data)
    http = ThreadingHTTPServer(("127.0.0.1",0),Handler)
    http.daemon_threads = True
    thread = threading.Thread(target=http.serve_forever,daemon=True)
    thread.start()
    try:
        yield state,f"http://127.0.0.1:{http.server_address[1]}"
    finally:
        http.shutdown()
        http.server_close()
        thread.join(timeout=3)


def wait_for(predicate, timeout=9000):
    loop = QEventLoop()
    timer = QTimer()
    timer.setInterval(15)
    timer.timeout.connect(lambda: loop.quit() if predicate() else None)
    timer.start()
    QTimer.singleShot(timeout,loop.quit)
    if not predicate():
        loop.exec()
    timer.stop()
    assert predicate(), "Timed out waiting for local LIVE fixture"


def make_controller():
    from views.main_window import MainWindow
    from views.extension_api import ExtensionApp
    scene = Scene()
    scene.mesh.add_face([V(0,0,0),V(1,0,0),V(0,1,0)])
    window = MainWindow(defer_extensions=True)
    window.viewport.scene = scene
    window.viewport.history = History(scene)
    app = ExtensionApp(window,"archcontrol")
    controller = live_controller(PanelService(app))
    app.on_document_changed(controller.on_change)
    return window,controller,scene


def test_local_pair_retry_change_undo_and_no_credentials_in_igz(tmp_path,monkeypatch):
    from plugins.archcontrol import live_transport
    original = live_transport.post
    network_threads = []
    main_thread = threading.get_ident()
    def recorded(*args,**kwargs):
        network_threads.append(threading.get_ident())
        return original(*args,**kwargs)
    monkeypatch.setattr(live_transport,"post",recorded)
    with server(retry=True) as (state,origin):
        window,controller,scene = make_controller()
        try:
            controller.connect_app(origin,"QA-CODE")
            wait_for(lambda:controller.session.revision == 1)
            batches = [r for r in state["requests"] if r["path"].endswith("/batch")]
            assert len(batches) == 2 and batches[0]["body"] == batches[1]["body"]
            assert all(t != main_thread for t in network_threads)
            assert state["requests"][0]["auth"] is None
            assert all(r["cookie"] is None and r["origin"] is None for r in state["requests"])
            assert len(state["entities"]) == 1
            history = window.viewport.history
            history.execute(AddFaceCommand([V(3,0,0),V(4,0,0),V(3,1,0)]))
            window.viewport.notify_scene_changed()
            wait_for(lambda:controller.session.revision == 2)
            assert len(state["entities"]) == 2
            history.undo()
            window.viewport.notify_scene_changed()
            wait_for(lambda:controller.session.revision == 3)
            assert len(state["entities"]) == 1
            from formats import igz
            path = tmp_path / "without-credentials.igz"
            igz.save_scene(scene,path)
            import zipfile
            if zipfile.is_zipfile(path):
                with zipfile.ZipFile(path) as archive:
                    contents = [archive.read(name) for name in archive.namelist()]
            else:
                contents = [path.read_bytes()]
            assert all(TOKEN.encode() not in data and b"QA-CODE" not in data for data in contents)
            restored = Scene()
            igz.load_into(restored,path)
            assert TOKEN not in repr(restored.plugin_data) and "QA-CODE" not in repr(restored.plugin_data)
            controller.pause()
            wait_for(lambda:any(r["path"].endswith("/heartbeat") and json.loads(r["body"]).get("presence") == "paused" for r in state["requests"]))
            assert controller.session.revision == 3
        finally:
            controller.shutdown()
            window._saved_version = scene.version
            window.close()


def test_new_document_disconnects_instead_of_uploading_its_geometry():
    with server() as (state,origin):
        window,controller,scene = make_controller()
        try:
            controller.connect_app(origin,"QA-CODE")
            wait_for(lambda:controller.session.revision == 1)
            scene.clear()
            controller.tick()
            assert not controller.session.public_status()["connected"]
            assert "Dokument se změnil" in controller.session.status
            assert state["revision"] == 1 and len(state["entities"]) == 1
        finally:
            controller.shutdown()
            window._saved_version = scene.version
            window.close()


def test_redirect_does_not_forward_bearer_to_another_server():
    with server() as (recipient,other):
        with server(redirect=other+"/stolen") as (sender,origin):
            request = Request(1,1,origin+"/api/penb/live/device/project/batch","/batch",b"{}",TOKEN)
            status,_ = post(request)
            assert status == 302
            assert len(sender["requests"]) == 1 and recipient["requests"] == []
