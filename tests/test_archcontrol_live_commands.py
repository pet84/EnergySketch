# SPDX-License-Identifier: GPL-3.0-or-later
# © 2026 ArchEnergy s.r.o.
"""Whitelisted commands: transaction rollback, native geometry and idempotent ACK."""
import copy
import json
import time
from types import SimpleNamespace
import pytest
from PySide6.QtGui import QVector3D as V
from core.history import History
from core.materials import Material
from core.scene import Scene
from plugins.archcontrol.adapter import (PanelService,LiveIdentities,execute_live_command,
                                         live_snapshot,component_volume,face_records)
from plugins.archcontrol.core import triangulated_area
from plugins.archcontrol.live import LiveSession
from plugins.archcontrol.live_commands import native_id,validate_model,validate_command


def command(action="box",**changes):
    return {"protocol":1,"id":"command-1","action":action,"modelId":"model",
            "connectionId":"connection","baseRevision":1,"createdAt":time.time()*1000,
            "expiresAt":time.time()*1000+60000,
            "payload":{"origin":[0,0,0],"size":[3000,2000,2500]},**changes}


def payload():
    window = [[1000,0,1000],[2000,0,1000],[2000,0,2000],[1000,0,2000]]
    return {"projectId":"project","sourceRevision":4,"version":"working",
            "zones":[{"id":"zone-a","nativeId":native_id("project","zone-a"),"name":"Přízemí"}],
            "materials":[{"id":"wall","type":"SO","variant":1,"name":"Zdivo","color":[100,150,200],"u":.3,"g":None},
                         {"id":"window","type":"OD","variant":1,"name":"Okno","color":[20,40,100],"u":1.2,"g":.5}],
            "faces":[{"id":"wall-a","zoneId":"zone-a","constructionId":"wall","hostFaceId":None,
                      "rings":[[[0,0,0],[4000,0,0],[4000,0,3000],[0,0,3000]],list(reversed(window))],
                      "source":"QA","confidence":"inferred","kind":"wall"},
                     {"id":"opening-a","zoneId":"zone-a","constructionId":"window","hostFaceId":"wall-a",
                      "rings":[window],"source":"QA","confidence":"inferred","kind":"window"}]}


def setup_scene():
    scene = Scene()
    original = scene.mesh.add_face([V(20,0,0),V(21,0,0),V(20,1,0)])
    original.attrs["mat"] = "SO-1-V1-U0.2-Původní"
    scene.materials[original.attrs["mat"]] = Material(original.attrs["mat"],(.3,.3,.3))
    scene.plugin_data["archcontrol"] = {"north_angle":15,"material_dictionaries":{original.attrs["mat"]:{"ArchControl_RP":{"klient":"Ano"}}}}
    history = History(scene)
    viewport = SimpleNamespace(history=history,notify_scene_changed=lambda:None,update=lambda:None)
    service = PanelService(SimpleNamespace(scene=scene,viewport=viewport,window=None))
    return scene,history,service,original


def sync_payload(p,snapshot,face_ids,removed=(),native=False):
    result = copy.deepcopy(p)
    result.update(purpose="model-sync",sourceRevision=p["sourceRevision"]+1,
                  faces=[f for f in result["faces"] if f["id"] in face_ids],removed=list(removed),
                  expected=[e for e in snapshot.values() if e.get("binding",{}).get("faceId") in [*face_ids,*removed]])
    if native:
        linked = [e for e in snapshot.values() if e.get("binding",{}).get("projectId")==p["projectId"]]
        path = linked[0]["id"][5:].split("/")[:-1]
        result.update(addressing="native-path-v1",targets=[{"id":e["binding"]["faceId"],"nativeId":e["id"],"zoneId":e["binding"]["zoneId"]} for e in result["expected"]],
            containers=[{"key":"container-a","zoneId":p["zones"][0]["id"],"path":path,"faceIds":list(face_ids),"removeIds":list(removed),
                         "identities":[{"id":e["binding"]["faceId"],"nativeId":e["id"]} for e in linked]}])
    return result


