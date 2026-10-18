# SPDX-License-Identifier: GPL-3.0-or-later
# © 2026 ArchEnergy s.r.o.
"""Local Ruby grid rules and native topology/history across placements."""
from types import SimpleNamespace
import copy
import pytest
from PySide6.QtGui import QVector3D as V, QMatrix4x4
from core.group import Group
from core.history import History
from core.materials import Material
from core.scene import Scene
from plugins.archcontrol.adapter import PanelService, face_handles, face_records
from plugins.archcontrol.core import triangulated_area
from plugins.archcontrol.windows import Grid, window_material

MAT = "OD-1-V1-U1.2-G0.5-S3-Okno"
WALL = "SO-1-V1-U0.3-Stěna"


def setup_scene(component=False):
    scene = Scene()
    mesh = scene.mesh
    if component:
        group = Group(name="Zóna 1")
        group.xform = QMatrix4x4()
        group.xform.translate(10, 20, 3)
        group.xform.rotate(45, 0, 0, 1)
        group.xform.scale(2, 1, 1)
        group.component = True
        scene.groups = [group]
        mesh = group.mesh
    face = mesh.add_face([V(-5, 0, 0), V(5, 0, 0), V(5, 0, 5), V(-5, 0, 5)])
    face.attrs.update(mat=WALL, archcontrol={"source_face_id": 12})
    scene.materials = {MAT: Material(MAT, (.2,.4,.6)), WALL: Material(WALL, (.8,.8,.8))}
    history = History(scene)
    viewport = SimpleNamespace(history=history, notify_scene_changed=lambda: None,
                               update=lambda: None, begin_group_edit=scene.begin_group_edit,
                               end_group_edit=scene.end_group_edit)
    service = PanelService(SimpleNamespace(scene=scene, viewport=viewport, window=None))
    return scene, history, service, next(face_handles(scene))[0]


def test_grid_local_axes_center_count_and_horizontal_faces():
    grid = Grid(cols=2, rows=2, width=1, height=2, gap_h=3, gap_v=4)
    assert grid.size == (5, 8)
    rects = grid.rectangles((10,0,20), (0,-1,0))
    assert len(rects) == 4
    assert rects[0] == ((12.5,0.,16.),(11.5,0.,16.),(11.5,0.,18.),(12.5,0.,18.))
    assert Grid().rectangles((0,0,1), (0,0,-1))[0] == ((-.5,-.5,1),(.5,-.5,1),(.5,.5,1),(-.5,.5,1))


@pytest.mark.parametrize("kwargs", [{"rows":0},{"cols":51},{"cols":1.5},
                                    {"width":0},{"height":float('nan')},{"gap_h":float('inf')}])
def test_invalid_grid_cannot_reach_geometry(kwargs):
    with pytest.raises(ValueError):
        Grid(**kwargs)


def test_window_material_filter_is_the_ruby_list():
    assert all(window_material(t+"-1") for t in ("OD","OS","ODN","ODZ","OX"))
    assert window_material("OD") and not window_material("ODD-1")
    assert not window_material("SO-1")


def totals(scene):
    result = {}
    for rec in face_records(scene):
        result[rec.material] = result.get(rec.material, 0) + triangulated_area(rec.triangles)
    return result


def test_grid_partitions_wall_both_sides_and_undo_restores_exact_face():
    scene, history, service, pid = setup_scene()
    original = scene.mesh.faces[0]
    before = scene.mesh.capture_state()
    grid = Grid(cols=2, width=1, height=2, gap_h=1, material=MAT)
    assert service.insert_window_grid(pid, (0,0,2.5), grid) == 2
    area = totals(scene)
    assert area[MAT] == pytest.approx(4, abs=1e-5)
    assert area[WALL] == pytest.approx(46, abs=1e-5)
    windows = [f for f in scene.mesh.faces if f.attrs.get("mat") == MAT]
    assert all(f.attrs.get("back") is True for f in windows)
    assert len({p for p,_,_ in face_handles(scene)}) == len(scene.mesh.faces)
    assert len(history.undo_stack) == 1
    assert history.undo()
    assert scene.mesh.faces == [original]
    assert scene.mesh.capture_state()["fattrs"] == before["fattrs"]
    assert history.redo()
    assert totals(scene)[MAT] == pytest.approx(4, abs=1e-5)


def test_rotated_scaled_component_uses_local_sizes_and_keeps_shared_definition():
    scene, history, service, pid = setup_scene(component=True)
    group = scene.groups[0]
    proto = group.mesh
    matrix = QMatrix4x4(group.xform)
    center = matrix.map(V(0,0,2.5))
    point = (center.x(),center.y(),center.z())
    grid = Grid(width=1,height=2,material=MAT)
    corners = service.window_geometry(pid, point, grid)
    assert (corners[0][1]-corners[0][0]).length() == pytest.approx(2, abs=1e-5)
    service.insert_window_grid(pid, point, grid)
    assert totals(scene)[MAT] == pytest.approx(4, abs=1e-4)
    scene.end_group_edit()
    assert group.mesh is proto
    assert group.xform == matrix
    assert totals(scene)[MAT] == pytest.approx(4, abs=1e-4)


def test_stale_face_and_removed_material_do_not_change_geometry_or_history():
    scene, history, service, pid = setup_scene()
    before = scene.mesh.capture_state()
    with pytest.raises(ValueError, match="neexistuje"):
        service.insert_window_grid("missing", (0,0,2), Grid(material=MAT))
    with pytest.raises(ValueError, match="materiál"):
        service.insert_window_grid(pid, (0,0,2), Grid(material="OD-gone"))
    assert not history.undo_stack
    assert scene.mesh.capture_state() == before


