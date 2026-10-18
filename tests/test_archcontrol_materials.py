# SPDX-License-Identifier: GPL-3.0-or-later
# © 2026 ArchEnergy s.r.o.
import copy
import json
from types import SimpleNamespace

import pytest
from PySide6.QtGui import QMatrix4x4, QVector3D
from core.group import Group
from core.history import History
from core.materials import Material
from core.mesh import Mesh
from core.scene import Scene
from plugins.archcontrol.adapter import PanelService, face_handles
from plugins.archcontrol.materials import build_name, next_free_number, validate_identity


OLD = "SO-1-V1-U0.3-Stěna"
BACK = "EP-1-zóna 1"


def setup_scene():
    scene = Scene()
    mesh = Mesh()
    face = mesh.add_face([QVector3D(0, 0, 0), QVector3D(1, 0, 0), QVector3D(0, 1, 0)])
    face.attrs.update(mat=OLD, color=(.4, .5, .6), back={"mat": BACK, "color": (.1, .2, .3)},
                      archcontrol={"source_face_id": 42})
    a, b = Group(mesh, name="Zóna A"), Group(mesh, name="Zóna B")
    b.xform = QMatrix4x4()
    b.xform.scale(2)
    scene.groups = [a, b]
    scene.materials = {OLD: Material(OLD, (.4, .5, .6)), BACK: Material(BACK, (.1, .2, .3))}
    scene.plugin_data = {"unrelated": {"value": 1}, "archcontrol": {
        "north_angle": 0, "material_dictionaries": {OLD: {
            "Other": {"x": 2}, "ArchControl_RP": {"etapa": "2. Etapa"}}}}}
    history = History(scene)
    app = SimpleNamespace(window=None, scene=scene,
                          viewport=SimpleNamespace(history=history, notify_scene_changed=lambda: None, update=lambda: None,
                                                   begin_group_edit=scene.begin_group_edit, end_group_edit=scene.end_group_edit),
                          document_data=lambda **_: copy.deepcopy(scene.plugin_data.get("archcontrol", {})))
    return scene, history, PanelService(app), face


def draft(**changes):
    return {"typ": "SO", "cislo": "2", "var": "V2", "u": "0,25", "g": "",
            "sklo": "", "popis": "Nová stěna", "color": "#ff3300", "apply": False,
            "rp": {"kategorie": "steny", "typ": "Stěna vnější", "etapa": "3. Etapa",
                   "klient": "Ano", "lze_zateplit": "Ano"}, **changes}


def test_names_report_ab_glazing_and_construction_identity():
    assert build_name(draft(typ="OD", g="0,63", sklo="S3")) == "OD-2-V2-U0.25-G0.63-S3-Nová stěna"
    assert build_name(draft(typ="EP")) == "EP-2-Nová stěna"
    assert build_name(draft(typ="AB")) == "AB-2-Nová stěna"
    assert next_free_number(["SO-1-V1-a", "SO-3-V1-b", "OD-2-V1-c"], "SO") == 2
    assert build_name(draft(popis="")) == "SO-2-V2-U0.25"
    assert build_name(draft(typ="EP",popis="")) == "EP-2-zona 2"
    assert build_name(draft(typ="AB",popis="")) == "AB-2"
    with pytest.raises(ValueError, match="Stejný typ"):
        validate_identity(["SO-02-V2-Starý"],build_name(draft()))
    with pytest.raises(ValueError, match="Stejný typ"):
        validate_identity(["SO-2-V2-U0.8-Jiná"], build_name(draft()))
    with pytest.raises(ValueError, match="už existuje"):
        validate_identity([OLD], OLD)


@pytest.mark.parametrize("changes", [{"u": "nan"}, {"g": "1.1", "typ": "OD"},
                                    {"cislo": "0"}, {"popis": "\n"}, {"var": "jiná"}])
def test_invalid_form_never_changes_model(changes):
    scene, history, service, face = setup_scene()
    before = copy.deepcopy(face.attrs)
    with pytest.raises(ValueError):
        service.save_material(draft(**changes))
    assert list(scene.materials) == [OLD, BACK]
    assert face.attrs == before
    assert not history.undo_stack


