# SPDX-License-Identifier: GPL-3.0-or-later
# © 2026 ArchEnergy s.r.o.
from pathlib import Path
from types import SimpleNamespace
import threading
import pytest
from core.scene import Scene
from core.history import History
from plugins.archcontrol import adapter


def test_normal_skp_entry_point_dispatches_to_registered_adapter():
    from views.main_window import MainWindow
    seen = []
    window = SimpleNamespace(_skp_import_handler=lambda path: seen.append(path) or True)
    assert MainWindow.import_skp_path(window, Path("model.skp"))
    assert seen == [Path("model.skp")]
    window._skp_import_handler = lambda path: False
    assert not MainWindow.import_skp_path(window, Path("broken.skp"))


def test_worker_parses_off_ui_thread_and_propagates_errors(monkeypatch):
    main = threading.get_ident()
    seen = []
    detached = Scene()
    def parse(path):
        seen.append(threading.get_ident())
        return detached
    monkeypatch.setattr(adapter, "parse_skp", parse)
    assert adapter.parse_in_worker(None, "test.skp") is detached
    assert len(seen) == 1 and seen[0] != main
    def broken(path):
        raise ValueError("Vadný model")
    monkeypatch.setattr(adapter, "parse_skp", broken)
    with pytest.raises(ValueError, match="Vadný model"):
        adapter.parse_in_worker(None, "test.skp")


def test_import_command_runs_on_ui_thread_and_remains_undoable(monkeypatch):
    from core.group import Group
    from core.mesh import Mesh
    from core.materials import Material
    from PySide6.QtGui import QVector3D
    detached = Scene()
    mesh = Mesh()
    mesh.add_face([QVector3D(0, 0, 0), QVector3D(1, 0, 0), QVector3D(0, 1, 0)])
    detached.groups.append(Group(mesh, name="Zóna"))
    detached.materials["SO-1"] = Material("SO-1", (1, 0, 0))
    detached.plugin_data["archcontrol"] = {"north_angle": None}
    scene = Scene()
    history = History(scene)
    messages = []
    callbacks = []
    window = SimpleNamespace(_prepare_import_display=lambda *_: callbacks.append(threading.get_ident()),
                             _update_title=lambda: None, _on_zoom_extents=lambda: None,
                             statusBar=lambda: SimpleNamespace(showMessage=lambda *args: messages.append(args)))
    app = SimpleNamespace(window=window, scene=scene,
                          viewport=SimpleNamespace(history=history, notify_scene_changed=lambda: None, update=lambda: None,
                                                   end_group_edit=scene.end_group_edit))
    monkeypatch.setattr(adapter, "parse_in_worker", lambda *_: detached)
    service = adapter.PanelService(app)
    assert service.import_path("test.skp")
    assert callbacks == [threading.get_ident()]
    assert scene.groups[0].name == "Zóna"
    assert "Potvrďte sever" in messages[0][0]
    assert history.undo()
    assert not scene.groups and not scene.materials and not scene.plugin_data
    assert history.redo()
    assert scene.groups[0].name == "Zóna"


def test_import_replaces_only_the_default_figure_and_undo_restores_it():
    from core.group import Group
    from core.mesh import Mesh
    from core.scale_figure import mark
    scene, imported = Scene(), Scene()
    figure = Group(Mesh(), name="Výchozí postava")
    mark(figure)
    scene.groups = [figure]
    target = Group(Mesh(), name="Importovaná zóna")
    imported.groups = [target]
    history = History(scene)
    history.execute(adapter.ImportCommand(imported, replace_scale_figures=True))
    assert scene.groups == [target]
    assert history.undo()
    assert scene.groups == [figure]
    assert history.redo()
    assert scene.groups == [target]
