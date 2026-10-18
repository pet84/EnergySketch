# SPDX-License-Identifier: GPL-3.0-or-later
# © 2026 ArchEnergy s.r.o.
"""Critical import regressions; no access to the user's source models."""
import pytest
from PySide6.QtGui import QVector3D
from openskp.model import Definition, Edge, Face, Instance, Material, SkpModel, Vertex

from plugins.archcontrol.adapter import adapt_model


def square():
    d = Definition(id=1, name="Definice")
    d.vertices = {i: Vertex(i, *point) for i, point in enumerate(
        [(0, 0, 0), (40, 0, 0), (40, 40, 0), (0, 40, 0)], 1)}
    d.edges = {i: Edge(i, i, i % 4 + 1) for i in range(1, 5)}
    d.faces = {20: Face(20, [[(i, 1) for i in range(1, 5)]],
                       normal=(0, 0, 1), material_id=7, back_material_id=8)}
    return d


def model():
    m = SkpModel()
    m.root = Definition(0, name="ROOT")
    m.definitions = {1: square()}
    a = Material("SO-1-U0.3-Stěna", id=7)
    b = Material("EP-1", id=8)
    m.materials = [a, b]
    m.materials_by_id = {7: a, 8: b}
    return m


def instance(name, offset=0):
    return Instance(name=name, ref_idx=1,
                    matrix=[1, 0, 0, 0, 1, 0, 0, 0, 1, offset, 0, 0, 1],
                    attribute_dictionaries={"ArchControl_AIRIS": {"zone_id": name}})


def test_names_are_per_instance_and_survive_igz(tmp_path):
    from core.scene import Scene
    from formats.igz import load_into, save_scene
    m = model()
    m.root.instances = [instance("Zóna A"), instance("Zóna B", 100)]
    scene = adapt_model(m, tmp_path / "source.skp")
    assert [g.name for g in scene.groups] == ["Zóna A", "Zóna B"]
    assert scene.groups[0].mesh is scene.groups[1].mesh
    assert scene.groups[1].xform.map(QVector3D()).x() == pytest.approx(2.54)
    assert scene.plugin_data["archcontrol"]["north_angle"] is None
    p = tmp_path / "model.igz"
    save_scene(scene, p)
    loaded = Scene()
    load_into(loaded, p)
    assert [g.name for g in loaded.groups] == ["Zóna A", "Zóna B"]
    assert loaded.groups[1].ext["archcontrol"]["attribute_dictionaries"] == {
        "ArchControl_AIRIS": {"zone_id": "Zóna B"}}
    assert loaded.plugin_data == scene.plugin_data


def test_front_normal_with_collinear_leading_vertices(tmp_path):
    m = model()
    d = m.definitions[1]
    points = [(0,0,0),(20,0,0),(40,0,0),(40,40,0),(0,40,0)]
    d.vertices = {i:Vertex(i,*p) for i,p in enumerate(points,1)}
    d.edges = {i:Edge(i,i,i%5+1) for i in range(1,6)}
    d.faces = {20:Face(20,[[(i,1) for i in range(1,6)]],normal=(0,0,-1),material_id=7)}
    m.root.instances = [instance("Zóna")]
    scene = adapt_model(m,tmp_path / "collinear.skp")
    assert scene.groups[0].mesh.faces[0].normal().z() < -.99


def test_nested_names_transforms_and_sidedness(tmp_path):
    m = model()
    parent = Definition(2, name="Kontejner")
    parent.instances = [instance("Vnitřní zóna", 100)]
    m.definitions[2] = parent
    outer = instance("Vnější skupina", 200)
    outer.ref_idx = 2
    m.root.instances = [outer]
    scene = adapt_model(m, tmp_path / "source.skp")
    g = scene.groups[0]
    assert g.name == "Vnější skupina"
    assert g.children[0].name == "Vnitřní zóna"
    xf = g.xform * g.children[0].xform
    assert xf.map(QVector3D()).x() == pytest.approx(7.62)
    face = g.children[0].mesh.faces[0]
    assert face.attrs["mat"] == "SO-1-U0.3-Stěna"
    assert face.attrs["back"]["mat"] == "EP-1"
    assert face.normal().z() > 0


def test_missing_definition_and_cycles_fail_before_scene_mutation(tmp_path):
    m = model()
    m.root.instances = [instance("A")]
    m.definitions[1].instances = [instance("Smyčka")]
    with pytest.raises(ValueError, match="Cyklická"):
        adapt_model(m, tmp_path / "source.skp")
    m.definitions = {}
    with pytest.raises(ValueError, match="Chybí definice"):
        adapt_model(m, tmp_path / "source.skp")