@pytest.mark.parametrize("native",[False,True])
def test_addressed_material_move_delete_and_undo(native):
    scene,history,service,original = setup_scene()
    ids = LiveIdentities()
    p = payload()
    before = execute_live_command(service,command("import_model",payload=p),ids)
    wall_before = next(e for e in before.values() if e.get("binding",{}).get("faceId")=="wall-a")
    change = sync_payload(p,before,["wall-a"],native=native)
    change["materials"][0]["color"] = [240,40,20]
    painted = execute_live_command(service,command("sync_model",id="paint",payload=change),ids)
    wall = next(e for e in painted.values() if e.get("binding",{}).get("faceId")=="wall-a")
    assert wall["id"]==wall_before["id"] and wall["rings"]==wall_before["rings"]
    assert wall["color"]==[240,40,20]
    moved = sync_payload(p,painted,["wall-a","opening-a"],native=native)
    for f in moved["faces"]:
        f["rings"] = [[[v[0],v[1]+500,v[2]] for v in r] for r in f["rings"]]
    result = execute_live_command(service,command("sync_model",id="move",payload=moved),ids)
    assert len(result)==3 and not any(e["kind"]=="edge" for e in result.values())
    assert original in scene.mesh.faces
    assert history.undo() and live_snapshot(scene,ids)==painted
    assert history.redo() and live_snapshot(scene,ids)==result
    delete = sync_payload(p,result,[],["wall-a","opening-a"],native=native)
    final = execute_live_command(service,command("sync_model",id="remove",payload=delete),ids)
    assert len(final)==1 and next(iter(final.values()))["zoneId"]=="root"
    assert history.undo() and live_snapshot(scene,ids)==result


@pytest.mark.parametrize("problem",["stale","copied","locked","identities","shared"])
def test_addressed_edit_fails_closed_without_changing_history(problem):
    from core.group import Group
    scene,history,service,original = setup_scene()
    ids = LiveIdentities()
    p = payload()
    before = execute_live_command(service,command("import_model",payload=p),ids)
    change = sync_payload(p,before,["wall-a"],native=problem=="identities")
    group = scene.groups[0]
    if problem=="stale":
        change["expected"][0]["hidden"] = True
    elif problem in ("shared","copied"):
        other = Group(group.mesh,"Kopie")
        if problem=="copied":
            other.ext = copy.deepcopy(group.ext)
        scene.groups.append(other)
    elif problem=="locked":
        group.locked = True
    else:
        change["containers"][0]["identities"].pop()
    unchanged = live_snapshot(scene,ids)
    count = len(history.undo_stack)
    with pytest.raises(ValueError):
        execute_live_command(service,command("sync_model",id="refused",payload=change),ids)
    assert live_snapshot(scene,ids)==unchanged and len(history.undo_stack)==count


def report_payload(snapshot,p,delta=(0,0,3000)):
    result = copy.deepcopy(p)
    result.update(purpose="floor-report-layout",layerName="EP/CP",sourceRevision=p["sourceRevision"]+1,
                  expected=[e for e in snapshot.values() if e.get("binding",{}).get("projectId")==p["projectId"]])
    result["moves"] = [{"faceId":f["id"],"zoneId":f["zoneId"],"floorId":"floor-a","elevationMm":3000,"cutMm":1200,"delta":list(delta)} for f in result["faces"]]
    for f in result["faces"]:
        f["rings"] = [[[v[k]+delta[k] for k in range(3)] for v in r] for r in f["rings"]]
    return result


def test_report_layout_moves_vertices_in_place_with_holes_and_undo():
    scene,history,service,original = setup_scene()
    ids = LiveIdentities()
    p = payload()
    p["zones"][0].update(id="epcp_zone-a",nativeId=native_id(p["projectId"],"epcp_zone-a"))
    for f in p["faces"]:
        f["zoneId"] = "epcp_zone-a"
    before = execute_live_command(service,command("import_model",payload=p),ids)
    original_faces = list(scene.groups[0].mesh.faces)
    original_vertices = list(scene.groups[0].mesh.vertices)
    result = execute_live_command(service,command("import_model",id="report",payload=report_payload(before,p)),ids)
    assert set(result)==set(before)
    assert scene.groups[0].mesh.faces==original_faces and scene.groups[0].mesh.vertices==original_vertices
    assert history.undo() and live_snapshot(scene,ids)==before
    assert history.redo() and live_snapshot(scene,ids)==result
    bad = report_payload(result,p)
    bad["moves"][0]["delta"][2] += 100
    with pytest.raises(ValueError,match="Sdílený vrchol"):
        execute_live_command(service,command("import_model",id="bad-report",payload=bad),ids)
    assert live_snapshot(scene,ids)==result