def test_preview_stays_the_same_after_entering_a_scaled_component():
    scene, history, service, pid = setup_scene(component=True)
    point = scene.groups[0].xform.map(V(0,0,2.5))
    point = (point.x(),point.y(),point.z())
    grid = Grid(cols=2,width=.8,height=1.5,material=MAT)
    before = service.window_geometry(pid, point, grid)
    service.select_faces([pid])
    after = service.window_geometry(pid, point, grid)
    assert max((a-b).length() for ar,br in zip(before,after) for a,b in zip(ar,br)) < 1e-5


def test_sibling_component_receives_the_same_local_window_after_share_back():
    scene, history, service, pid = setup_scene(component=True)
    first = scene.groups[0]
    second = Group(first.mesh, name="Zóna 2")
    second.component = True
    second.xform = QMatrix4x4()
    second.xform.translate(50,0,0)
    scene.groups.append(second)
    point = first.xform.map(V(0,0,2.5))
    service.insert_window_grid(pid, (point.x(),point.y(),point.z()), Grid(width=1,height=2,material=MAT))
    scene.end_group_edit()
    assert first.mesh is second.mesh
    areas = sorted(triangulated_area(r.triangles) for r in face_records(scene) if r.material == MAT)
    assert areas == pytest.approx([2,4], abs=1e-4)


def test_nested_rotated_container_keeps_window_world_position():
    scene, history, service, _ = setup_scene(component=True)
    child = scene.groups[0]
    parent = Group(name="Patro")
    parent.component = True
    parent.xform = QMatrix4x4()
    parent.xform.translate(5,-2,7)
    parent.xform.rotate(30,0,0,1)
    parent.children = [child]
    scene.groups = [parent]
    pid = next(face_handles(scene))[0]
    matrix = parent.xform * child.xform
    center = matrix.map(V(0,0,2.5))
    point = (center.x(),center.y(),center.z())
    before = service.window_geometry(pid, point, Grid(material=MAT))
    service.insert_window_grid(pid, point, Grid(material=MAT))
    windows = [r for r in face_records(scene) if r.material == MAT]
    assert len(windows) == 1
    assert triangulated_area(windows[0].triangles) == pytest.approx(2, abs=1e-4)
    verts = {tuple(round(c,4) for c in p) for tri in windows[0].triangles for p in tri}
    expected = {(round(v.x(),4),round(v.y(),4),round(v.z(),4)) for v in before[0]}
    assert verts == expected


def test_native_viewport_share_back_is_one_undoable_grid(monkeypatch):
    from views.main_window import MainWindow
    from views.extension_api import ExtensionApp
    scene, history, _service, pid = setup_scene(component=True)
    window = MainWindow(defer_extensions=True)
    viewport = window.viewport
    viewport.scene, viewport.history = scene, history
    service = PanelService(ExtensionApp(window, "archcontrol"))
    group = scene.groups[0]
    proto = group.mesh
    center = group.xform.map(V(0,0,2.5))
    try:
        service.insert_window_grid(pid, (center.x(),center.y(),center.z()), Grid(material=MAT))
        viewport.end_group_edit()
        assert group.mesh is proto
        assert len(history.undo_stack) == 1
        assert totals(scene)[MAT] == pytest.approx(2, abs=1e-4)
        assert history.undo()
        assert MAT not in totals(scene)
        assert totals(scene)[WALL] == pytest.approx(100, abs=1e-4)
        assert history.redo()
        assert totals(scene)[MAT] == pytest.approx(2, abs=1e-4)
    finally:
        window._saved_version = scene.version
        window.close()


def test_locked_component_refuses_grid_without_modifying_mesh():
    from views.main_window import MainWindow
    from views.extension_api import ExtensionApp
    scene, history, _service, pid = setup_scene(component=True)
    scene.groups[0].locked = True
    before = scene.groups[0].mesh.capture_state()
    window = MainWindow(defer_extensions=True)
    window.viewport.scene, window.viewport.history = scene, history
    service = PanelService(ExtensionApp(window, "archcontrol"))
    try:
        with pytest.raises(ValueError, match="uzamčení"):
            service.insert_window_grid(pid, (10,20,5), Grid(material=MAT))
        assert not history.undo_stack
        assert scene.groups[0].mesh.capture_state() == before
    finally:
        window._saved_version = scene.version
        window.close()


def test_window_on_closed_box_preserves_other_planes_and_solid_volume():
    from plugins.archcontrol.live_commands import solid_rings
    from plugins.archcontrol.adapter import component_volume
    scene,history,service,_ = setup_scene(component=True)
    group = scene.groups[0]
    group.xform = QMatrix4x4()
    group.mesh.clear()
    for i,ring in enumerate(solid_rings("box",[0,0,0],[5000,5000,3000])):
        face = group.mesh.add_face([V(*(v/1000 for v in p)) for p in ring])
        face.attrs.update(mat=WALL,archcontrol={"source_face_id":100+i})
    pid = list(face_handles(scene))[2][0]
    service.insert_window_grid(pid,(2.5,0,1.5),Grid(material=MAT))
    areas = totals(scene)
    assert areas[MAT] == pytest.approx(1,abs=1e-5)
    assert areas[WALL] == pytest.approx(109,abs=1e-5)
    assert component_volume(group) == pytest.approx(75,abs=1e-4)
    scene.end_group_edit()
    assert component_volume(group) == pytest.approx(75,abs=1e-4)