def test_edit_both_sides_of_shared_definition_restores_everything_on_undo():
    scene, history, service, face = setup_scene()
    scene.groups[1].material = {"mat": OLD, "color": (.4, .5, .6)}
    before_attrs = copy.deepcopy(face.attrs)
    before_data = copy.deepcopy(scene.plugin_data)
    name = service.save_material(draft(), OLD)
    assert OLD not in scene.materials
    assert face.attrs["mat"] == name
    assert face.attrs["color"] == (1., .2, 0.)
    assert face.attrs["back"]["mat"] == BACK
    assert scene.groups[1].material["mat"] == name
    assert scene.groups[0].mesh is scene.groups[1].mesh
    attrs = scene.plugin_data["archcontrol"]["material_dictionaries"][name]
    assert attrs["Other"] == {"x": 2}
    assert attrs["ArchControl_RP"]["etapa"] == "3. Etapa"
    assert history.undo()
    assert face.attrs == before_attrs
    assert scene.plugin_data == before_data
    assert scene.groups[1].material["mat"] == OLD
    assert history.redo()
    assert face.attrs["mat"] == name
    assert scene.plugin_data["unrelated"] == {"value": 1}


def test_edit_back_material_does_not_repaint_front_and_round_trips_igz(tmp_path):
    from formats.igz import save_scene, load_into
    scene, history, service, face = setup_scene()
    service.save_material(draft(typ="EP", popis="zóna 2"), BACK)
    assert face.attrs["mat"] == OLD
    assert face.attrs["back"]["mat"] == "EP-2-zóna 2"
    path = tmp_path / "materials.igz"
    save_scene(scene, path)
    loaded = Scene()
    load_into(loaded, path)
    assert loaded.plugin_data == scene.plugin_data
    assert loaded.groups[0].mesh.faces[0].attrs["back"]["mat"] == "EP-2-zóna 2"
    assert history.undo()
    assert face.attrs["back"]["mat"] == BACK


def test_apply_to_nested_group_keeps_back_metadata_and_undo():
    scene, history, service, face = setup_scene()
    name = service.save_material(draft(typ="AB"))
    scene.selection = {scene.groups[0]}
    service.apply_material(name)
    assert face.attrs["mat"] == name
    assert face.attrs["opacity"] == .5
    assert face.attrs["archcontrol"]["source_face_id"] == 42
    assert face.attrs["back"]["mat"] == BACK
    assert history.undo()
    assert face.attrs["mat"] == OLD
    assert history.redo()
    assert face.attrs["mat"] == name


def test_front_paint_preserves_original_mirrored_back_and_delete_handles_both_sides():
    scene, history, service, face = setup_scene()
    face.attrs["back"] = True
    service.apply_material(BACK, [next(face_handles(scene))[0]])
    assert face.attrs["mat"] == BACK
    assert face.attrs["back"]["mat"] == OLD
    service.delete_material(OLD)
    assert "back" not in face.attrs
    assert face.attrs["mat"] == BACK
    assert history.undo()
    assert face.attrs["back"]["mat"] == OLD
    assert OLD in scene.materials


def test_palette_counts_placements_and_both_sides_even_when_hidden():
    scene, history, service, face = setup_scene()
    face.attrs["hidden"] = True
    rows = {r["name"]: r for r in service.materials()}
    assert rows[OLD]["area"] == pytest.approx(2.5)
    assert rows[BACK]["area"] == pytest.approx(2.5)
    assert rows[OLD]["hidden"] is True
    service.toggle_material_hidden(OLD)
    assert "hidden" not in face.attrs
    assert history.undo()
    assert face.attrs["hidden"] is True


def test_library_matches_ruby_schema_and_atomic_import_restamps_back(tmp_path):
    scene, history, service, face = setup_scene()
    path = tmp_path / "library.json"
    service.export_library(path)
    items = json.loads(path.read_bytes())
    assert set(items[0]) == {"name", "color", "typ", "cislo", "var", "u", "g", "popis"}
    assert items[0]["color"] == [102, 128, 153]
    path.write_text(json.dumps([{"name": BACK, "color": [255, 0, 0]}]), encoding="utf-8")
    assert service.import_library(path) == 1
    assert face.attrs["back"]["color"] == (1., 0., 0.)
    assert history.undo()
    assert face.attrs["back"]["color"] == (.1, .2, .3)
    path.write_text(json.dumps([{"name": "Nový", "color": [0, 0, 0]}, {"name": "Vadný", "color": [999]}]), encoding="utf-8")
    with pytest.raises(ValueError):
        service.import_library(path)
    assert "Nový" not in scene.materials