@pytest.mark.parametrize("root",[True,False])
def test_native_unbound_root_and_nested_path_preserve_unaffected_siblings(root):
    from PySide6.QtGui import QMatrix4x4
    from core.group import Group
    from core.mesh import Mesh
    from plugins.archcontrol.live_commands import native_id
    scene,history,service,original = setup_scene()
    ids = LiveIdentities()
    if not root:
        parent,child = Group(Mesh(),"Vnější"),Group(Mesh(),"Vnitřní")
        parent.xform,child.xform = QMatrix4x4(),QMatrix4x4()
        parent.xform.translate(7,2,1)
        child.xform.rotate(30,0,0,1)
        child.xform.scale(2)
        child.mesh.add_face([V(0,0,0),V(1,0,0),V(0,1,0)]).attrs.update(original.attrs)
        child.mesh.add_face([V(3,0,0),V(4,0,0),V(3,1,0)]).attrs.update(original.attrs)
        parent.children.append(child)
        scene.groups.append(parent)
    before = live_snapshot(scene,ids)
    addressed = next(e for e in before.values() if (e["zoneId"]=="root")==root)
    path = addressed["id"][5:].split("/")[:-1]
    peers = [e for e in before.values() if e["id"][5:].split("/")[:-1]==path]
    p = {"projectId":"project","sourceRevision":2,"version":"accepted","purpose":"model-sync","addressing":"native-path-v1",
         "zones":[{"id":"native-zone","name":"Moje zóna","nativeId":native_id("project","native-zone")}],
         "materials":[{"id":"wall","type":"SO","variant":1,"name":"Stěna","color":[80,90,100],"u":.2,"g":None,"nativeMaterial":original.attrs["mat"]}],
         "faces":[{"id":"logical-0","zoneId":"native-zone","constructionId":"wall","hostFaceId":None,"confidence":"inferred","source":"QA",
                   "rings":[[[v[0]+100,v[1],v[2]+100] for v in addressed["rings"][0]]]}],
         "removed":[],"expected":[addressed],"targets":[{"id":"logical-0","zoneId":"native-zone","nativeId":addressed["id"]}],
         "containers":[{"key":"container","zoneId":"native-zone","path":path,"faceIds":["logical-0"],"removeIds":[],
                         "identities":[{"id":"logical-"+str(i),"nativeId":e["id"]} for i,e in enumerate(peers)]}]}
    result = execute_live_command(service,command("sync_model",payload=p),ids)
    assert len(result)==len(before)
    assert all(result[key]==e for key,e in before.items() if key!=addressed["id"])
    assert history.undo() and live_snapshot(scene,ids)==before


def test_demo_solids_and_colors_are_native_closed_and_undoable():
    scene,history,service,original = setup_scene()
    ids = LiveIdentities()
    execute_live_command(service,command(),ids)
    execute_live_command(service,command("pyramid",id="command-2",payload={"origin":[5000,0,0],"size":[3000,3000,3000]}),ids)
    assert len(scene.groups) == 2
    assert component_volume(scene.groups[0]) == pytest.approx(15,abs=1e-5)
    assert component_volume(scene.groups[1]) == pytest.approx(9,abs=1e-5)
    execute_live_command(service,command("colors",id="command-3",payload={}),ids)
    colors = {tuple(v["color"]) for v in live_snapshot(scene,ids).values() if v["zoneId"] != "root"}
    assert colors == {(45,125,220),(235,130,45)}
    assert original.attrs["mat"] == "SO-1-V1-U0.2-Původní"
    assert len(history.undo_stack) == 3
    assert history.undo()
    assert {tuple(v["color"]) for v in live_snapshot(scene,ids).values() if v["zoneId"] != "root"} == {(180,190,200)}
    assert history.redo()
    assert len(scene.groups) == 2


def test_model_import_preserves_holes_bindings_existing_data_and_redo_ids():
    scene,history,service,original = setup_scene()
    ids = LiveIdentities()
    before = copy.deepcopy(scene.plugin_data)
    snapshot = execute_live_command(service,command("import_model",payload=payload()),ids)
    assert len(scene.groups) == 1 and len(scene.groups[0].mesh.faces) == 2
    records = [r for r in face_records(scene) if r.zone == "Přízemí"]
    assert sorted(triangulated_area(r.triangles) for r in records) == pytest.approx([1,11])
    model_faces = [v for v in snapshot.values() if v["zoneId"] != "root"]
    assert {v["binding"]["faceId"] for v in model_faces} == {"wall-a","opening-a"}
    assert all(v["binding"]["transferId"] == "command-1" for v in model_faces)
    assert len(next(v for v in model_faces if v["binding"]["faceId"] == "wall-a")["rings"]) == 2
    assert any(name.startswith("SO-2-V1") for name in scene.materials)
    assert scene.plugin_data["archcontrol"]["north_angle"] == 15
    assert scene.plugin_data["archcontrol"]["material_dictionaries"][original.attrs["mat"]] == before["archcontrol"]["material_dictionaries"][original.attrs["mat"]]
    assert history.undo()
    assert not scene.groups and scene.mesh.faces == [original] and scene.plugin_data == before
    assert list(scene.materials) == [original.attrs["mat"]]
    assert history.redo()
    assert live_snapshot(scene,ids) == snapshot


