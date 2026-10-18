# SPDX-License-Identifier: GPL-3.0-or-later
# © 2026 ArchEnergy s.r.o.
"""Protocol parity, retry receipts, credential lifetime and world-mm snapshots."""
import copy
import json
import pytest
from PySide6.QtGui import QMatrix4x4, QVector3D as V
from core.group import Group
from core.materials import Material
from core.mesh import Mesh
from core.scene import Scene
from core.layers import Layer
from plugins.archcontrol.live import LiveSession, MAX_BATCH, validate_url, delta
from plugins.archcontrol.adapter import live_snapshot, LiveIdentities

# Deliberately fake credentials used only by in-process test doubles.
TOKEN = "1"*64


def session():
    now = [0.]
    ids = iter(f"id-{i}" for i in range(100))
    s = LiveSession(clock=lambda: now[0], uuid_factory=lambda: next(ids))
    s.connect("http://localhost:1234", "QA-CODE", "Test", ["presence-v1"])
    req = s.next_request(lambda: {})
    assert req.token is None
    assert json.loads(req.body)["code"] == "QA-CODE"
    assert s.complete(req,200,{"token":TOKEN,"projectId":"project","connectionId":"connection"})
    return s, now


@pytest.mark.parametrize("url", ["http://example.com", "file:///tmp/x", "https://user:pass@site",
                                  "https://site/a", "https://site/?q=x", "https://site/#x",
                                  "http://localhost.evil", "http://127.0.0.2", "http://[::2]",
                                  "https://site:0", "https://site:70000", "https://local\nhost"])
def test_untrusted_or_nonlocal_http_addresses_are_refused(url):
    with pytest.raises(ValueError):
        validate_url(url)


@pytest.mark.parametrize("url", ["https://app.archenergy.cz", "http://localhost:1234/", "http://[::1]:4567", "http://127.0.0.1"])
def test_allowed_origins(url):
    assert validate_url(url) == url.rstrip("/")


def test_retry_keeps_identical_change_id_bytes_and_snapshot_until_ack():
    s, now = session()
    snapshot = {"face:1":{"id":"face:1","value":1}}
    request = s.next_request(lambda:snapshot)
    original = request.body
    assert json.loads(original)["reset"] is True
    snapshot["face:1"]["value"] = 2
    s.dirty()
    assert not s.complete(request,503,{"error":TOKEN})
    assert s.next_request(lambda:snapshot) is None
    now[0] = 3.1
    retry = s.next_request(lambda:snapshot)
    assert retry.body == original and retry.token == TOKEN
    assert TOKEN not in repr(retry) and TOKEN not in repr(s.public_status())
    assert s.complete(retry,200,{"revision":1,"connectionId":"connection"})
    assert s.acked["face:1"]["value"] == 1
    assert s.revision == 1 and s.stats["batches"] == 1
    next_request = s.next_request(lambda:snapshot)
    assert json.loads(next_request.body)["upserts"][0]["value"] == 2
    assert json.loads(next_request.body)["baseRevision"] == 1


def test_pause_and_editing_send_heartbeat_without_collecting_geometry():
    s, now = session()
    def forbidden():
        raise AssertionError("Geometry must not be read")
    s.toggle_pause()
    request = s.next_request(forbidden)
    assert request.route.endswith("/heartbeat")
    assert json.loads(request.body) == {"presence":"paused"}
    s.complete(request,200,{"revision":0,"connectionId":"connection"})
    assert s.public_status()["connectionStatus"] == "online"
    now[0] = 9
    assert s.public_status()["connectionStatus"] == "offline"
    s.toggle_pause()
    request = s.next_request(forbidden,editing=True)
    assert json.loads(request.body)["presence"] == "editing"


def test_disconnect_rejects_delayed_responses_and_clears_credentials():
    s, now = session()
    old = s.next_request(lambda:{})
    first_id = s.model_id
    s.disconnect()
    assert not s.complete(old,200,{"revision":1,"connectionId":"connection"})
    assert not s.public_status()["connected"] and s._token is None and s.pending is None
    s.connect("https://example.com","NEW-CODE","Other")
    assert s.model_id != first_id
    assert TOKEN not in repr(s.public_status())


