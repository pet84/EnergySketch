# SPDX-License-Identifier: GPL-3.0-or-later
# © 2026 ArchEnergy s.r.o.
from types import SimpleNamespace
import pytest
from PySide6.QtGui import QVector3D
from plugins.archcontrol.core import north_from_points, orientation_from_normal


@pytest.mark.parametrize("direction,angle", [((0, 1, 0), 0), ((1, 0, 0), 270),
                                           ((0, -1, 0), 180), ((-1, 0, 0), 90),
                                           ((1, 1, 500), 315)])
def test_two_points_make_the_pointed_direction_north(direction, angle):
    value = north_from_points((10, 20, 30), tuple(a + b for a, b in zip((10, 20, 30), direction)))
    assert value == pytest.approx(angle)
    assert orientation_from_normal((direction[0], direction[1], 0), value) == "S"


def test_same_xy_or_nonfinite_points_are_rejected():
    with pytest.raises(ValueError):
        north_from_points((0, 0, 0), (0, 0, 99))
    with pytest.raises(ValueError):
        north_from_points((0, 0, 0), (float("nan"), 0, 0))


def test_north_updates_georef_and_document_in_one_undo_step():
    from core.scene import Scene
    from core.history import History
    from georef.datum import SceneDatum
    from plugins.archcontrol.adapter import PanelService
    scene = Scene()
    scene.georef = SceneDatum(49, 14, north=10)
    original = scene.georef
    history = History(scene)
    app = SimpleNamespace(window=None, scene=scene,
                          document_data=lambda **_: scene.plugin_data.get("archcontrol", {}).copy(),
                          viewport=SimpleNamespace(history=history, notify_scene_changed=lambda: None, update=lambda: None))
    service = PanelService(app)
    service.set_north(270)
    assert scene.georef.north == 90
    assert (scene.georef.lat, scene.georef.lon) == (49, 14)
    assert service.north() == 270
    assert len(history.undo_stack) == 1
    assert history.undo()
    assert scene.georef is original
    assert "archcontrol" not in scene.plugin_data
    assert service.north() == -10
    assert history.redo()
    assert service.north() == 270


def test_native_tool_uses_both_clicks_and_cancel_makes_no_edit():
    from plugins.archcontrol.adapter import north_tool
    values = []
    tools = []
    service = SimpleNamespace(set_north=lambda value: values.append(value))
    viewport = SimpleNamespace(flash_status=lambda *_: None, update=lambda: None,
                               set_active_tool=lambda tool: tools.append(tool))
    tool = north_tool(service)
    tool.on_activate(viewport)
    ctx = lambda point: SimpleNamespace(world=QVector3D(*point), viewport=viewport)
    tool.on_click(ctx((2, 3, 0)))
    tool.on_hover(ctx((12, 3, 0)))
    assert tool.hover_point == QVector3D(12, 3, 0)
    tool.on_click(ctx((12, 3, 0)))
    assert values == [270]
    assert tools[-1].name == "Select"
    tool.on_deactivate(viewport)
    tool.on_activate(viewport)
    tool.on_click(ctx((0, 0, 0)))
    tool.on_cancel(viewport)
    assert values == [270]