def test_result_size_failure_rolls_back_groups_materials_metadata_and_history(monkeypatch):
    from plugins.archcontrol import adapter
    scene,history,service,original = setup_scene()
    before = copy.deepcopy(scene.plugin_data)
    monkeypatch.setattr(adapter,"live_snapshot",lambda *_:{"big":{"value":"x"*(6*1024*1024)}})
    with pytest.raises(ValueError,match="limit"):
        execute_live_command(service,command("import_model",payload=payload()),LiveIdentities())
    assert not scene.groups and scene.mesh.faces == [original]
    assert list(scene.materials) == [original.attrs["mat"]]
    assert scene.plugin_data == before and not history.undo_stack


@pytest.mark.parametrize("change", ["self_crossing","nonplanar","outside_hole","duplicate_id","invalid_u"])
def test_invalid_model_is_refused_before_a_native_transaction(change):
    p = payload()
    if change == "self_crossing":
        p["faces"][0]["rings"] = [[[0,0,0],[4000,0,3000],[4000,0,0],[0,0,3000]]]
    elif change == "nonplanar":
        p["faces"][0]["rings"][0][1][1] = 50
    elif change == "outside_hole":
        p["faces"][0]["rings"][1][0][0] = 10000
    elif change == "duplicate_id":
        p["faces"][1]["id"] = p["faces"][0]["id"]
    else:
        p["materials"][0]["u"] = float('nan')
    scene,history,service,original = setup_scene()
    with pytest.raises(ValueError):
        execute_live_command(service,command("import_model",payload=p),LiveIdentities())
    assert not scene.groups and scene.mesh.faces == [original] and not history.undo_stack


@pytest.mark.parametrize("changes", [{"modelId":"other"},{"connectionId":"other"},{"baseRevision":0},
                                    {"expiresAt":0},{"action":"eval"},{"protocol":True}])
def test_command_scope_expiry_and_whitelist(changes):
    with pytest.raises(ValueError):
        validate_command(command(**changes),"model","connection",1)


def connected_session(snapshot):
    s = LiveSession()
    s.connect("http://localhost:1234","QA-CODE","QA",["demo-solids-v1"])
    request = s.next_request(lambda:snapshot)
    s.complete(request,200,{"token":"1"*64,"projectId":"project","connectionId":"connection","demoCommands":True})
    request = s.next_request(lambda:snapshot)
    s.complete(request,200,{"revision":1,"connectionId":"connection"})
    return s


def test_command_result_is_uploaded_before_ack_and_duplicate_is_not_executed_twice():
    current = {}
    s = connected_session(current)
    calls = []
    def execute(cmd):
        calls.append(cmd["id"])
        current["face:1"] = {"id":"face:1","value":1}
        return copy.deepcopy(current)
    poll = s.next_request(lambda:current,execute_command=execute)
    assert poll.route.endswith("/commands/next")
    incoming = command(modelId=s.model_id)
    s.complete(poll,200,{"revision":1,"command":incoming})
    assert s.next_request(lambda:current,execute_command=execute) is None
    assert calls == ["command-1"]
    batch = s.next_request(lambda:current,execute_command=execute)
    assert batch.route.endswith("/batch") and json.loads(batch.body)["commandId"] == "command-1"
    s.complete(batch,200,{"revision":2,"connectionId":"connection"})
    ack = s.next_request(lambda:current,execute_command=execute)
    assert ack.route.endswith("/commands/ack") and json.loads(ack.body)["resultRevision"] == 2
    first_ack = ack.body
    s.complete(ack,200,{"id":"command-1","status":"confirmed"})
    s.incoming = incoming
    assert s.next_request(lambda:current,execute_command=execute) is None
    repeated_ack = s.next_request(lambda:current,execute_command=execute)
    assert calls == ["command-1"] and repeated_ack.body == first_ack


def test_changed_local_snapshot_rejects_command_and_schedules_manual_delta():
    current = {}
    s = connected_session(current)
    s.incoming = command(modelId=s.model_id)
    current["new"] = {"id":"new"}
    s.execute_incoming(lambda:current,lambda _:pytest.fail("Stale command executed"))
    assert s.command_result["outcome"] == "rejected" and s.generation>s.sent_generation
    ack = s.next_request(lambda:current)
    assert ack.route.endswith("/commands/ack")