@pytest.mark.parametrize("status", [401,403,404,409,413,422,302])
def test_auth_conflict_size_and_redirect_do_not_silently_continue(status):
    s, now = session()
    request = s.next_request(lambda:{})
    s.complete(request,status,{"error":TOKEN})
    assert s.paused
    assert s.public_status()["needsPairing"] == (status in (401,403,404))
    assert TOKEN not in json.dumps(s.public_status())


def test_batch_ack_must_confirm_the_current_connection_and_revision():
    s, now = session()
    request = s.next_request(lambda:{})
    assert not s.complete(request,200,{"revision":1,"connectionId":"wrong"})
    assert s.revision == 0 and s.pending is not None and s.paused


def test_utf8_size_is_checked_before_a_large_batch_can_be_sent():
    s, now = session()
    with pytest.raises(ValueError,match="6 MB"):
        s.next_request(lambda:{"face:1":{"id":"face:1","material":"ž"*(MAX_BATCH//2)}})
    assert s.pending is None and s.inflight is None


def test_delta_preserves_removals_and_does_not_alias_mutable_input():
    current = {"a":{"id":"a","x":2}}
    change = delta({"a":{"id":"a","x":1},"b":{"id":"b"}},current)
    current["a"]["x"] = 3
    assert change == {"upserts":[{"id":"a","x":2}],"removed":["b"]}


def test_snapshot_world_mm_holes_back_report_inheritance_and_hidden_layers():
    scene = Scene()
    scene.layers.append(Layer("Skrytá", False))
    mesh = Mesh()
    face = mesh.add_face([V(0,0,0),V(2,0,0),V(2,2,0),V(0,2,0)],
                         [[V(.5,.5,0),V(.5,1,0),V(1,1,0),V(1,.5,0)]])
    face.attrs.update(back={"mat":"EP-1-Zóna"},archcontrol={"source_face_id":12})
    edge = mesh.add_edge(V(0,0,1),V(1,0,1))
    group = Group(mesh, "Podlaží")
    group.xform = QMatrix4x4()
    group.xform.translate(10,20,3)
    group.layer = "Skrytá"
    group.material = {"mat":"SO-1"}
    scene.groups = [group]
    scene.materials = {"EP-1-Zóna":Material("EP-1-Zóna",(.2,.4,.6),opacity=.5)}
    before = mesh.capture_state()
    ids = LiveIdentities()
    snapshot = live_snapshot(scene,ids)
    faces = [v for v in snapshot.values() if v["kind"] == "face"]
    edges = [v for v in snapshot.values() if v["kind"] == "edge"]
    assert len(faces) == len(edges) == 1
    result = faces[0]
    assert result["rings"][0][0] == [10000.,20000.,3000.]
    assert len(result["rings"]) == 2 and result["color"] == [51,102,153]
    assert result["material"] == "EP-1-Zóna" and result["alpha"] == .5
    assert result["hidden"] and result["layer"] == "Skrytá" and result["zone"] == "Podlaží"
    assert edges[0]["material"] == "SO-1" and edges[0]["hidden"]
    assert snapshot == live_snapshot(scene,ids)
    assert mesh.capture_state() == before


def test_duplicate_imported_face_ids_get_distinct_connection_ids_without_document_writes():
    scene = Scene()
    a = scene.mesh.add_face([V(0,0,0),V(1,0,0),V(0,1,0)])
    b = scene.mesh.add_face([V(2,0,0),V(3,0,0),V(2,1,0)])
    for face in (a,b):
        face.attrs["archcontrol"] = {"source_face_id":5}
    ids = LiveIdentities()
    before = copy.deepcopy([a.attrs,b.attrs])
    first = live_snapshot(scene,ids)
    assert set(first) == {"face:5","face:6"}
    scene.mesh.faces.reverse()
    assert live_snapshot(scene,ids) == first
    assert [a.attrs,b.attrs] == before and scene.plugin_data == {}
