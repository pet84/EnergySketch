# SPDX-License-Identifier: GPL-3.0-or-later
# © 2026 ArchEnergy s.r.o.
"""Real editable slice geometry: holes, placements, visibility and history."""
from types import SimpleNamespace

import pytest
from PySide6.QtGui import QMatrix4x4, QVector3D as V
from PySide6.QtWidgets import QMenu
from core.group import Group
from core.history import History
from core.mesh import Mesh
from core.scene import Scene
from core.section import SectionPlane
from plugins.archcontrol.adapter import PanelService, build_section_slice, section_slice_context_menu


def box(mesh):
    points = [V(x, y, z) for z in (0, 2) for y in (0, 2) for x in (0, 2)]
    for indices in ((0, 1, 3, 2), (4, 6, 7, 5), (0, 4, 5, 1),
                    (2, 3, 7, 6), (0, 2, 6, 4), (1, 5, 7, 3)):
        mesh.add_face([points[i] for i in indices])


def service(scene):
    history = History(scene)
    viewport = SimpleNamespace(history=history, notify_scene_changed=lambda: None, update=lambda: None)
    return PanelService(SimpleNamespace(scene=scene, window=None, viewport=viewport)), history


def plane(scene, point=(0, 0, 1), normal=(0, 0, 1)):
    value = SectionPlane(V(*point), V(*normal), symbol="A", active=False)
    scene.section_planes.append(value)
    scene.selection = {value}
    return value


@pytest.mark.parametrize("height", [0, 1, 2])
def test_box_and_coplanar_cap_make_four_edges_without_diagonals_or_faces(height):
    scene = Scene()
    box(scene.mesh)
    cut = plane(scene, (0, 0, height))
    state = scene.mesh.capture_state()
    group = build_section_slice(scene, cut)
    assert len(group.mesh.edges) == 4
    assert len(group.mesh.vertices) == 4 and not group.mesh.faces
    assert all(abs(v.position.z()-height) < 1e-6 for v in group.mesh.vertices)
    assert sum(e.length() for e in group.mesh.edges) == pytest.approx(8)
    assert scene.mesh.capture_state() == state and scene.groups == []
    assert not cut.active


def test_oblique_cut_through_vertices_closes_and_reverse_keeps_geometry():
    scene = Scene()
    box(scene.mesh)
    cut = plane(scene, (1, 1, 1), (1, 1, 1))
    one = build_section_slice(scene, cut)
    assert len(one.mesh.edges) == 6
    assert all(len(v.edges) == 2 for v in one.mesh.vertices)
    assert all(abs(cut.side(v.position)) < 1e-6 for v in one.mesh.vertices)
    cut.flip()
    two = build_section_slice(scene, cut)
    coords = lambda g: sorted(tuple(v.position.toTuple()) for v in g.mesh.vertices)
    assert coords(one) == coords(two)


def test_cut_keeps_gap_in_window_and_coplanar_face_keeps_hole_boundary():
    scene = Scene()
    scene.mesh.add_face([V(-2,0,0),V(2,0,0),V(2,0,4),V(-2,0,4)],
                        [[V(-.5,0,1),V(-.5,0,3),V(.5,0,3),V(.5,0,1)]])
    group = build_section_slice(scene, plane(scene, (0,0,2)))
    assert len(group.mesh.edges) == 2
    assert sum(e.length() for e in group.mesh.edges) == pytest.approx(3)
    assert all(e.a.x()*e.b.x() > 0 for e in group.mesh.edges)
    coplanar = build_section_slice(scene, plane(scene, (0,0,0), (0,1,0)))
    assert len(coplanar.mesh.edges) == 8 and not coplanar.mesh.faces