def test_duplicate_copies_metadata_but_has_unused_number_and_is_undoable():
    scene, history, service, face = setup_scene()
    name = service.duplicate_material(OLD)
    assert name == "SO-2-V1-U0.3-Stěna"
    ds = scene.plugin_data["archcontrol"]["material_dictionaries"]
    assert ds[name] == ds[OLD]
    assert face.attrs["mat"] == OLD
    assert history.undo()
    assert name not in scene.materials
    assert name not in scene.plugin_data["archcontrol"]["material_dictionaries"]


def test_selection_enters_correct_context_and_rejects_mixed_or_stale_paths():
    scene, history, service, face = setup_scene()
    pids = "|".join(pid for pid, _, _ in face_handles(scene))
    with pytest.raises(ValueError, match="jedné komponenty"):
        service.select_faces(pids)
    assert scene.edit_group is None
    assert service.select_faces(pids.split("|")[0]) == 1
    assert scene.edit_group is scene.groups[0]
    assert scene.selection == {face}
    service.set_faces_hidden(pids, True)
    assert face.attrs["hidden"] is True
    assert history.undo()
    assert "hidden" not in face.attrs
    with pytest.raises(ValueError, match="aktuální"):
        service.set_faces_hidden("stale/42", True)


def test_form_preserves_imported_rp_and_palette_refreshes_after_undo():
    from plugins.archcontrol.materials_ui import MaterialDialog, MaterialPalette
    scene, history, service, face = setup_scene()
    material = next(r for r in service.materials() if r["name"] == OLD)
    dialog = MaterialDialog(service, material)
    assert dialog.rp["etapa"].currentData() == "2. Etapa"
    assert dialog.u.text() == "0.3"
    assert dialog.rp["typ"].currentData() == "Stěna vnější"
    dialog.description.setText("Upravená stěna")
    dialog.save()
    from PySide6.QtWidgets import QDialog
    assert dialog.result() == QDialog.DialogCode.Accepted
    assert face.attrs["mat"] == "SO-1-V1-U0.3-Upravená stěna"
    palette = MaterialPalette(service)
    assert palette.table.rowCount() == 2
    palette.filter.setText("Upravená")
    assert palette.table.rowCount() == 1
    assert history.undo()
    palette.refresh()
    assert palette.table.rowCount() == 0


def test_scaled_instance_selection_uses_edit_mesh_and_rp_export_closes_it(tmp_path):
    scene, history, service, face = setup_scene()
    pid = list(face_handles(scene))[1][0]
    service.select_faces([pid])
    edited = scene.groups[1].mesh.faces[0]
    assert edited is not face
    assert scene.selection == {edited}
    assert edited in scene.mesh.faces
    path = tmp_path / "rp.csv"
    service.export("rp", path)
    assert scene.edit_group is None
    assert scene.groups[0].mesh is scene.groups[1].mesh
    rows = path.read_text(encoding="utf-8").splitlines()
    assert rows[1].split(",")[4] == "1.0"  # two local 0.5 m² faces, per legacy policy


@pytest.mark.parametrize("label,method", [
    ("Malovat materiálem", "paint_material"), ("Použít na výběr", "apply_material"),
    ("Upravit materiál", "edit"), ("Duplikovat materiál", "duplicate_material"),
    ("Skrýt", "toggle_material_hidden"), ("Smazat materiál", "delete_material"),
])
def test_row_actions_target_their_material_after_sorting_not_previous_selection(monkeypatch, label, method):
    from PySide6.QtCore import Qt
    from PySide6.QtWidgets import QMessageBox, QToolButton
    from plugins.archcontrol import materials_ui
    scene, history, service, face = setup_scene()
    calls = []
    if method == "edit":
        class Dialog:
            def __init__(self, service, material, parent):
                calls.append(material["name"])

            def exec(self):
                return 0
        monkeypatch.setattr(materials_ui, "MaterialDialog", Dialog)
    else:
        monkeypatch.setattr(service, method, lambda name: calls.append(name))
    monkeypatch.setattr(QMessageBox, "question", lambda *args: QMessageBox.Yes)
    palette = materials_ui.MaterialPalette(service)
    palette.table.sortItems(0, Qt.DescendingOrder)
    target = next(i for i in range(palette.table.rowCount()) if palette.table.item(i, 0).text() == OLD)
    other = next(i for i in range(palette.table.rowCount()) if i != target)
    palette.table.setCurrentCell(other, 0)
    button = next(b for b in palette.table.cellWidget(target, 8).findChildren(QToolButton)
                  if b.property("material_action") == label)
    button.click()
    assert calls == [OLD]
    assert palette.selected_name() == OLD