def test_back_only_does_not_become_front(tmp_path):
    m = model()
    m.definitions[1].faces[20].material_id = None
    m.root.instances = [instance("Zóna")]
    face = adapt_model(m, tmp_path / "source.skp").groups[0].mesh.faces[0]
    assert "mat" not in face.attrs
    assert face.attrs["back"]["mat"] == "EP-1"
    assert face.normal().z() > 0


def test_records_use_current_transformed_geometry_and_keep_hidden(tmp_path):
    from plugins.archcontrol.adapter import face_records
    from plugins.archcontrol.core import triangulated_area
    m = model()
    m.root.instances = [instance("Zóna")]
    scene = adapt_model(m, tmp_path / "source.skp")
    group = scene.groups[0]
    group.xform.scale(2, 3, 1)
    group.hidden = True
    rows = list(face_records(scene))
    assert len(rows) == 1
    assert triangulated_area(rows[0].triangles) == pytest.approx((40 * .0254) ** 2 * 6, abs=1e-5)
    assert rows[0].zone == "Zóna"
    assert rows[0].parent_name == "Definice"
    assert rows[0].visible is False
    assert rows[0].back_material == "EP-1"


def test_identity_keeps_whitespace_and_unplaced_materials(tmp_path):
    m = model()
    m.root.instances = [instance(" Zóna A ")]
    m.materials_by_id[7].name = " SO-1-U0.3-Stěna "
    m.materials.append(Material("Nepoužitý materiál"))
    scene = adapt_model(m, tmp_path / "source.skp")
    assert scene.groups[0].name == " Zóna A "
    assert " SO-1-U0.3-Stěna " in scene.materials
    assert "Nepoužitý materiál" in scene.materials
    assert scene.groups[0].mesh.faces[0].attrs["mat"] == " SO-1-U0.3-Stěna "


def test_history_restores_materials_layers_and_document_data(tmp_path):
    from core.scene import Scene
    from core.history import History
    from core.materials import Material as NativeMaterial
    from plugins.archcontrol.adapter import ImportCommand
    m = model()
    m.root.instances = [instance("Zóna A")]
    imported = adapt_model(m, tmp_path / "source.skp")
    scene = Scene()
    scene.plugin_data = {"unrelated": {"x": [1]}}
    original_material = NativeMaterial("Starý nepoužitý", (.1, .2, .3))
    scene.materials[original_material.name] = original_material
    old_layer = scene.layers[0]
    history = History(scene)
    history.execute(ImportCommand(imported))
    assert history.last_error is None
    assert len(scene.groups) == 1
    assert scene.plugin_data["unrelated"] == {"x": [1]}
    assert "archcontrol" in scene.plugin_data
    assert history.undo()
    assert scene.groups == []
    assert scene.layers == [old_layer]
    assert scene.materials == {original_material.name: original_material}
    assert scene.plugin_data == {"unrelated": {"x": [1]}}
    assert history.redo()
    assert scene.groups[0].name == "Zóna A"
    assert "archcontrol" in scene.plugin_data


def test_group_is_not_the_zone_and_material_rp_reaches_record(tmp_path):
    from plugins.archcontrol.adapter import face_records
    m = model()
    parent = Definition(2, name="Skupina")
    parent.instances = [instance("Skutečná zóna")]
    m.definitions[2] = parent
    outer = instance("Pouhá skupina")
    outer.ref_idx = 2
    m.root.instances = [outer]
    metadata = {"entities": {0: ["group"], 2: ["component"]},
                "material_dictionaries": {"SO-1-U0.3-Stěna": {"ArchControl_RP": {
                    "kategorie": "steny", "typ": "Stěna vnější", "etapa": "3. Etapa"}}}}
    scene = adapt_model(m, tmp_path / "source.skp", metadata=metadata)
    record, = face_records(scene)
    assert record.zone == "Skutečná zóna"
    assert record.rp[:3] == ("steny", "Stěna vnější", "3. Etapa")


def precise_window_model(area):
    m = model()
    width, height = area / .5, .5
    x, y = 8.1234, 13.4567
    points = [(x, y, 0), (x + width, y, 0),
              (x + width, y + height, 0), (x, y + height, 0)]
    m.definitions[1].vertices = {i: Vertex(i, *(v / .0254 for v in p))
                                for i, p in enumerate(points, 1)}
    m.definitions[1].faces[20].back_material_id = None
    m.materials_by_id[7].name = "OD-1-U0.9"
    m.root.instances = [instance("Zóna 1")]
    return m