def test_nested_scaled_rotated_instances_and_hidden_ancestors_layers_faces():
    from core.layers import Layer
    scene = Scene()
    source = Mesh()
    box(source)
    child = Group(source, "Box")
    child.xform = QMatrix4x4()
    child.xform.scale(2, 3, 4)
    parent = Group(Mesh(), "Parent")
    parent.xform = QMatrix4x4()
    parent.xform.translate(10, 20, 1)
    parent.xform.rotate(30, 0, 0, 1)
    parent.children = [child]
    scene.groups = [parent]
    cut = plane(scene, (0,0,5))
    group = build_section_slice(scene, cut)
    assert len(group.mesh.edges) == 4
    assert sum(e.length() for e in group.mesh.edges) == pytest.approx(20, abs=1e-5)
    parent.hidden = True
    with pytest.raises(ValueError, match="neprotíná"):
        build_section_slice(scene, cut)
    parent.hidden = False
    scene.layers.append(Layer("Hidden", False))
    child.layer = "Hidden"
    with pytest.raises(ValueError, match="neprotíná"):
        build_section_slice(scene, cut)
    child.layer = None
    for face in source.faces:
        face.attrs["hidden"] = True
    with pytest.raises(ValueError, match="neprotíná"):
        build_section_slice(scene, cut)


def test_insert_undo_redo_and_igz_preserve_editable_group_and_original_model(tmp_path):
    from formats.igz import load_into, save_scene
    scene = Scene()
    box(scene.mesh)
    cut = plane(scene)
    state = scene.mesh.capture_state()
    api, history = service(scene)
    group = api.create_section_slice(cut)
    assert scene.selection == {group} and scene.groups == [group]
    assert scene.mesh.capture_state() == state
    assert history.undo() and scene.groups == [] and scene.selection == {cut}
    assert history.redo() and scene.groups == [group] and scene.selection == {group}
    assert len(group.mesh.edges) == 4 and scene.mesh.capture_state() == state
    path = tmp_path / "slice.igz"
    save_scene(scene, path)
    loaded = Scene()
    load_into(loaded, path)
    restored = loaded.groups[0]
    assert len(restored.mesh.edges) == 4 and not restored.mesh.faces
    assert restored.uid == group.uid
    assert restored.ext["archcontrol"]["section_slice"]["source_plane_uid"] == cut.uid


def test_empty_or_stale_slice_adds_no_history_and_menu_targets_only_plane():
    scene = Scene()
    box(scene.mesh)
    cut = plane(scene, (0,0,10))
    api, history = service(scene)
    with pytest.raises(ValueError, match="neprotíná"):
        api.create_section_slice(cut)
    assert not history.undo_stack and scene.selection == {cut}
    menu = QMenu()
    section_slice_context_menu(api, menu, [])
    assert not menu.actions()
    section_slice_context_menu(api, menu, [cut])
    assert menu.actions()[0].text() == "Vytvořit skupinu z průřezu"
    scene.section_planes.clear()
    with pytest.raises(ValueError, match="není v dokumentu"):
        api.create_section_slice(cut)
    assert not history.undo_stack


def test_slice_in_plain_edit_context_stays_in_parent_and_undo_is_atomic():
    scene = Scene()
    context = Group(Mesh(), "Edited")
    box(context.mesh)
    scene.groups = [context]
    scene.begin_group_edit(context)
    cut = plane(scene)
    api, history = service(scene)
    group = api.create_section_slice(cut)
    assert context.children == [group] and scene.groups == [context]
    assert history.undo() and context.children == []
    assert history.redo() and context.children == [group]
    scene.end_group_edit()
    assert len(context.mesh.faces) == 6


def test_tangent_touch_is_not_a_fake_segment():
    from plugins.archcontrol.section_slice import triangle_segment
    assert triangle_segment(((0,0,0),(1,0,1),(0,1,1)), (0,0,0), (0,0,1)) is None
    assert triangle_segment(((0,0,0),(1,0,0),(0,1,1)), (0,0,0), (0,0,1)) == ((0,0,0),(1,0,0))


def test_shared_component_edit_is_refused_before_any_mutation():
    scene = Scene()
    component = Group(Mesh(), "Shared")
    component.component = True
    component.xform = QMatrix4x4()
    box(component.mesh)
    scene.groups = [component]
    scene.begin_group_edit(component)
    cut = plane(scene)
    api, history = service(scene)
    with pytest.raises(ValueError, match="ukončete úpravy komponenty"):
        api.create_section_slice(cut)
    assert not history.undo_stack and not component.children
    scene.end_group_edit()
