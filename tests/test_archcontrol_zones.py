# SPDX-License-Identifier: GPL-3.0-or-later
# © 2026 ArchEnergy s.r.o.
from types import SimpleNamespace
import copy
import pytest
from PySide6.QtGui import QMatrix4x4, QVector3D
from core.group import Group
from core.mesh import Mesh
from core.scene import Scene
from core.history import History
from plugins.archcontrol.adapter import PanelService, component_records, face_records
from plugins.archcontrol.zones import zone_report, component_palette


def cube(name="Zóna 1"):
    mesh = Mesh()
    for points in (
        [(0, 0, 0), (0, 1, 0), (1, 1, 0), (1, 0, 0)],
        [(0, 0, 1), (1, 0, 1), (1, 1, 1), (0, 1, 1)],
        [(0, 0, 0), (1, 0, 0), (1, 0, 1), (0, 0, 1)],
        [(1, 0, 0), (1, 1, 0), (1, 1, 1), (1, 0, 1)],
        [(1, 1, 0), (0, 1, 0), (0, 1, 1), (1, 1, 1)],
        [(0, 1, 0), (0, 0, 0), (0, 0, 1), (0, 1, 1)],
    ):
        mesh.add_face([QVector3D(*p) for p in points]).attrs["mat"] = "SO-1-V1-Stěna"
    group = Group(mesh, name=name)
    group.xform = QMatrix4x4()
    return group


def service_for(scene):
    history = History(scene)
    app = SimpleNamespace(window=None, scene=scene,
                          document_data=lambda **_: copy.deepcopy(scene.plugin_data.get("archcontrol", {})),
                          viewport=SimpleNamespace(history=history, end_group_edit=scene.end_group_edit,
                                                   begin_group_edit=scene.begin_group_edit,
                                                   notify_scene_changed=lambda: None, update=lambda: None))
    return PanelService(app), history


def test_closed_volume_scale_mirror_and_open_shell():
    scene = Scene()
    a, b, c = cube(), cube("Zóna 2"), cube("Zóna 3")
    b.xform.scale(-2, 3, 4)
    c.mesh.remove_face(c.mesh.faces[0])
    scene.groups = [a, b, c]
    rows = list(component_records(scene))
    assert [row["volume"] for row in rows] == pytest.approx([1., 24., 0.])
    assert [row["solid"] for row in rows] == [True, True, False]


def test_mixed_face_winding_and_cavity_do_not_corrupt_volume_or_model():
    from plugins.archcontrol.zones import solid_volume_triangles
    from plugins.archcontrol.adapter import component_volume
    outer = cube()
    triangles = [tuple((p.x(), p.y(), p.z()) for p in tri)
                 for face in outer.mesh.faces for tri in face.triangulate()]
    mixed = [tri[::-1] if i % 3 == 0 else tri for i, tri in enumerate(triangles)]
    assert solid_volume_triangles(mixed) == pytest.approx(1.)
    inner = [tuple(tuple(.25 + v * .5 for v in p) for p in tri) for tri in triangles]
    assert solid_volume_triangles([*mixed, *inner]) == pytest.approx(.875)
    before = outer.mesh.capture_state()
    assert component_volume(outer) == pytest.approx(1.)
    assert outer.mesh.capture_state() == before


def test_collinear_polygon_vertices_omitted_by_one_triangulation_still_close():
    from plugins.archcontrol.zones import solid_volume_faces
    group = cube()
    point = lambda p: (p.x(), p.y(), p.z())
    faces = [{"loops": [[point(p) for p in face.vertices]],
              "triangles": [tuple(point(p) for p in tri) for tri in face.triangulate()]}
             for face in group.mesh.faces]
    a, b = faces[0]["loops"][0][:2]
    middle = tuple((x+y)/2 for x, y in zip(a, b))
    for face in faces:
        ring = face["loops"][0]
        for i, (first, second) in enumerate(zip(ring, [*ring[1:], ring[0]])):
            if {first, second} == {a, b}:
                ring.insert(i+1, middle)
                break
    for i, tri in enumerate(faces[0]["triangles"]):
        for j in range(3):
            first, second, third = tri[j], tri[(j+1)%3], tri[(j+2)%3]
            if {first, second} == {a, b}:
                faces[0]["triangles"][i:i+1] = [(first, middle, third), (middle, second, third)]
                break
        else:
            continue
        break
    assert solid_volume_faces(faces) == pytest.approx(1.)


def test_zone_report_preserves_ruby_ab_subtraction_and_numeric_order():
    components = [{"report_visible": True, "report_zone": "Zóna 10", "raw_volume": 1.2345},
                  {"report_visible": True, "report_zone": "Zóna 2", "raw_volume": 2.}]
    reports = {"envelope": {"Zóna 10": 6.005, "Zóna 2": 5.}, "ab": {"Zóna 2": 2.}}
    rows = zone_report(reports, components)
    assert [row["zoneNumber"] for row in rows] == ["2", "10"]
    assert rows[0]["m2"] == 5.
    assert rows[0]["m2net"] == 3.
    assert rows[1]["m3"] == 1.235
    assert rows[1]["m2"] == 6.01


def test_palette_and_report_intentionally_differ_for_hidden_component():
    scene = Scene()
    group = cube()
    scene.groups = [group]
    service, history = service_for(scene)
    assert service.zones()[0]["m2"] == 6.
    assert service.zones()[0]["volume"] == 1.
    service.toggle_component_hidden(group.uid)
    rows = service.zones()
    assert len(rows) == 1 and rows[0]["hidden"] is True
    assert rows[0]["volume"] == 1.
    assert rows[0]["m2"] == 0.
    assert history.undo()
    assert service.zones()[0]["m2"] == 6.
    assert history.redo()
    assert service.zones()[0]["hidden"] is True


def test_parent_scale_is_not_applied_to_child_volume_like_ruby_e_volume():
    scene = Scene()
    child = cube("Vnitřní komponenta")
    parent = Group(Mesh(), name="Pouhá skupina")
    parent.component = False
    parent.xform = QMatrix4x4()
    parent.xform.scale(10)
    parent.children = [child]
    scene.groups = [parent]
    rows = list(component_records(scene))
    assert len(rows) == 1
    assert rows[0]["volume"] == 1.  # source doesn't use accumulated parent transform
    assert rows[0]["zone"] == "Vnitřní komponenta"
    assert rows[0]["report_zone"] == "(model)"  # source report's group sentinel
    assert next(face_records(scene)).zone == "Vnitřní komponenta"
    service, history = service_for(scene)
    assert service.zones()[0]["m2"] == 600.
    service.select_component(child.uid)
    assert scene.edit_group is parent
    assert scene.selection == {child}


def test_native_classic_group_does_not_create_a_zone():
    scene = Scene()
    group = cube("Skupina")
    group.xform = None
    scene.groups = [group]
    assert not list(component_records(scene))
    assert next(face_records(scene)).zone == "(model)"


def test_zone_palette_filter_numeric_cells_and_clipboard():
    from PySide6.QtWidgets import QApplication
    from plugins.archcontrol.zones_ui import ZonePalette
    scene = Scene()
    scene.groups = [cube("Zóna 10"), cube("Zóna 2")]
    service, history = service_for(scene)
    panel = ZonePalette(service)
    assert panel.table.rowCount() == 2
    panel.filter.setText("Zóna 2")
    assert panel.table.rowCount() == 1
    assert panel.table.item(0, 3).data(0) == 1.
    panel.copy()
    assert "Zóna 2" in QApplication.clipboard().text()