@pytest.mark.parametrize("area,formatted", [(.3750000001, "0.38"), (1.1250000001, "1.13")])
@pytest.mark.parametrize("binary", [False, True])
def test_source_double_precision_controls_per_face_rounding_and_survives_paint_igz(tmp_path, monkeypatch, area, formatted, binary):
    from core.scene import Scene
    from formats.igz import load_into, save_scene
    if binary:
        monkeypatch.setattr("formats.igz._BULK_MIN", 0)
        monkeypatch.setattr("formats.igz._LARGE_DOCUMENT", 0)
    from plugins.archcontrol.adapter import face_records
    from plugins.archcontrol.core import collect_rows, face_area_m2
    scene = adapt_model(precise_window_model(area), tmp_path / "source.skp")
    face = scene.groups[0].mesh.faces[0]
    face.attrs["color"] = (.2, .3, .4)  # painting must retain source geometry
    record, = face_records(scene)
    assert record.source_triangles_inches is not None
    assert face_area_m2(record) == pytest.approx(area, abs=1e-13)
    assert collect_rows([record], 0)["rows"][0][10] == formatted
    path = tmp_path / "precise.igz"
    save_scene(scene, path)
    loaded = Scene()
    load_into(loaded, path)
    restored, = face_records(loaded)
    assert face_area_m2(restored) == face_area_m2(record)
    assert restored.source_local_triangles_inches == record.source_local_triangles_inches


def test_igz_extension_data_cannot_override_material_and_is_independently_copied():
    from formats.igz import _face_attrs_from_json
    raw = {"mat": "SO-1", "ext": {"mat": "EVIL", "archcontrol": {"ids": [1, 2]}}}
    attrs = _face_attrs_from_json(raw)
    assert attrs["mat"] == "SO-1"
    attrs["archcontrol"]["ids"].append(3)
    assert raw["ext"]["archcontrol"]["ids"] == [1, 2]


def test_vertex_edit_invalidates_source_precision_and_undo_recovers_it(tmp_path):
    from core.history import History
    from plugins.archcontrol.adapter import LiveMutationCommand, face_records
    from plugins.archcontrol.core import face_area_m2, triangulated_area
    scene = adapt_model(precise_window_model(.3750000001), tmp_path / "source.skp")
    group = scene.groups[0]
    face = group.mesh.faces[0]
    before, = face_records(scene)
    history = History(scene)

    def edit(_):
        right = max(vertex.position.x() for vertex in face.loop)
        for vertex in face.loop:
            if vertex.position.x() == right:
                group.mesh.move_vertex(vertex, QVector3D(.25, 0, 0))

    history.execute(LiveMutationCommand(edit))
    assert history.last_error is None
    changed, = face_records(scene)
    assert changed.source_local_triangles_inches is None
    assert face_area_m2(changed) == pytest.approx(triangulated_area(changed.triangles), abs=1e-12)
    assert face_area_m2(changed) == pytest.approx(.5, abs=1e-6)
    assert history.undo()
    restored, = face_records(scene)
    assert restored.source_local_triangles_inches is not None
    assert face_area_m2(restored) == face_area_m2(before)


def test_nested_source_matrices_and_changed_scale_use_live_geometry(tmp_path):
    from plugins.archcontrol.adapter import face_records
    from plugins.archcontrol.core import face_area_m2
    m = precise_window_model(.3750000001)
    # Rotation about Z with nonuniform scale; native normal follows Ruby.
    inner = m.root.instances[0]
    inner.matrix = [0, -3, 0, 2, 0, 0, 0, 0, 1, 200.123456789, 0, 0, 1]
    parent = Definition(2, name="Parent", instances=[inner])
    m.definitions[2] = parent
    outer = instance("Outer", 100.123456789)
    outer.ref_idx = 2
    m.root.instances = [outer]
    scene = adapt_model(m, tmp_path / "source.skp")
    record, = face_records(scene)
    assert face_area_m2(record) == pytest.approx(.3750000001 * 6, abs=1e-12)
    assert face_area_m2(record, local=True) == pytest.approx(.3750000001, abs=1e-13)
    scene.groups[0].xform.scale(2)
    scaled, = face_records(scene)
    assert face_area_m2(scaled) == pytest.approx(face_area_m2(record) * 4, abs=1e-12)
    assert face_area_m2(scaled, local=True) == face_area_m2(record, local=True)
