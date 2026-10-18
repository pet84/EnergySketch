# SPDX-License-Identifier: GPL-3.0-or-later
# © 2026 ArchEnergy s.r.o.
"""The only layer depending on IngeTrazo/OpenSKP/Qt APIs.

Keep original instance identity and face sidedness instead of the upstream
adapter's display-oriented flattening. No installed binary parser is modified;
one optional MainWindow hook installs this importer for standard opening.
Legacy dictionaries and Group/Component classes are recovered through an
isolated instance of the pinned reader. Version 17 model dictionaries and
shadow north are decoded with verified boundaries; unknown layouts stay unknown.
"""
from __future__ import annotations

import copy
import hashlib
import importlib.util
from pathlib import Path
import sys
from threading import RLock

_private_reader = None
_reader_lock = RLock()


def _reader_package():
    """Load the pinned reader in a private namespace; leave global OpenSKP alone.

    Compatibility overrides are local to this plugin, not monkey patches of
    another importer that may be running on a different thread.
    """
    global _private_reader
    if _private_reader is not None:
        return _private_reader
    import openskp
    from formats import openskp_compat
    openskp_compat.apply()
    from openskp import legacy as original
    name = f"{__package__}._reader"
    spec = importlib.util.spec_from_file_location(
        name, openskp.__file__, submodule_search_locations=[str(Path(openskp.__file__).parent)])
    package = importlib.util.module_from_spec(spec)
    sys.modules[name] = package
    spec.loader.exec_module(package)
    legacy = __import__(f"{name}.legacy", fromlist=["legacy"])
    # Reuse IngeTrazo's existing dimension-path correction without modifying
    # the clone's package files (the correction works by archive interface).
    legacy._READERS["CDimensionLinear"] = original._READERS["CDimensionLinear"]
    preamble = legacy._preamble
    material_reader = legacy._READERS["CMaterial"]

    def capture_preamble(ar, cursor):
        value = preamble(ar, cursor)
        if getattr(ar, "_arch_capture_material", False) and ar.current_class == "CMaterial":
            ar._arch_material_attrs = value["attrs"]
            ar._arch_capture_material = False
        return value

    def capture_material(ar, cursor):
        ar._arch_capture_material = True
        ar._arch_material_attrs = None
        value = material_reader(ar, cursor)
        value["archcontrol_dictionaries"] = legacy._extract_legacy_attribute_dictionaries(ar._arch_material_attrs)
        return value

    legacy._preamble = capture_preamble
    legacy._READERS["CMaterial"] = capture_material
    _private_reader = (package, legacy)
    return _private_reader


def read_skp(path):
    """Read typed geometry plus legacy metadata with a bounded guide fallback."""
    with _reader_lock:
        return _read_skp_locked(path)


def _read_skp_locked(path):
    package, legacy = _reader_package()
    reader = package.SkpFile.open(str(path))
    fallback = False
    guide_reader = legacy._READERS["CConstructionLine"]
    try:
        model = reader.parse()
    except Exception as exc:
        if "definition list misaligned" not in str(exc):
            raise
        # The source reader sometimes chooses 0 bytes on a four-byte zero
        # guide trailer, then counts each leftover zero word as an entity.
        # Retry a COMPLETE parse with the known four-byte layout; never scan
        # past a failed record or return a partially parsed document.
        def four_byte_guide(ar, cursor):
            ar._cline_tail = 4
            return guide_reader(ar, cursor)
        legacy._READERS["CConstructionLine"] = four_byte_guide
        try:
            model = reader.parse()
            fallback = True
        finally:
            legacy._READERS["CConstructionLine"] = guide_reader
    metadata = {"guide_tail_4_fallback": fallback, "material_dictionaries": {}, "entities": {}}
    # Legacy's _walk retains the dictionaries and entity classes that its
    # public typed model drops. The byte reader itself remains the pinned one.
    version = str(model.version).strip("{}").split(".")[0]
    if version.isdigit() and int(version) < 21:
        if fallback:
            def four_byte_guide(ar, cursor):
                ar._cline_tail = 4
                return guide_reader(ar, cursor)
            legacy._READERS["CConstructionLine"] = four_byte_guide
        try:
            source_bytes = Path(path).read_bytes()
            archive, roots, _layers, materials = legacy._walk(source_bytes)
        finally:
            legacy._READERS["CConstructionLine"] = guide_reader
        metadata["material_dictionaries"] = {
            value["name"]: value.get("archcontrol_dictionaries", {}) for _, value in materials}
        metadata["face_dictionaries"] = {
            slot: legacy._extract_legacy_attribute_dictionaries(entry[2].get("attrs"))
            for slot, entry in archive.slots.items()
            if entry[0] == "obj" and entry[1] == "CFace" and isinstance(entry[2], dict)}
        from .skp_metadata import shadow_north,model_dictionaries
        metadata["north_angle"] = shadow_north(legacy,archive,source_bytes)
        metadata["model_dictionaries"] = model_dictionaries(legacy,archive,source_bytes)

        def entity_classes(entities):
            return ["group" if name == "CGroup" else "component"
                    for _, name, value in entities
                    if isinstance(value, dict) and value.get("k") in ("instance", "image")]

        metadata["entities"][model.root.id] = entity_classes(roots)
        for did, entry in archive.slots.items():
            if entry[0] == "obj" and entry[1] == "CComponentDefinition" and entry[2]:
                metadata["entities"][did] = entity_classes(entry[2]["ents"])
        metadata["legacy_metadata_complete"] = True
    return reader, model, metadata


def parse_skp(path):
    reader, model, metadata = read_skp(path)
    # Raw face layer IDs are exposed only in this library's internal map.
    layers = (reader._parsed or {}).get("layer_id_to_name", {})
    scene = adapt_model(model, path, layers, metadata)
    return scene


def adapt_model(model, path, layer_names=None, metadata=None):
    """Build a detached Scene; only install it after successful validation.

    Definitions share meshes; each occurrence has its OWN name/attributes/
    transform/children. Unreadable references fail the entire import.
    """
    from PySide6.QtGui import QMatrix4x4, QVector3D
    from core.group import Group
    from core.layers import DEFAULT_LAYER, Layer
    from core.materials import Material
    from core.mesh import Mesh
    from core.scene import Scene
    from formats.skp_openskp import _material_attrs, _matrix, _ring_raw

    path = Path(path)
    layer_names = layer_names or {}
    metadata = metadata or {}
    attrs_map, _registry = _material_attrs(model, path)
    scene = Scene()
    # The upstream helper strips material names for display. Identity in
    # ArchControl must retain every character of the source name.
    for mid, material in model.materials_by_id.items():
        entry = attrs_map.get(mid)
        if entry is not None:
            entry["mat"] = material.name
            scene.materials[material.name] = Material(
                material.name, color=entry.get("color"),
                texture=copy.deepcopy(entry.get("texture")),
                opacity=entry.get("opacity"))
    for material in model.materials:
        if material.name not in scene.materials:
            scene.materials[material.name] = Material(
                material.name, color=tuple(c / 255 for c in material.color[:3]),
                opacity=material.transparency)
    for layer in model.layers:
        if layer.name not in ("Layer0", "Untagged", DEFAULT_LAYER):
            scene.layers.append(Layer(layer.name, not layer.hidden))
    meshes = {}

    def layer_name(value):
        name = layer_names.get(value, value)
        if not name or name in ("Layer0", "Untagged", DEFAULT_LAYER):
            return None
        if not isinstance(name, str):
            raise ValueError(f"Neznámá hladina {name!r}")
        return name

    def mesh_for(definition):
        if id(definition) in meshes:
            return meshes[id(definition)]
        mesh = Mesh()
        for source in definition.faces.values():
            rings = [_ring_raw(definition, loop) for loop in source.loops]
            if not rings or any(ring is None or len(ring) < 3 for ring in rings):
                raise ValueError(f"Neúplná plocha {definition.name}/{source.id}")
            qrings = [[QVector3D(*(v * 0.0254 for v in p)) for p in ring]
                      for ring in rings]
            precise_rings = [[list(p) for p in ring] for ring in rings]
            # Ring connectivity may run opposite to the stored FRONT normal.
            # Leading vertices may be collinear (common on split facades).
            geometric = native_normal(qrings[0])
            if source.normal and QVector3D.dotProduct(geometric, QVector3D(*source.normal)) < 0:
                qrings = [list(reversed(ring)) for ring in qrings]
                precise_rings = [list(reversed(ring)) for ring in precise_rings]
            face = mesh.add_face(qrings[0], qrings[1:] or None)
            face.attrs.update(copy.deepcopy(attrs_map.get(source.material_id, {})))
            back = attrs_map.get(source.back_material_id)
            if back:
                face.attrs["back"] = copy.deepcopy(back)
            layer = layer_name(source.layer)
            if layer:
                face.attrs["layer"] = layer
            if source.hidden:
                face.attrs["hidden"] = True
            face.attrs["archcontrol"] = {
                "source_face_id": source.id,
                "source_definition_id": definition.id,
                # Qt vectors/matrices are float32. Preserve the source's
                # float64 coordinates, not a cached area: per-face rounding
                # at .005 m2 must not drift before the Ruby-style sum.
                "source_geometry": {"rings_inches":precise_rings,
                    "native_rings":[[list(p.toTuple()) for p in loop] for loop in (face.vertices,*face.holes)],
                    "normal":list(source.normal) if source.normal else None},
                "attribute_dictionaries": copy.deepcopy(metadata.get("face_dictionaries", {}).get(source.id, {})),
            }
        meshes[id(definition)] = mesh
        return mesh

    def placed(source, stack=frozenset(), entity_kind="unknown"):
        definition = model.definitions.get(source.ref_idx)
        if definition is None:
            raise ValueError(f"Chybí definice komponenty {source.ref_idx}")
        if source.ref_idx in stack or len(stack) >= 64:
            raise ValueError("Cyklická nebo příliš hluboká hierarchie komponent")
        group = Group(mesh_for(definition))
        group.name = source.name if source.name.strip() else definition.name
        group.xform = _matrix(source.matrix)
        group.layer = layer_name(source.layer)
        group.hidden = source.hidden
        group.component = entity_kind != "group"
        group.material = copy.deepcopy(attrs_map.get(source.material_id))
        group.ext = {"archcontrol": {
            "source_definition_name": definition.name,
            "source_instance_name": source.name,
            "attribute_dictionaries": copy.deepcopy(source.attribute_dictionaries),
            # Parser does not expose the original Group-vs-Component class.
            "source_entity_kind": entity_kind,
            "source_native_matrix":list(group.xform.copyDataTo()),
            "source_matrix_inches":[source.matrix[0],source.matrix[1],source.matrix[2],source.matrix[9],
                source.matrix[3],source.matrix[4],source.matrix[5],source.matrix[10],
                source.matrix[6],source.matrix[7],source.matrix[8],source.matrix[11],0.,0.,0.,1.],
        }}
        kinds = metadata.get("entities", {}).get(definition.id, [])
        group.children = [placed(child, stack | {source.ref_idx}, kinds[i] if i < len(kinds) else "unknown")
                          for i, child in enumerate(definition.instances)]
        return group

    if model.root is None:
        raise ValueError("Model nemá kořenovou definici")
    root_mesh = mesh_for(model.root)
    if root_mesh.faces:
        group = Group(root_mesh)
        group.name = path.stem
        group.xform = QMatrix4x4()
        group.ext = {"archcontrol": {"root_loose_faces": True}}
        scene.groups.append(group)
    kinds = metadata.get("entities", {}).get(model.root.id, [])
    scene.groups.extend(placed(instance, entity_kind=kinds[i] if i < len(kinds) else "unknown")
                        for i, instance in enumerate(model.root.instances))
    unverified = ["positioned_texture_uvs"]
    if metadata.get("model_dictionaries") is None:
        unverified.append("model_dictionaries")
    if metadata.get("north_angle") is None:
        unverified.append("north_angle")
    if not metadata.get("legacy_metadata_complete"):
        unverified.append("material_dictionaries")
        unverified.append("group_vs_component_kind")
    scene.plugin_data["archcontrol"] = {
        "schema": 1,
        "north_angle": metadata.get("north_angle"),
        "north_source": "skp-shadow-schema-7" if metadata.get("north_angle") is not None else None,
        "model_dictionaries": metadata.get("model_dictionaries") or {},
        "material_dictionaries": metadata.get("material_dictionaries", {}),
        "import": {
            "source_filename": path.name,
            "sha256": hashlib.sha256(path.read_bytes()).hexdigest() if path.is_file() else None,
            "source_version": model.version,
            "instance_names_preserved": True,
            "instance_dictionaries_preserved": True,
            "guide_tail_4_fallback": metadata.get("guide_tail_4_fallback", False),
            "unverified": unverified,
        },
    }
    if metadata.get("north_angle") is not None and scene.georef is not None:
        from dataclasses import replace
        scene.georef = replace(scene.georef,north=-metadata["north_angle"])
    return scene


class ImportCommand:
    """One history step including registry and document data.

    Upstream SnapshotImport only restores geometry/groups/layers; it would
    leave imported materials and plugin_data behind after Undo.
    """

    def __init__(self, detached, replace_scale_figures=False):
        self.detached = detached
        self.replace_scale_figures = replace_scale_figures
        self.before = None
        self.after = None

    @staticmethod
    def _capture(scene):
        return (list(scene.groups), list(scene.layers), dict(scene.materials),
                copy.deepcopy(scene.plugin_data), set(scene.selection))

    @staticmethod
    def _restore(scene, state):
        groups, layers, materials, data, selection = state
        scene.groups[:] = groups
        scene.layers[:] = layers
        scene.materials.clear()
        scene.materials.update(materials)
        scene.plugin_data.clear()
        scene.plugin_data.update(copy.deepcopy(data))
        scene.selection = set(selection)
        scene.version += 1

    def do(self, scene):
        if self.before is None:
            from core.scale_figure import is_marked
            occupied = any(not self.replace_scale_figures or not is_marked(g) for g in scene.groups)
            if occupied or scene.loose_mesh.faces or scene.loose_mesh.edges:
                raise ValueError("Nejprve vytvořte nový prázdný dokument.")
            self.before = self._capture(scene)
            try:
                if self.replace_scale_figures:
                    scene.groups.clear()
                scene.groups.extend(self.detached.groups)
                scene.layers[:] = self.detached.layers
                scene.materials.update(self.detached.materials)
                scene.plugin_data.update(copy.deepcopy(self.detached.plugin_data))
                scene.selection.clear()
                self.after = self._capture(scene)
            except BaseException:
                self._restore(scene, self.before)
                raise
        self._restore(scene, self.after)

    def undo(self, scene):
        self._restore(scene, self.before)


def import_dialog(app):
    from PySide6.QtWidgets import QFileDialog
    path, _ = QFileDialog.getOpenFileName(app.window, "Import .skp — ArchControl", "", "Model (*.skp)")
    if not path:
        return
    return PanelService(app).import_path(path)


def parse_in_worker(parent, path):
    """Only detached data crosses Signal(object); mutation stays on UI thread."""
    from PySide6.QtCore import QEventLoop, QObject, QThread, Qt, Signal, Slot
    from PySide6.QtWidgets import QProgressDialog
    class Worker(QObject):
        completed = Signal(object)

        @Slot()
        def run(self):
            try:
                result = (parse_skp(path), None)
            except Exception as exc:
                result = (None, exc)
            self.completed.emit(result)

    loop = QEventLoop()
    result = []
    class Relay(QObject):
        @Slot(object)
        def finished(self, value):
            result.append(value)
            loop.quit()

    dialog = QProgressDialog(f"Načítání {Path(path).name}…", "", 0, 0, parent)
    dialog.setWindowTitle("EnergySketch — import SKP")
    dialog.setCancelButton(None)
    dialog.setWindowModality(Qt.ApplicationModal)
    dialog.setMinimumDuration(0)
    dialog.show()
    thread, worker, relay = QThread(), Worker(), Relay()
    worker.moveToThread(thread)
    thread.started.connect(worker.run)
    worker.completed.connect(relay.finished, Qt.QueuedConnection)
    thread.finished.connect(worker.deleteLater)
    thread.start()
    try:
        loop.exec()
    finally:
        thread.quit()
        thread.wait()
        dialog.close()
    if not result:
        raise ValueError("Import nedokončil čtení modelu.")
    scene, error = result[0]
    if error is not None:
        raise error
    return scene


def face_records(scene):
    """Live geometry to pure Python records; no cached/baked area measurements.

    Unchanged imported geometry retains float64 source coordinates. Exact
    native-loop and transform fingerprints invalidate that precision mapping
    after any geometric edit; painting and IGZ round-trips do not discard it.

    Includes hidden records with visible=False. The main table drops them;
    the historical RP exporter doesn't (see the compatibility decision).
    """
    from PySide6.QtGui import QMatrix4x4
    from .core import FaceRecord
    from .exports import RP_FIELDS, read_rp

    def tup(vector):
        return (float(vector.x()), float(vector.y()), float(vector.z()))

    def flat(matrix):
        return list(matrix.copyDataTo())

    def multiply(a,b):
        return [sum(a[i*4+k]*b[k*4+j] for k in range(4)) for i in range(4) for j in range(4)]

    def point(matrix,p,vector=False):
        return tuple(sum(matrix[i*4+j]*p[j] for j in range(3))+(0 if vector else matrix[i*4+3]) for i in range(3))

    def mesh_records(mesh, matrix, precise_matrix, path, zone, parent_name, visible=True):
        for face in mesh.faces:
            attrs = face.attrs
            back = attrs.get("back")
            if back is True:
                back = attrs
            material = attrs.get("mat", "")
            material_obj = scene.materials.get(material)
            color = material_obj.color if material_obj else attrs.get("color")
            color = color or (158 / 255, 158 / 255, 158 / 255)
            hex_color = "#" + "".join(f"{round(max(0, min(1, c)) * 255):02x}" for c in color[:3])
            meta = attrs.get("archcontrol", {})
            # Imported faces retain file IDs. Native faces have only an
            # in-process handle until a persistent ID facility is added.
            pid = "/".join([*path, str(meta.get("source_face_id", id(face)))])
            native_triangles = face.triangulate()
            local_triangles = tuple(tuple(tup(v) for v in tri) for tri in native_triangles)
            source_local = None
            local_normal = tup(face.normal())
            source = meta.get("source_geometry",{})
            current_rings = [[list(p.toTuple()) for p in loop] for loop in (face.vertices,*face.holes)]
            if source.get("native_rings") == current_rings:
                precise = source.get("rings_inches",[])
                if len(precise)==len(current_rings) and all(len(a)==len(b) for a,b in zip(precise,current_rings)):
                    points = {}
                    valid = True
                    for originals,natives in zip(precise,current_rings):
                        for original,native in zip(originals,natives):
                            key,value = tuple(native),tuple(original)
                            if key in points and points[key]!=value:
                                valid = False  # native welding merged distinct source coordinates
                            points[key] = value
                    if valid and all(tuple(v.toTuple()) in points for t in native_triangles for v in t):
                        source_local = tuple(tuple(points[tuple(v.toTuple())] for v in t) for t in native_triangles)
                        local_triangles = tuple(tuple(tuple(v*.0254 for v in p) for p in t) for t in source_local)
                        if source.get("normal"):
                            local_normal = tuple(source["normal"])
            local_inches = source_local if source_local is not None else tuple(tuple(tuple(v/.0254 for v in p) for p in t) for t in local_triangles)
            world_inches = tuple(tuple(point(precise_matrix,p) for p in t) for t in local_inches)
            triangles = tuple(tuple(tuple(v*.0254 for v in p) for p in t) for t in world_inches)
            rp_attrs = scene.plugin_data.get("archcontrol", {}).get("material_dictionaries", {}).get(material, {}).get("ArchControl_RP", {})
            rp = read_rp(material, rp_attrs)
            yield FaceRecord(
                pid=pid, triangles=triangles,
                # Deliberately follows Ruby's normal.transform!, not the
                # inverse-transpose rendering rule under nonuniform scale.
                normal=point(precise_matrix,local_normal,True),
                material=material,
                back_material=back.get("mat", "") if isinstance(back, dict) else "",
                layer=attrs.get("layer", "Layer0"), zone=zone,
                parent_name=parent_name, color=hex_color,
                rp=tuple(rp[field] for field in RP_FIELDS),
                visible=visible and scene.entity_visible(face),
                local_triangles=local_triangles, local_normal=local_normal,
                source_triangles_inches=world_inches if source_local is not None else None,
                source_local_triangles_inches=source_local,
            )

    def walk(group, parent_matrix, parent_precise, path, zone, visible):
        matrix = parent_matrix * (group.xform or QMatrix4x4())
        meta = (group.ext or {}).get("archcontrol", {})
        native_matrix = flat(group.xform or QMatrix4x4())
        native_inches = [v/.0254 if i in (3,7,11) else v for i,v in enumerate(native_matrix)]
        own_precise = meta.get("source_matrix_inches",native_inches) if meta.get("source_native_matrix")==native_matrix else native_inches
        precise_matrix = multiply(parent_precise,own_precise)
        is_root = meta.get("root_loose_faces", False)
        if zone == "(model)" and not is_root and is_component_group(group):
            zone = group.name or "(model)"
        own_path = [*path, group.uid]
        visible = visible and scene.entity_visible(group)
        parent_name = "" if is_root else meta.get("source_definition_name", group.name)
        yield from mesh_records(group.mesh, matrix, precise_matrix, own_path, zone, parent_name, visible)
        for child in group.children:
            yield from walk(child, matrix, precise_matrix, own_path, zone, visible)

    identity = flat(QMatrix4x4())
    yield from mesh_records(scene.loose_mesh, QMatrix4x4(), identity, [], "(model)", "")
    for group in scene.groups:
        yield from walk(group, QMatrix4x4(), identity, [], "(model)", True)


def build_section_slice(scene, plane):
    """Detached, editable edges where visible faces meet the chosen plane.

    Ignore display clipping, honour hidden faces/layers/ancestors, and stay
    in the current edit context. Source meshes and the plane are untouched.
    """
    from PySide6.QtGui import QVector3D
    from core.group import Group
    from core.mesh import Mesh
    from .section_slice import plane_basis, triangle_segment
    point, normal = plane_basis(plane.point.toTuple(), plane.normal.toTuple())
    mesh = Mesh()

    def add(a, b):
        # The host welds endpoints closer than 0.1 mm. Such a fragment is
        # not representable as an independent edge in the native mesh.
        try:
            mesh.add_edge(QVector3D(*a), QVector3D(*b))
        except ValueError as error:
            if "endpoints weld to one vertex" not in str(error):
                raise

    def faces(source, matrix=None):
        def position(p):
            return tuple((matrix.map(p) if matrix is not None else p).toTuple())
        for face in source.faces:
            if not scene.entity_visible(face):
                continue
            rings = [[position(p) for p in loop] for loop in (face.vertices, *face.holes)]
            if all(abs(sum(normal[i]*(p[i]-point[i]) for i in range(3))) <= 1e-7
                   for loop in rings for p in loop):
                for loop in rings:
                    for a, b in zip(loop, loop[1:] + loop[:1]):
                        add(a, b)
            else:
                for triangle in face.triangulate():
                    segment = triangle_segment(tuple(position(p) for p in triangle), point, normal)
                    if segment is not None:
                        add(*segment)

    def walk(group, parent=None):
        if not scene.entity_visible(group) or group.billboard:
            return
        own = group.xform
        matrix = parent if own is None else own if parent is None else parent * own
        faces(group.mesh, matrix)
        for child in group.children:
            walk(child, matrix)

    context = scene.edit_group
    faces(scene.mesh)
    for group in (context.children if context is not None else scene.groups):
        walk(group)
    # Remove only truly collinear triangle subdivisions, not small bends in
    # curved sections (the general mesh simplifier allows a wider angle).
    for vertex in list(mesh.vertices):
        if len(vertex.edges) != 2:
            continue
        a, b = [edge.other(vertex).position.toTuple() for edge in vertex.edges]
        p = vertex.position.toTuple()
        u = tuple(p[i]-a[i] for i in range(3))
        v = tuple(b[i]-p[i] for i in range(3))
        cross = (u[1]*v[2]-u[2]*v[1], u[2]*v[0]-u[0]*v[2], u[0]*v[1]-u[1]*v[0])
        if (sum(u[i]*v[i] for i in range(3)) > 0
                and sum(c*c for c in cross) <= 1e-12*sum(c*c for c in u)*sum(c*c for c in v)):
            mesh.collapse_vertex(vertex)
    mesh.prune_orphan_vertices()
    if not mesh.edges:
        raise ValueError("Rovina řezu neprotíná žádné viditelné plochy.")
    group = Group(mesh, "Průřez " + (plane.symbol or plane.name or str(plane.uid)))
    group.ext = {"archcontrol": {"section_slice": {
        "source_plane_uid": plane.uid, "point": point, "normal": normal, "snapshot": True}}}
    return group


class SectionSliceCommand:
    """Insert a detached slice once; redo reuses its geometry and identity."""
    def __init__(self, scene, group):
        self.group = group
        context = scene.edit_group
        self.owner = context.children if context is not None else scene.groups
        if context is not None and context.xform is not None:
            inverse, valid = context.xform.inverted()
            if not valid:
                raise ValueError("Transformaci skupiny nelze obrátit.")
            from core.group import transformed_mesh
            group.mesh = transformed_mesh(group.mesh, inverse)
        self.index = len(self.owner)
        self.before = set(scene.selection)

    def do(self, scene):
        self.owner.insert(self.index, self.group)
        scene.selection = {self.group}
        scene.version += 1

    def undo(self, scene):
        self.owner.remove(self.group)
        scene.selection = set(self.before)
        scene.version += 1


def section_slice_context_menu(service, menu, selection):
    from PySide6.QtCore import QTimer
    from PySide6.QtGui import QAction
    from PySide6.QtWidgets import QMessageBox
    from core.section import SectionPlane
    from core.i18n import tr
    planes = [value for value in selection if isinstance(value, SectionPlane)]
    if not planes:
        return
    action = QAction("Vytvořit skupinu z průřezu", menu)
    action.setToolTip("Vytvořit samostatnou upravitelnou skupinu hran v rovině řezu.")
    action.setEnabled(len(selection) == 1)

    def create():
        try:
            service.create_section_slice(planes[0])
        except ValueError as error:
            QMessageBox.warning(service.parent, "Průřez modelu", str(error))
    action.triggered.connect(lambda: QTimer.singleShot(0, create))
    anchor = next((item for item in menu.actions() if item.text() == tr("Name and symbol…")), None)
    menu.insertAction(anchor, action)


class PanelService:
    """Host API boundary used by the Qt panel, separate from business logic."""

    def __init__(self, app):
        self.app = app
        self.parent = app.window

    def create_section_slice(self, plane):
        scene = self.app.scene
        if plane not in scene.section_planes:
            raise ValueError("Rovina řezu už není v dokumentu.")
        from core.outliner import editing_inside_component
        if editing_inside_component(scene):
            raise ValueError("Nejprve ukončete úpravy komponenty; průřez pak vytvořte v modelu.")
        group = build_section_slice(scene, plane)
        self.app.viewport.history.execute(SectionSliceCommand(scene, group))
        if self.app.viewport.history.last_error:
            raise ValueError(self.app.viewport.history.last_error)
        self.app.viewport.notify_scene_changed()
        self.app.viewport.update()
        return group

    def north(self):
        data = self.app.document_data(default={})
        value = data.get("north_angle")
        if value is None and self.app.scene.georef is not None:
            value = -self.app.scene.georef.north
        return value

    def set_north(self, value):
        import math
        if not math.isfinite(value):
            raise ValueError("Sever musí být konečné číslo ve stupních.")
        data = copy.deepcopy(self.app.document_data(default={}))
        data["north_angle"] = value % 360
        data["north_source"] = "user_confirmed"
        def action(scene):
            from dataclasses import replace
            scene.plugin_data["archcontrol"] = data
            if scene.georef is not None:
                scene.georef = replace(scene.georef, north=-value)
        self._execute(action)
        reset = getattr(self.app.viewport, "reset_tiles", None)
        if callable(reset):
            reset()

    def data(self):
        from .core import collect_rows
        from .zones import zone_report
        records = list(face_records(self.app.scene))
        result = collect_rows(records, self.north())
        result["zone_table"] = zone_report(result["reports"], list(component_records(self.app.scene)))
        return result

    def zones(self):
        from .core import collect_rows
        from .zones import component_palette
        reports = collect_rows(face_records(self.app.scene), None, include_rows=False)["reports"]
        return component_palette(reports, list(component_records(self.app.scene)))

    def select_component(self, uid):
        def find(groups, path=()):
            for group in groups:
                if group.uid == uid:
                    return (*path, group)
                result = find(group.children, (*path, group))
                if result:
                    return result
        path = find(self.app.scene.groups)
        if not path:
            raise ValueError("Komponenta už není dostupná.")
        self.app.viewport.end_group_edit()
        for parent in path[:-1]:
            self.app.viewport.begin_group_edit(parent)
            if self.app.scene.edit_group is not parent:
                raise ValueError("Nadřazená komponenta je uzamčená.")
        self.app.scene.select([path[-1]])
        self.app.viewport.notify_scene_changed()
        self.app.viewport.update()

    def toggle_component_hidden(self, uid):
        group = next((g for g in all_groups(self.app.scene) if g.uid == uid), None)
        if group is None:
            raise ValueError("Komponenta už není dostupná.")
        def action(scene):
            group.hidden = not group.hidden
        self._execute(action, groups=[group])

    def export(self, kind, path):
        from .core import collect_rows
        from .exports import complex_csv, energy_csv, renovacni_pas_csv
        # Native group editing temporarily bakes the prototype into world
        # space. Finish its share-back before the legacy RP local export.
        self.app.viewport.end_group_edit()
        records = list(face_records(self.app.scene))
        north = self.north()
        if north is None:
            raise ValueError("Nejprve potvrďte sever modelu.")
        if kind == "rp":
            dictionaries = self.app.document_data(default={}).get("material_dictionaries", {})
            attrs = {name: ds.get("ArchControl_RP", {}) for name, ds in dictionaries.items()}
            data = renovacni_pas_csv(records, north, attrs)
        else:
            rows = collect_rows(records, north)["rows"]
            data = (complex_csv if kind == "complex" else energy_csv)(rows)
        Path(path).write_bytes(data)

    def import_file(self):
        import_dialog(self.app)

    def import_path(self, path):
        from PySide6.QtWidgets import QMessageBox
        from core.scale_figure import is_marked
        scene, viewport, window = self.app.scene, self.app.viewport, self.app.window
        if (any(not is_marked(g) for g in scene.groups) or scene.loose_mesh.faces or scene.loose_mesh.edges or
                scene.dimensions or scene.geo_paths or scene.geo_points or scene.image_planes):
            QMessageBox.information(window, "Otevření SKP", "Nejprve vytvořte nový prázdný dokument. Import SKP vyžaduje samostatný model kvůli severu a zónám.")
            return False
        try:
            viewport.end_group_edit()
            detached = parse_in_worker(window, path)
            command = ImportCommand(detached, replace_scale_figures=True)
            command.added_groups = list(detached.groups)
            viewport.history.execute(command)
            if viewport.history.last_error:
                raise ValueError(viewport.history.last_error)
            window._prepare_import_display(command, lambda *_: None)
            viewport.notify_scene_changed()
            viewport.update()
            window._import_name = Path(path).name
            window._update_title()
            window._on_zoom_extents()
            north = detached.plugin_data["archcontrol"]["north_angle"]
            window.statusBar().showMessage("Model načten. " + ("Potvrďte sever modelu v panelu ArchControl." if north is None else "Sever byl načten z modelu."), 10000)
            return True
        except Exception as exc:
            QMessageBox.warning(window, "Import SKP — ArchControl",
                f"Model se nepodařilo načíst.\n{exc}\n\n"
                "Z původního programu jej exportujte jako COLLADA (.dae) nebo OBJ a importujte tento soubor.")
            return False

    def paint_material(self, name):
        from tools.paint import PaintTool
        material = self.app.scene.materials.get(name)
        if material is None:
            raise ValueError("Materiál nebyl nalezen.")
        PaintTool.current_material = material
        PaintTool.current_color = material.color or (.62, .62, .62)
        PaintTool.current_texture = copy.deepcopy(material.texture)
        PaintTool.current_opacity = material.opacity
        PaintTool.current_texture_plane = None
        PaintTool.current_is_default = False
        PaintTool.sample_armed = False
        self.app.viewport.set_active_tool(PaintTool())

    def start_north_tool(self):
        self.app.viewport.set_active_tool(north_tool(self))

    def start_window_tool(self, parameters):
        self.app.viewport.set_active_tool(window_tool(self, parameters))

    def window_geometry(self, pid, world_click, parameters):
        """Ruby grid in original local coordinates, then composed into world."""
        from PySide6.QtGui import QMatrix4x4, QVector3D
        scene = self.app.scene
        found = next(((f, g) for key, f, g in face_handles(scene) if key == pid), None)
        if found is None:
            raise ValueError("Plocha už neexistuje. Vyberte ji znovu.")
        face, owner = found
        matrix = QMatrix4x4()
        level = scene.groups
        for uid in pid.split("/")[:-1]:
            group = next((g for g in level if g.uid == uid), None)
            if group is None:
                raise ValueError("Komponenta už neexistuje.")
            if group.xform is not None:
                matrix = matrix * group.xform
            level = group.children
        positions = face.vertices
        # An open component is temporarily baked into world coordinates.
        # Recover its saved local frame so dimensions still match Ruby.
        if scene.edit_group is owner and scene._edit_stack:
            share = scene._edit_stack[-1].get("share")
            if share is not None:
                matrix = share[2]
                inverse, ok = matrix.inverted()
                if not ok:
                    raise ValueError("Komponenta má nevratnou transformaci.")
                positions = [inverse.map(p) for p in positions]
        inverse, ok = matrix.inverted()
        if not ok:
            raise ValueError("Komponenta má nevratnou transformaci.")
        click = inverse.map(QVector3D(*world_click))
        normal = QVector3D()
        for a, b in zip(positions, [*positions[1:], positions[0]]):
            normal += QVector3D.crossProduct(a, b)
        normal.normalize()
        if normal.lengthSquared() < .5:
            raise ValueError("Plocha nemá platnou normálu.")
        click -= normal * QVector3D.dotProduct(click-positions[0], normal)
        local = parameters.rectangles((click.x(), click.y(), click.z()),
                                      (normal.x(), normal.y(), normal.z()))
        return [[matrix.map(QVector3D(*p)) for p in rect] for rect in local]

    def insert_window_grid(self, pid, world_click, parameters):
        from core.edits import build_add_edges
        from core.history import AddFaceCommand, SnapshotMutation
        import uuid
        scene, viewport = self.app.scene, self.app.viewport
        rectangles = self.window_geometry(pid, world_click, parameters)
        material = scene.materials.get(parameters.material) if parameters.material else None
        if parameters.material and material is None:
            raise ValueError("Zvolený materiál už neexistuje.")
        self.select_faces([pid])  # native context: respects locks, sharing and undo
        def mutate(current):
            faces = []
            edges = []
            for rect in rectangles:
                attrs = copy.deepcopy(material.face_attrs()) if material else {}
                if material:
                    attrs["back"] = True
                faces.append(AddFaceCommand(rect, attrs=attrs, auto=not loop_in_existing_void(current.mesh,rect)))
                edges.extend(zip(rect, [*rect[1:], rect[0]]))
            target_face = next(item for key,item,_ in face_handles(current) if key == pid)
            local = coplanar_scene(current.mesh,target_face.normal(),target_face.vertices[0])
            command = build_add_edges(local, edges, detect_faces=False,
                                      extra=faces, plane_rebuild=True)
            command.do(local)
            # A split imported face may inherit its source PID. Keep exactly
            # one original identity; each new region gets a fresh stable ID.
            used = set()
            for face in current.mesh.faces:
                meta = face.attrs.get("archcontrol", {})
                fid = meta.get("source_face_id")
                if fid is None or str(fid) in used:
                    meta = copy.deepcopy(meta)
                    meta["source_face_id"] = "window-" + uuid.uuid4().hex
                    face.attrs["archcontrol"] = meta
                used.add(str(face.attrs["archcontrol"]["source_face_id"]))
        viewport.history.execute(SnapshotMutation(mutate))
        if viewport.history.last_error or viewport.history.last_rejected:
            raise ValueError(viewport.history.last_error or viewport.history.last_rejected)
        viewport.notify_scene_changed()
        viewport.update()
        return len(rectangles)

    def _execute(self, action, faces=(), groups=()):
        self.app.viewport.history.execute(MaterialStateCommand(action, faces, groups))
        if self.app.viewport.history.last_error:
            raise ValueError(self.app.viewport.history.last_error)
        self.app.viewport.notify_scene_changed()
        self.app.viewport.update()

    def materials(self):
        from collections import defaultdict
        from .core import parse_material_name, triangulated_area
        usage, zones = defaultdict(float), defaultdict(set)
        for record in face_records(self.app.scene):
            for name in {record.material, record.back_material} - {""}:
                usage[name] += triangulated_area(record.triangles)
                if record.zone != "(model)":
                    zones[name].add(record.zone)
        hidden_by_material = {}
        for _pid, face, _group in face_handles(self.app.scene):
            back = face.attrs.get("back")
            names = {face.attrs.get("mat")}
            if isinstance(back, dict):
                names.add(back.get("mat"))
            for name in names - {None, ""}:
                hidden_by_material[name] = hidden_by_material.get(name, True) and bool(face.attrs.get("hidden"))
        result = []
        dictionaries = self.app.document_data(default={}).get("material_dictionaries", {})
        from .exports import read_rp
        for name, material in self.app.scene.materials.items():
            color = material.color or (.62, .62, .62)
            result.append({"name": name, **parse_material_name(name),
                           "color": "#" + "".join(f"{round(c * 255):02x}" for c in color),
                           "area": usage[name], "zones": sorted(zones[name]),
                           "hidden": hidden_by_material.get(name, False),
                           "rp": read_rp(name, dictionaries.get(name, {}).get("ArchControl_RP", {}))})
        return sorted(result, key=lambda item: (not bool(item["typ"]), item["typ"], item["cislo"], item["name"].casefold()))

    def _targets(self, pids=None):
        from core.mesh import Face
        from core.group import Group
        if pids is not None:
            wanted = set(pids.split("|")) if isinstance(pids, str) else set(pids)
            found = [(pid, face) for pid, face, _ in face_handles(self.app.scene) if pid in wanted]
            if set(pid for pid, _ in found) != wanted:
                raise ValueError("Výběr ploch už není aktuální. Obnovte tabulku.")
            return {face for _, face in found}
        result = set()
        def add(entity):
            if isinstance(entity, Face):
                result.add(entity)
            elif isinstance(entity, Group):
                result.update(entity.mesh.faces)
                for child in entity.children:
                    add(child)
        for entity in self.app.scene.selection:
            add(entity)
        return result

    def select_faces(self, pids):
        wanted = set(pids.split("|")) if isinstance(pids, str) else set(pids)
        self._targets(wanted)  # validate before changing the edit context
        paths = {pid.rsplit("/", 1)[0] if "/" in pid else "" for pid in wanted}
        if len(paths) != 1:
            raise ValueError("Vyberte plochy jedné komponenty. Pro více zón vypněte Sčítat stejné nebo použijte filtr.")
        path = next(iter(paths))
        scene, viewport = self.app.scene, self.app.viewport
        wanted_groups = path.split("/") if path else []
        current_groups = [entry["group"].uid for entry in scene._edit_stack]
        if current_groups != wanted_groups:
            viewport.end_group_edit()
            level = scene.groups
            for uid in wanted_groups:
                group = next((g for g in level if g.uid == uid), None)
                if group is None:
                    raise ValueError("Komponenta už není dostupná. Obnovte tabulku.")
                viewport.begin_group_edit(group)
                if scene.edit_group is not group:
                    raise ValueError("Komponentu nelze otevřít. Zkontrolujte její uzamčení.")
                level = group.children
        faces = self._targets(wanted)
        self.app.scene.select(faces)
        self.app.viewport.notify_scene_changed()
        self.app.viewport.update()
        return len(faces)

    def set_faces_hidden(self, pids, hidden):
        faces = self._targets(pids)
        def action(scene):
            for face in faces:
                if hidden:
                    face.attrs["hidden"] = True
                else:
                    face.attrs.pop("hidden", None)
        self._execute(action, faces)

    def show_all_faces(self):
        faces = {f for _, f, _ in face_handles(self.app.scene)}
        groups = list(all_groups(self.app.scene))
        def action(scene):
            for face in faces:
                face.attrs.pop("hidden", None)
            for group in groups:
                group.hidden = False
        self._execute(action, faces, groups)

    def save_material(self, data, old_name=None, pids=None):
        from core.materials import Material
        from .materials import build_name, validate_identity, validate_rp, hex_rgb
        name = build_name(data)
        scene = self.app.scene
        if old_name is not None and old_name not in scene.materials:
            raise ValueError("Upravovaný materiál už neexistuje.")
        validate_identity(scene.materials, name, old_name)
        rp = validate_rp(data.get("rp", {}))
        color = hex_rgb(data.get("color", "#9e9e9e"))
        old = scene.materials.get(old_name)
        new = Material(name, color, copy.deepcopy(old.texture) if old else None,
                       .5 if data["typ"] == "AB" else 1., old.finish if old else None)
        targets = self._targets(pids) if data.get("apply") else set()
        faces = {f for _, f, _ in face_handles(scene) if old_name and wears(f.attrs, old_name)} | targets
        groups = [g for g in all_groups(scene) if old_name and isinstance(g.material, dict) and g.material.get("mat") == old_name]
        def action(scene):
            if old_name is not None:
                scene.materials.pop(old_name)
                for face in faces - targets:
                    restamp(face.attrs, old_name, new)
                for face in faces & targets:
                    restamp(face.attrs, old_name, new)
                for group in groups:
                    group.material = new.face_attrs()
            scene.materials[name] = new
            ds = scene.plugin_data.setdefault("archcontrol", {}).setdefault("material_dictionaries", {})
            attrs = ds.pop(old_name, {}) if old_name else {}
            attrs["ArchControl_RP"] = rp
            ds[name] = attrs
            for face in targets:
                stamp_front(face.attrs, new)
        self._execute(action, faces, groups)
        return name

    def apply_material(self, name, pids=None):
        material = self.app.scene.materials.get(name)
        if material is None:
            raise ValueError("Materiál nebyl nalezen.")
        faces = self._targets(pids)
        if not faces:
            raise ValueError("Nejprve vyberte plochy nebo skupinu.")
        def action(scene):
            for face in faces:
                stamp_front(face.attrs, material)
        self._execute(action, faces)

    def toggle_material_hidden(self, name):
        handles = [(pid, f) for pid, f, _ in face_handles(self.app.scene) if wears(f.attrs, name)]
        if handles:
            self.set_faces_hidden([pid for pid, _ in handles], any(not f.attrs.get("hidden") for _, f in handles))

    def delete_material(self, name):
        scene = self.app.scene
        if name not in scene.materials:
            raise ValueError("Materiál už neexistuje.")
        faces = {f for _, f, _ in face_handles(scene) if wears(f.attrs, name)}
        groups = [g for g in all_groups(scene) if isinstance(g.material, dict) and g.material.get("mat") == name]
        def action(scene):
            scene.materials.pop(name)
            scene.plugin_data.get("archcontrol", {}).get("material_dictionaries", {}).pop(name, None)
            for face in faces:
                restamp(face.attrs, name, None)
            for group in groups:
                group.material = None
        self._execute(action, faces, groups)

    def duplicate_material(self, name):
        from dataclasses import replace
        from .materials import next_free_number, build_name
        from .core import parse_material_name
        scene = self.app.scene
        source = scene.materials[name]
        parsed = parse_material_name(name)
        parsed["cislo"] = str(next_free_number(scene.materials, parsed["typ"]))
        new_name = build_name(parsed)
        new = replace(source, name=new_name, texture=copy.deepcopy(source.texture))
        def action(scene):
            scene.materials[new_name] = new
            ds = scene.plugin_data.setdefault("archcontrol", {}).setdefault("material_dictionaries", {})
            ds[new_name] = copy.deepcopy(ds.get(name, {}))
        self._execute(action)
        return new_name

    def export_library(self, path):
        from .materials import library_json
        data = [(m.name, [round(c * 255) for c in m.color or (.62, .62, .62)]) for m in self.app.scene.materials.values()]
        Path(path).write_bytes(library_json(data))

    def import_library(self, path):
        from dataclasses import replace
        from core.materials import Material
        from .materials import read_library
        batch = read_library(Path(path).read_text(encoding="utf-8-sig"))
        names = {name for name, _ in batch}
        faces = {f for _, f, _ in face_handles(self.app.scene) if any(wears(f.attrs, n) for n in names)}
        groups = [g for g in all_groups(self.app.scene) if isinstance(g.material, dict) and g.material.get("mat") in names]
        def action(scene):
            for name, color in batch:
                old = scene.materials.get(name)
                new = replace(old, color=color) if old else Material(name, color)
                scene.materials[name] = new
                for face in faces:
                    restamp(face.attrs, name, new)
                for group in groups:
                    if group.material.get("mat") == name:
                        group.material = new.face_attrs()
        self._execute(action, faces, groups)
        return len(batch)


def all_groups(scene):
    def walk(groups):
        for group in groups:
            yield group
            yield from walk(group.children)
    yield from walk(scene.groups)


def component_records(scene):
    from .zones import rounded
    def walk(groups, palette_zone=None, report_zone=None, visible=True):
        for group in groups:
            meta = (group.ext or {}).get("archcontrol", {})
            if meta.get("root_loose_faces") or (group.ext or {}).get("scale_figure"):
                continue
            component = is_component_group(group)
            name = group.name or meta.get("source_definition_name", "")
            own_palette = palette_zone or (name if component else None)
            # Ruby report seeds '(model)' on a group; its palette doesn't.
            own_report = report_zone or (name if component else "(model)")
            own_visible = visible and scene.entity_visible(group)
            if component:
                value = component_volume(group)  # own transform, as Ruby e.volume
                yield {"name": name or "(bez nazvu)",
                       "defName": meta.get("source_definition_name", group.name),
                       "eid": group.uid, "zone": own_palette or "(model)",
                       "volume": rounded(value or 0., 3), "raw_volume": value or 0.,
                       "solid": value is not None, "hidden": group.hidden,
                       "report_zone": own_report or "(model)", "report_visible": own_visible}
            yield from walk(group.children, own_palette, own_report, own_visible)
    yield from walk(scene.groups)


def component_volume(group):
    from .zones import solid_volume_faces
    if group.children or not group.mesh.faces:
        return None
    if any(sum(not getattr(f, "interior", False) for f in edge.faces) != 2 for edge in group.mesh.edges):
        return None
    faces = []
    def points(positions):
        mapped = [group.xform.map(p) for p in positions] if group.xform is not None else positions
        return tuple((float(p.x()), float(p.y()), float(p.z())) for p in mapped)
    for face in group.mesh.faces:
        if getattr(face, "interior", False):
            continue
        faces.append({"loops": [points(loop) for loop in [face.vertices, *face.holes]],
                      "triangles": [points(tri) for tri in face.triangulate()]})
    return solid_volume_faces(faces)


def is_component_group(group):
    meta = (group.ext or {}).get("archcontrol", {})
    return (not meta.get("root_loose_faces") and bool(group.component) and
            (group.xform is not None or meta.get("source_entity_kind") == "component"))


def north_tool(service):
    """Construct a native snapping tool without importing host APIs in core."""
    from PySide6.QtGui import QVector3D
    from tools.base import Tool
    from tools.select import SelectTool
    from .core import north_from_points

    class NorthTool(Tool):
        name = "ArchControl — Sever dvěma body"
        description = "Klikněte na počátek a potom ve směru severu."

        def __init__(self):
            self.start_point = self.hover_point = None

        def on_activate(self, viewport):
            viewport.flash_status("Sever: klikněte na počáteční bod. Esc nástroj ukončí.", 6000)

        def on_deactivate(self, viewport):
            self.start_point = self.hover_point = None

        def on_hover(self, ctx):
            self.hover_point = QVector3D(ctx.world)
            ctx.viewport.update()

        def on_click(self, ctx):
            if self.start_point is None:
                self.start_point = QVector3D(ctx.world)
                ctx.viewport.flash_status("Sever: klikněte na druhý bod ve směru severu.", 6000)
                return
            try:
                p = self.start_point
                q = ctx.world
                angle = north_from_points((p.x(), p.y(), p.z()), (q.x(), q.y(), q.z()))
                service.set_north(angle)
            except ValueError as exc:
                ctx.viewport.flash_status(str(exc), 6000)
                return
            ctx.viewport.set_active_tool(SelectTool())
            ctx.viewport.flash_status(f"Sever nastaven: {angle:.1f}°", 6000)

        def on_cancel(self, viewport):
            viewport.set_active_tool(SelectTool())

    return NorthTool()


def north_overlay(app, viewport, painter):
    from PySide6.QtCore import QPointF
    from PySide6.QtGui import QColor, QPen
    tool = viewport.active_tool
    if tool is None or tool.name != "ArchControl — Sever dvěma body":
        return
    if tool.start_point is None or tool.hover_point is None:
        return
    points = [(v.x(), v.y(), v.z()) for v in (tool.start_point, tool.hover_point)]
    x, y, front = app.world_to_pixels(points)
    if not all(front):
        return
    painter.setPen(QPen(QColor("#ee8b20"), 3))
    a, b = QPointF(float(x[0]), float(y[0])), QPointF(float(x[1]), float(y[1]))
    painter.drawLine(a, b)
    painter.drawEllipse(a, 4, 4)
    painter.drawEllipse(b, 4, 4)
    painter.drawText(b + QPointF(8, -8), "S")


def loop_in_existing_void(mesh,points):
    """Drawing inside an existing hole must not punch that hole a second time."""
    from PySide6.QtGui import QVector3D
    from core.mesh import Face, Vertex
    from core.topology import loop_inside_face
    from .live_commands import same_ring
    normal = native_normal(points)
    mm = lambda ring:[[float(v.x()*1000),float(v.y()*1000),float(v.z()*1000)] for v in ring]
    for face in mesh.faces:
        if not face.holes or abs(QVector3D.dotProduct(normal,face.normal()))<.99999:
            continue
        if any(abs(QVector3D.dotProduct(v-points[0],normal))>.0001 for v in face.vertices):
            continue
        for hole in face.holes:
            if same_ring(mm(points),mm(hole)) or same_ring(mm(points),mm(hole),True) or loop_inside_face(Face([Vertex(v) for v in hole]),points):
                return True
    return False


def coplanar_scene(mesh,normal,origin):
    """Scope native face subdivision to its plane, retaining full mesh incidence.

    AddFaceCommand's boundary-carving fallback also tests projected outlines;
    exposing noncoplanar faces there can carve a pyramid's base into a side.
    This per-call mesh view changes no global host methods or installed files.
    """
    from PySide6.QtGui import QVector3D
    from core.scene import Scene

    class PlaneMesh:
        def __getattr__(self,name):
            return getattr(mesh,name)

        @property
        def faces(self):
            return [face for face in mesh.faces
                    if abs(QVector3D.dotProduct(face.normal(),normal))>.99999
                    and all(abs(QVector3D.dotProduct(v-origin,normal))<=.0001 for v in face.vertices)]

    return Scene(mesh=PlaneMesh())


class LiveMutationCommand:
    """One atomic LIVE transaction, including native meshes and all plugin data."""
    def __init__(self,action):
        self.action = action
        self.before = self.after = self.captured = None

    @staticmethod
    def capture(scene):
        from PySide6.QtGui import QMatrix4x4
        groups = list(all_groups(scene))
        meshes = {scene.loose_mesh, *(g.mesh for g in groups)}
        geometry = {}
        for mesh in meshes:
            state = mesh.capture_state()
            state["fattrs"] = {f:copy.deepcopy(a) for f,a in state["fattrs"].items()}
            geometry[mesh] = state
        fields = [(g,g.mesh,list(g.children),QMatrix4x4(g.xform) if g.xform is not None else None,
                   copy.deepcopy(g.ext),copy.deepcopy(g.material),g.layer,g.hidden,g.name) for g in groups]
        return ImportCommand._capture(scene),geometry,fields

    @staticmethod
    def restore(scene,state):
        from core.history import _dirty_group_chunks
        base,geometry,fields = state
        ImportCommand._restore(scene,base)
        for mesh,snapshot in geometry.items():
            snapshot = {**snapshot,"fattrs":{f:copy.deepcopy(a) for f,a in snapshot["fattrs"].items()}}
            mesh.restore_state(snapshot)
        for g,mesh,children,matrix,ext,material,layer,hidden,name in fields:
            g.mesh,g.xform,g.layer,g.hidden,g.name = mesh,matrix,layer,hidden,name
            g.children[:] = children
            g.ext,g.material = copy.deepcopy(ext),copy.deepcopy(material)
        _dirty_group_chunks(scene)

    def do(self,scene):
        if self.before is None:
            self.before = self.capture(scene)
            try:
                self.captured = self.action(scene)
                self.after = self.capture(scene)
            except BaseException:
                self.restore(scene,self.before)
                raise
        self.restore(scene,self.after)

    def undo(self,scene):
        self.restore(scene,self.before)


def execute_live_command(service,command,identities):
    """Apply only the original whitelisted native actions, then capture before commit."""
    from PySide6.QtGui import QMatrix4x4, QVector3D
    from core.group import Group
    from core.history import AddFaceCommand
    from core.layers import Layer
    from core.materials import Material
    from core.mesh import Mesh
    from core.scene import Scene
    from .live import encode
    from .live_commands import solid_rings,validate_model,binding,model_material_name
    from .materials import build_name,next_free_number,validate_identity
    scene,viewport = service.app.scene,service.app.viewport
    if scene.edit_group is not None:
        raise ValueError("Nejdříve ukončete editaci komponenty.")
    action = command["action"]
    if action not in ("box","pyramid","colors","import_model","sync_model"):
        raise ValueError("Tento zpětný příkaz zatím není podporován.")
    if action == "import_model":
        validate_model(command["payload"])

    def dictionaries(group):
        return (group.ext or {}).get("archcontrol",{}).get("attribute_dictionaries",{})

    def create_group(current,zone_id,name):
        if any(dictionaries(g).get("ArchControl_AIRIS",{}).get("zone_id") == zone_id for g in all_groups(current)):
            raise ValueError("Zóna s tímto ID již v modelu existuje.")
        group = Group(Mesh(),name)
        group.component,group.xform = True,QMatrix4x4()
        group.ext = {"archcontrol":{"source_entity_kind":"component","attribute_dictionaries":{
            "ArchControl_AIRIS":{"zone_id":zone_id}}}}
        current.groups.append(group)
        return group

    def add_face(group,rings,material,meta):
        points = [[QVector3D(*(v/1000 for v in p)) for p in loop] for loop in rings]
        attrs = {**copy.deepcopy(material.face_attrs()),"back":True,"archcontrol":meta}
        native = AddFaceCommand(points[0],holes=points[1:] or None,attrs=attrs,
                                auto=not loop_in_existing_void(group.mesh,points[0]))
        local = coplanar_scene(group.mesh,native_normal(points[0]),points[0][0])
        native.do(local)
        if native.face is None:
            raise ValueError("Nepodařilo se vytvořit plochu APP.")
        return native.face

    def material(current,name,color,alpha=1.):
        if name in current.materials:
            raise ValueError("Cílový materiál již existuje.")
        result = Material(name,tuple(v/255 for v in color),opacity=alpha)
        current.materials[name] = result
        return result

    def mutate(current):
        if action in ("box","pyramid"):
            neutral = material(current,"ASTRA LIVE test " + command["id"] + " neutral",[180,190,200])
            group = create_group(current,"live_"+command["id"],"ASTRA LIVE test - " + ("Kvadr" if action == "box" else "Jehlan"))
            dictionaries(group)["ArchControl_AstraLiveDemo"] = {"connection":command["connectionId"],"shape":action}
            rings = solid_rings(action,command["payload"]["origin"],command["payload"]["size"])
            for i,ring in enumerate(rings):
                add_face(group,[ring],neutral,{"attribute_dictionaries":{"ArchControl_AIRIS":{
                    "face_id":"f"+str(i),"confidence":"inferred","source":"LIVE test bez AI"}}})
        elif action == "colors":
            targets = [(g,dictionaries(g).get("ArchControl_AstraLiveDemo",{})) for g in current.groups]
            targets = [(g,d) for g,d in targets if d.get("connection") == command["connectionId"] and d.get("shape") in ("box","pyramid")]
            if not targets or len(targets)>40:
                raise ValueError("Nejdříve vytvořte kvádr nebo jehlan tímto propojením (nejvýše 40 komponent).")
            for i,(group,data) in enumerate(targets):
                paint = material(current,"ASTRA LIVE test " + command["id"] + " color"+str(i),
                                 [45,125,220] if data["shape"] == "box" else [235,130,45])
                for face in group.mesh.faces:
                    stamp_front(face.attrs,paint)
                    face.attrs["back"] = True
        elif action=="sync_model" or command.get("payload",{}).get("purpose")=="floor-report-layout":
            apply_live_edit(current,command,identities,create_group,material,add_face)
        else:
            p = command["payload"]
            refs = {}
            for spec in p["materials"]:
                name = model_material_name(spec,current.materials)
                validate_identity(current.materials,name)
                refs[spec["id"]] = material(current,name,spec["color"],.5 if spec["type"].upper() == "AB" else 1.)
                current.plugin_data.setdefault("archcontrol",{}).setdefault("material_dictionaries",{})[name] = {
                    "ArchControl_AIRIS":{"created_by":"AIRIS"}}
            for zone in p["zones"]:
                group = create_group(current,zone["nativeId"],zone["name"])
                dictionaries(group)["ArchControl_LiveModel"] = {"metadata":encode({
                    "projectId":p["projectId"],"zoneId":zone["id"],"sourceRevision":p["sourceRevision"],
                    "transferId":command["id"],"north":p.get("north"),"northSource":p.get("northSource"),"offset":p.get("offset")}).decode()}
                if zone["id"].startswith("epcp_"):
                    if current.layer("EP/CP") is None:
                        current.layers.append(Layer("EP/CP"))
                    group.layer = "EP/CP"
                specs = sorted((f for f in p["faces"] if f["zoneId"] == zone["id"]),
                               key=lambda f:bool(f.get("hostFaceId") or f.get("kind") in ("window","roof_window","door","attic_door")))
                for face in specs:
                    meta = {"attribute_dictionaries":{
                        "ArchControl_AIRIS":{"face_id":face["id"],"host_face_id":face.get("hostFaceId"),
                                             "source":face["source"],"confidence":face["confidence"]},
                        "ArchControl_LiveModel":{"binding":encode(binding(p,face,command)).decode()}}}
                    add_face(group,face["rings"],refs[face["constructionId"]],meta)
                actual = [f.attrs.get("archcontrol",{}).get("attribute_dictionaries",{}).get("ArchControl_AIRIS",{}).get("face_id") for f in group.mesh.faces]
                if len(actual) != len(specs) or sorted(actual) != sorted(f["id"] for f in specs):
                    raise ValueError("Nativní modelář změnil počet nebo ID ploch zóny; celá dávka se vrací.")
        captured = live_snapshot(current,identities)
        if len(encode(list(captured.values())))>5*1024*1024:
            raise ValueError("Výsledek příkazu překročil bezpečný limit pro dávku 6 MB.")
        return captured

    cmd = LiveMutationCommand(mutate)
    viewport.history.execute(cmd)
    if viewport.history.last_error or viewport.history.last_rejected:
        raise ValueError(viewport.history.last_error or viewport.history.last_rejected)
    viewport.notify_scene_changed()
    viewport.update()
    return cmd.captured


def apply_live_edit(scene,command,identities,create_group,material,add_face):
    """Addressed native edit inside LiveMutationCommand's rollback boundary."""
    import json
    from types import SimpleNamespace
    from PySide6.QtGui import QMatrix4x4,QVector3D
    from core.layers import Layer
    from .live import encode
    from .live_commands import validate_sync,validate_report,same_rings,binding,model_material_name
    from .core import parse_material_name
    p = command["payload"]
    report = p.get("purpose")=="floor-report-layout"
    (validate_report if report else validate_sync)(p)
    before = live_snapshot(scene,identities)
    if not all(before.get(e.get("id"))==e for e in p["expected"]):
        raise ValueError("Model se od odeslání změnil.")
    changed = {f["id"] for f in p["faces"]}|set(p.get("removed",[]))
    bound = [e for e in before.values() if e.get("binding",{}).get("projectId")==p["projectId"] and
             (e["binding"].get("zoneId","").startswith("epcp_") if report else e["binding"].get("faceId") in changed)]
    native = p.get("addressing")=="native-path-v1"
    if not native and sorted(e["id"] for e in bound)!=sorted(e["id"] for e in p["expected"]):
        raise ValueError("Plocha byla zkopírována nebo rozdělena.")

    def dictionaries(group):
        return (group.ext or {}).setdefault("archcontrol",{}).setdefault("attribute_dictionaries",{})

    # Same paths as live_snapshot, including its transparent imported root wrapper.
    contexts = {():SimpleNamespace(group=None,mesh=scene.loose_mesh,matrix=QMatrix4x4(),ancestors=[])}
    faces = {}
    def visit(group,matrix,path,ancestors):
        if group is not None:
            matrix = matrix*(group.xform if group.xform is not None else QMatrix4x4())
            ancestors = ancestors+[group]
            if not (group.ext or {}).get("archcontrol",{}).get("root_loose_faces"):
                path = (*path,identities.get(group,group.uid))
            elif contexts[()].mesh.faces:
                raise ValueError("Kořen má více samostatných sítí; před propojením je slučte nebo vložte do komponent.")
            mesh = group.mesh
            contexts[path] = SimpleNamespace(group=group,mesh=mesh,matrix=matrix,ancestors=ancestors)
        else:
            mesh = scene.loose_mesh
        for face in mesh.faces:
            pid = identities.get(face,face.attrs.get("archcontrol",{}).get("source_face_id"))
            faces["face:"+"/".join((*path,pid))] = (face,contexts[path])
        for child in (group.children if group is not None else scene.groups):
            visit(child,matrix,path,ancestors)
    visit(None,QMatrix4x4(),(),[])
    groups = list(all_groups(scene))

    def editable(context):
        if any(g.locked for g in context.ancestors):
            raise ValueError("Komponenta je zamčená.")
        if any(sum(g.mesh is ancestor.mesh for g in groups)>1 for ancestor in context.ancestors):
            raise ValueError("Sdílená definice má více instancí; před změnou ji osamostatněte.")
        inverse,ok = context.matrix.inverted()
        if not ok:
            raise ValueError("Komponenta má nevratnou transformaci.")
        return inverse

    def zone_context(zone):
        matches = [c for c in contexts.values() if c.group is not None and dictionaries(c.group).get("ArchControl_AIRIS",{}).get("zone_id")==zone["nativeId"]]
        if len(matches)!=1:
            raise ValueError("Zóna chybí nebo má duplicitní ID.")
        c = matches[0]
        editable(c)
        try:
            meta = dictionaries(c.group).get("ArchControl_LiveModel",{}).get("metadata","{}")
            meta = json.loads(meta) if isinstance(meta,str) else meta
        except (ValueError,TypeError):
            raise ValueError("Neplatná metadata zóny.")
        if meta.get("projectId")!=p["projectId"] or meta.get("zoneId")!=zone["id"]:
            raise ValueError("Zóna patří jinému projektu.")
        return c,meta

    if report:
        for zone in p["zones"]:
            c,meta = zone_context(zone)
            inverse = editable(c)
            specs = {f["id"]:f for f in p["faces"] if f["zoneId"]==zone["id"]}
            if c.group.children or len(c.mesh.faces)!=len(specs):
                raise ValueError("Počet reportových ploch se změnil nebo report obsahuje další objekty.")
            moves = {m["faceId"]:m for m in p["moves"] if m["zoneId"]==zone["id"]}
            positions = {}
            for face in c.mesh.faces:
                fid = face.attrs.get("archcontrol",{}).get("attribute_dictionaries",{}).get("ArchControl_AIRIS",{}).get("face_id")
                if fid not in moves:
                    raise ValueError("Chybí ID reportové plochy.")
                delta = QVector3D(*(v/1000 for v in moves[fid]["delta"]))
                for vertex in [*face.loop,*(v for ring in face.hole_loops for v in ring)]:
                    target = inverse.map(c.matrix.map(vertex.position)+delta)
                    if vertex in positions and (positions[vertex]-target).length()>.00002:
                        raise ValueError("Sdílený vrchol vyžaduje rozdílné posuny.")
                    positions[vertex] = target
                dictionaries_face = face.attrs["archcontrol"]["attribute_dictionaries"]
                dictionaries_face.setdefault("ArchControl_LiveModel",{}).update({
                    "binding":encode(binding(p,specs[fid],command)).decode(),
                    "report_floor":encode({k:v for k,v in moves[fid].items() if k!="delta"}).decode()})
                face.attrs.pop("layer",None)
            # Move loose edge endpoints as well if they share report vertices, like Ruby.
            for vertex,target in positions.items():
                c.mesh.place_vertex(vertex,target)
            for edge in c.mesh.edges:
                edge.layer = None
            if scene.layer("EP/CP") is None:
                scene.layers.append(Layer("EP/CP"))
            c.group.layer = "EP/CP"
            meta.update(reportLayout="in-place",sourceRevision=p["sourceRevision"])
            dictionaries(c.group)["ArchControl_LiveModel"]["metadata"] = encode(meta).decode()
    else:
        refs = {}
        for spec in p["materials"]:
            existing = scene.materials.get(spec.get("nativeMaterial")) if native else None
            fields = parse_material_name(existing.name) if existing else {}
            def numeric(value):
                return None if value in (None,"") else float(value)
            matching = existing is not None and (spec["type"]=="UN" or
                fields.get("typ")==spec["type"] and fields.get("var")=="V"+str(spec["variant"]) and
                all(numeric(fields.get(k))==spec.get(k) for k in ("u","g")))
            if matching and [round(v*255) for v in existing.color or ()]==spec["color"] and ("alpha" not in spec or (existing.opacity if existing.opacity is not None else 1)==spec["alpha"]):
                refs[spec["id"]] = existing
            else:
                name = "LIVE nezařazeno "+spec["id"] if native and spec["type"]=="UN" else model_material_name(spec,scene.materials)
                if name in scene.materials:
                    name += " "+command["id"]
                refs[spec["id"]] = material(scene,name,spec["color"],spec.get("alpha",1))
        work = p["containers"] if native else [{"zoneId":z["id"]} for z in p["zones"]]
        for container in work:
            zone = next(z for z in p["zones"] if z["id"]==container["zoneId"])
            if native:
                path = container["path"]
                if path is None:
                    group = create_group(scene,zone["nativeId"],zone["name"])
                    dictionaries(group)["ArchControl_LiveModel"] = {"metadata":encode({"projectId":p["projectId"],"zoneId":zone["id"]}).decode()}
                    c = SimpleNamespace(group=group,mesh=group.mesh,matrix=QMatrix4x4(),ancestors=[group])
                else:
                    c = contexts.get(tuple(path))
                    if c is None:
                        raise ValueError("Komponenta chybí.")
                inverse = editable(c)
                known = {i["nativeId"] for i in container["identities"]}
                actual = {key for key,(face,context) in faces.items() if context is c}
                if actual!=known:
                    raise ValueError("Obsah komponenty se změnil.")
                logical = {i["id"]:faces[i["nativeId"]][0] for i in container["identities"]}
                specs = [f for f in p["faces"] if f["id"] in container["faceIds"]]
                removed = container["removeIds"]
            else:
                c,_ = zone_context(zone)
                inverse = editable(c)
                logical = {}
                for face in c.mesh.faces:
                    fid = face.attrs.get("archcontrol",{}).get("attribute_dictionaries",{}).get("ArchControl_AIRIS",{}).get("face_id")
                    if fid is not None:
                        if fid in logical:
                            raise ValueError("Plocha má duplicitní logické ID.")
                        logical[fid] = face
                specs = [f for f in p["faces"] if f["zoneId"]==zone["id"]]
                removed = [fid for fid in p["removed"] if any(e["binding"]["faceId"]==fid and e["binding"]["zoneId"]==zone["id"] for e in p["expected"])]
            expected = {((next(t["id"] for t in p["targets"] if t["nativeId"]==e["id"])) if native else e["binding"]["faceId"]):e for e in p["expected"]}
            geometry = [f for f in specs if f["id"] not in expected or not same_rings(f["rings"],expected[f["id"]]["rings"])]
            orphan_candidates = set()
            for fid in [*removed,*(f["id"] for f in geometry if f["id"] in expected)]:
                if fid not in logical:
                    raise ValueError("Původní plocha chybí.")
                orphan_candidates.update(e for e in c.mesh.edges if logical[fid] in e.faces)
                c.mesh.remove_face(logical[fid])
                del logical[fid]
            for edge in orphan_candidates:
                if not edge.faces:
                    c.mesh.remove_edge(edge)
            for spec in sorted(geometry,key=lambda f:bool(f.get("hostFaceId"))):
                rings = [[inverse.map(QVector3D(*(v/1000 for v in point))) for point in ring] for ring in spec["rings"]]
                local = [[[point.x()*1000,point.y()*1000,point.z()*1000] for point in ring] for ring in rings]
                logical[spec["id"]] = add_face(c,local,refs[spec["constructionId"]],{})
            for spec in specs:
                face = logical.get(spec["id"])
                if face is None or face not in c.mesh.faces:
                    raise ValueError("Nativní modelář změnil ID plochy.")
                stamp_front(face.attrs,refs[spec["constructionId"]])
                face.attrs["back"] = True
                data = face.attrs.setdefault("archcontrol",{}).setdefault("attribute_dictionaries",{})
                data.setdefault("ArchControl_AIRIS",{}).update(face_id=spec["id"],host_face_id=spec.get("hostFaceId"))
                data.setdefault("ArchControl_LiveModel",{})["binding"] = encode(binding(p,spec,command)).decode()
    after = live_snapshot(scene,identities)
    affected = {e["id"] for e in p["expected"]}
    if any(after.get(key)!=item for key,item in before.items() if key not in affected):
        raise ValueError("Změna zasáhla jiné prvky; celá dávka se vrací.")
    for spec in p["faces"]:
        matches = [e for e in after.values() if e.get("binding",{}).get("projectId")==p["projectId"] and e["binding"].get("faceId")==spec["id"] and e["binding"].get("transferId")==command["id"]]
        if len(matches)!=1 or not same_rings(matches[0]["rings"],spec["rings"]):
            raise ValueError("Nativní modelář změnil výslednou geometrii.")
        if report:
            old = next(e for e in p["expected"] if e["binding"]["faceId"]==spec["id"])
            if matches[0]["id"]!=old["id"] or matches[0]["layer"]!="EP/CP" or any(matches[0].get(k)!=old.get(k) for k in ("material","color","alpha")):
                raise ValueError("Změnila se topologie nebo materiál EP/CP.")
    if any(e.get("binding",{}).get("projectId")==p["projectId"] and e["binding"].get("faceId") in p.get("removed",[]) for e in after.values()) or native and any(t["nativeId"] in after for t in p["targets"] if t["id"] in p["removed"]):
        raise ValueError("Smazaná plocha zůstala v modelu.")


def native_normal(points):
    from PySide6.QtGui import QVector3D
    normal = QVector3D()
    for a,b in zip(points,[*points[1:],points[0]]):
        normal += QVector3D.crossProduct(a-points[0],b-points[0])
    return normal.normalized()


_live_threads = {}


def live_controller(service):
    """Qt lifetime/thread boundary. Workers receive immutable plain requests."""
    from PySide6.QtCore import QObject, QTimer, Signal, Slot, Qt
    from PySide6.QtWidgets import QApplication
    from threading import Event, Thread
    from .live import LiveSession
    from .live_transport import post

    class Worker(QObject):
        completed = Signal(object)

        def __init__(self, request, stopping):
            super().__init__()
            self.request = request
            self.stopping = stopping

        @Slot()
        def run(self):
            status, body = post(self.request)
            if not self.stopping.is_set():
                self.completed.emit((self.request, status, body))

    class Controller(QObject):
        updated = Signal(object)

        def __init__(self):
            super().__init__(service.app.window)
            self.session = LiveSession()
            self._scene = self._document_data = None
            self._source = None
            self._version = None
            self._identities = LiveIdentities()
            self._threads = set()
            self._stopping = Event()
            self._timer = QTimer(self)
            self._timer.setInterval(350)
            self._timer.timeout.connect(self.tick)
            QApplication.instance().aboutToQuit.connect(self.shutdown)

        def editing(self):
            return service.app.scene.edit_group is not None

        def publish(self):
            self.updated.emit(self.session.public_status(self.editing()))

        @staticmethod
        def source(scene):
            return scene.plugin_data.get("archcontrol", {}).get("import", {}).get("sha256")

        def connect_app(self, url, code):
            title = service.app.window._import_name or (service.app.window._current_path.name if service.app.window._current_path else "EnergySketch — bez názvu")
            self.session.connect(url, code, title, ("presence-v1","demo-solids-v1","model-import-v1",
                                                   "model-sync-v1","manual-sync-v1","report-layout-v1"))
            self._scene = service.app.scene
            self._document_data = self._scene.plugin_data
            self._source = self.source(self._scene)
            self._version = self._scene.content_version
            self._identities = LiveIdentities()
            self._timer.start()
            self.tick()

        def disconnect(self):
            self._timer.stop()
            self.session.disconnect()
            self._scene = self._document_data = None
            self._identities = LiveIdentities()
            self.publish()

        def pause(self):
            self.session.toggle_pause()
            self.publish()

        def on_change(self):
            scene = service.app.scene
            if self._version != scene.content_version:
                self._version = scene.content_version
                self.session.dirty()

        @Slot()
        def reap(self):
            # QObject wrappers are released only on the GUI thread and AFTER
            # the Python worker returned. No running QThread can be destroyed.
            for thread, worker in list(_live_threads.items()):
                if not thread.is_alive():
                    _live_threads.pop(thread, None)
                    self._threads.discard(thread)
                    worker.deleteLater()

        @Slot()
        def tick(self):
            self.reap()
            scene = service.app.scene
            if self._scene is not None and (scene is not self._scene or scene.plugin_data is not self._document_data or self.source(scene) != self._source):
                self.disconnect()
                self.session.status = "Dokument se změnil. Propojte nový model výslovně znovu."
            self.on_change()
            try:
                request = self.session.next_request(lambda: live_snapshot(scene,self._identities), self.editing(),
                    lambda command:execute_live_command(service,command,self._identities))
            except Exception as exc:
                self.session.paused = True
                self.session.status = str(exc)
                request = None
            if request is not None:
                worker = Worker(request, self._stopping)
                thread = Thread(target=worker.run, daemon=True, name="EnergySketch LIVE HTTP")
                self._threads.add(thread)
                _live_threads[thread] = worker
                worker.completed.connect(self.completed, Qt.QueuedConnection)
                thread.start()
            self.publish()

        @Slot(object)
        def completed(self, result):
            request, status, body = result
            self.session.complete(request, status, body)
            QTimer.singleShot(100, self.reap)
            self.publish()

        def shutdown(self):
            self._timer.stop()
            self._stopping.set()
            self.session.disconnect()
            for thread in list(self._threads):
                if not thread.is_alive():
                    worker = _live_threads.pop(thread, None)
                    if worker is not None:
                        worker.deleteLater()
                    self._threads.discard(thread)

    return Controller()


class LiveIdentities:
    """Connection-local native identity; no token or identity registry in IGZ."""
    def __init__(self):
        self.objects, self.used = {}, {}

    def get(self, entity, preferred=None):
        if entity in self.objects:
            return self.objects[entity]
        import re
        key = str(preferred if preferred is not None else id(entity))
        if not re.fullmatch(r"[1-9]\d{0,19}", key):
            key = str((int.from_bytes(hashlib.blake2b(key.encode(), digest_size=8).digest(), "big") & ((1<<63)-1)) + 1)
        while key in self.used and self.used[key] is not entity:
            key = str(int(key)+1)
        self.used[key], self.objects[entity] = entity, key
        return key


def live_snapshot(scene, identities=None):
    """Same Ruby entity envelope, world millimetres, inherited paint/visibility."""
    from PySide6.QtGui import QMatrix4x4
    from decimal import Decimal, ROUND_HALF_UP
    import json
    import math
    import re
    identities = identities or LiveIdentities()
    result = {}

    def point(vector, matrix):
        v = matrix.map(vector)
        raw = (v.x()*1000, v.y()*1000, v.z()*1000)
        if not all(math.isfinite(x) and abs(x) <= 1e8 for x in raw):
            raise ValueError("LIVE: souřadnice je neplatná nebo mimo rozsah ±100 km.")
        return [float(Decimal(str(x)).quantize(Decimal('.000001'), rounding=ROUND_HALF_UP)) for x in raw]

    def effective_layer(name, inherited):
        return inherited if name in (None,"", "Layer0", "Untagged", "Default") and inherited else name or "Layer0"

    def hidden_layer(name):
        layer = scene.layer(name)
        return layer is not None and not layer.visible

    def mesh_items(mesh, matrix, ids, labels, inherited_material=None, inherited_hidden=False, inherited_layer=None):
        for kind, entities in (("face", mesh.faces), ("edge", [e for e in mesh.edges if not e.faces])):
            for entity in entities:
                attrs = entity.attrs if kind == "face" else {}
                meta = attrs.get("archcontrol", {})
                fid = identities.get(entity, meta.get("source_face_id"))
                key = kind + ":" + "/".join([*ids, fid])
                if len(key) > 200 or key in result:
                    raise ValueError("LIVE: příliš dlouhá nebo duplicitní cesta prvku.")
                material = attrs.get("mat") or inherited_material or ""
                back = attrs.get("back")
                if back is True:
                    back = attrs
                if isinstance(back, dict) and (not material or re.match(r"\A(?:EP|CV)-\d", back.get("mat", ""), re.I)):
                    material = back.get("mat", "")
                layer = effective_layer(attrs.get("layer") if kind == "face" else entity.layer, inherited_layer)
                hidden = inherited_hidden or bool(attrs.get("hidden") if kind == "face" else entity.hidden) or hidden_layer(layer)
                item = {"id": key, "kind": kind, "zoneId": ids[0] if ids else "root",
                        "zone": labels[0] if labels else "Mimo komponentu", "material": material,
                        "hidden": bool(hidden), "layer": layer}
                entry = scene.materials.get(material)
                color = entry.color if entry else attrs.get("color")
                if color is not None:
                    item["color"] = [max(0,min(255,int(float(c)*255+.5))) for c in color[:3]]
                    alpha = entry.opacity if entry else attrs.get("opacity")
                    item["alpha"] = 1. if alpha is None else float(alpha)
                if kind == "face":
                    binding = meta.get("attribute_dictionaries", {}).get("ArchControl_LiveModel", {}).get("binding")
                    if isinstance(binding, str) and len(binding.encode("utf-8")) < 2000:
                        try:
                            item["binding"] = json.loads(binding)
                        except ValueError as exc:
                            raise ValueError("LIVE: plocha má neplatnou vazbu na APP.") from exc
                    elif isinstance(binding, dict):
                        item["binding"] = copy.deepcopy(binding)
                    item["rings"] = [[point(v,matrix) for v in loop] for loop in (entity.vertices, *entity.holes)]
                else:
                    item["points"] = [point(entity.a,matrix),point(entity.b,matrix)]
                result[key] = item
                if len(result) > 50000:
                    raise ValueError("LIVE podporuje nejvýše 50 000 prvků.")

    def walk(group, matrix, ids, labels, material=None, hidden=False, layer=None):
        if len(ids) >= 32:
            raise ValueError("LIVE: příliš hluboké vnoření komponent.")
        own_matrix = matrix * (group.xform if group.xform is not None else QMatrix4x4())
        if not (group.ext or {}).get("archcontrol", {}).get("root_loose_faces"):
            ids = [*ids, identities.get(group, group.uid)]
            labels = [*labels, group.name or "Komponenta " + ids[-1]]
        layer = effective_layer(group.layer, layer)
        hidden = hidden or group.hidden or hidden_layer(layer)
        material = (group.material or {}).get("mat") or material
        mesh_items(group.mesh,own_matrix,ids,labels,material,hidden,layer)
        for child in group.children:
            walk(child,own_matrix,ids,labels,material,hidden,layer)

    mesh_items(scene.loose_mesh,QMatrix4x4(),[],[])
    for group in scene.groups:
        walk(group,QMatrix4x4(),[],[])
    return result


def window_tool(service, parameters):
    from PySide6.QtGui import QMatrix4x4
    from tools.base import Tool
    from tools.select import SelectTool

    class WindowTool(Tool):
        name = "ArchControl — Mřížka oken"
        description = "Klikněte na fasádu do středu mřížky oken. Esc ukončí nástroj."

        def __init__(self):
            self.rectangles = []
            self.pid = None
            self.point = None

        def on_activate(self, viewport):
            viewport.flash_status(self.description, 6000)

        def on_deactivate(self, viewport):
            self.rectangles = []

        def on_hover(self, ctx):
            self.rectangles, self.pid = [], None
            scene = service.app.scene
            face, placement = ctx.viewport.pick_face_placement(ctx.screen.x(), ctx.screen.y())
            if face is not None:
                wanted = placement.xform if placement is not None and placement.xform is not None else QMatrix4x4()
                for pid, candidate, owner in face_handles(scene):
                    if candidate is not face:
                        continue
                    if placement is None and owner is not scene.edit_group:
                        continue
                    level, matrix = scene.groups, QMatrix4x4()
                    for uid in pid.split("/")[:-1]:
                        group = next(g for g in level if g.uid == uid)
                        if group.xform is not None:
                            matrix = matrix * group.xform
                        level = group.children
                    if placement is not None and any(abs(a-b) > 1e-5 for a,b in zip(matrix.data(), wanted.data())):
                        continue
                    self.pid = pid
                    self.point = (ctx.world.x(), ctx.world.y(), ctx.world.z())
                    try:
                        self.rectangles = service.window_geometry(pid, self.point, parameters)
                    except ValueError:
                        self.pid = None
                    break
            ctx.viewport.update()

        def on_click(self, ctx):
            self.on_hover(ctx)
            if self.pid is None:
                ctx.viewport.flash_status("Klikněte na plochu fasády.", 5000)
                return
            try:
                count = service.insert_window_grid(self.pid, self.point, parameters)
            except ValueError as exc:
                ctx.viewport.flash_status(str(exc), 6000)
                return
            ctx.viewport.set_active_tool(SelectTool())
            ctx.viewport.flash_status(f"Vloženo {count} oken. Zpět vrátí celou mřížku.", 6000)

        def on_cancel(self, viewport):
            viewport.set_active_tool(SelectTool())

    return WindowTool()


def window_overlay(app, viewport, painter):
    from PySide6.QtCore import QPointF
    from PySide6.QtGui import QColor, QPen, QPolygonF
    tool = viewport.active_tool
    if tool is None or tool.name != "ArchControl — Mřížka oken":
        return
    rectangles = tool.rectangles
    if not rectangles:
        return
    points = [(v.x(), v.y(), v.z()) for rect in rectangles for v in rect]
    x, y, front = app.world_to_pixels(points)
    painter.setPen(QPen(QColor("#dc1e1e"), 2))
    for i in range(0, len(points), 4):
        if all(front[i:i+4]):
            poly = [QPointF(float(x[j]), float(y[j])) for j in range(i, i+4)]
            painter.drawPolyline(QPolygonF([*poly, poly[0]]))


def face_handles(scene):
    """The same placement PID convention as face_records, with live handles."""
    def mesh_faces(mesh, path, owner):
        for face in mesh.faces:
            fid = face.attrs.get("archcontrol", {}).get("source_face_id", id(face))
            yield "/".join([*path, str(fid)]), face, owner
    def walk(group, path):
        path = [*path, group.uid]
        yield from mesh_faces(group.mesh, path, group)
        for child in group.children:
            yield from walk(child, path)
    yield from mesh_faces(scene.loose_mesh, [], None)
    for group in scene.groups:
        yield from walk(group, [])


def wears(attrs, name):
    back = attrs.get("back")
    return attrs.get("mat") == name or isinstance(back, dict) and back.get("mat") == name


def stamp_front(attrs, material):
    from core.mesh import PAINT_KEYS
    # A shared back=True denotes the old front recipe. Preserve that side
    # when changing only the front, as a native two-sided paint operation.
    if attrs.get("back") is True:
        attrs["back"] = {k: copy.deepcopy(attrs[k]) for k in PAINT_KEYS if k in attrs}
    for key in (*PAINT_KEYS, "uv"):
        attrs.pop(key, None)
    if material is not None:
        attrs.update(copy.deepcopy(material.face_attrs()))


def restamp(attrs, name, material):
    front = attrs.get("mat") == name
    back = attrs.get("back")
    if back is True and front:
        # Both sides followed this one material before the edit.
        attrs.pop("back")
        stamp_front(attrs, material)
        if material is not None:
            attrs["back"] = True
    else:
        if front:
            stamp_front(attrs, material)
        if isinstance(back, dict) and back.get("mat") == name:
            if material is None:
                attrs.pop("back", None)
            else:
                attrs["back"] = copy.deepcopy(material.face_attrs())


class MaterialStateCommand:
    """Small attr/registry transaction, including metadata and both sides."""
    def __init__(self, action, faces=(), groups=()):
        self.action = action
        self.faces = set(faces)
        self.groups = list(groups)
        self.before = self.after = None

    def capture(self, scene):
        return (dict(scene.materials), copy.deepcopy(scene.plugin_data.get("archcontrol")),
                [(f, copy.deepcopy(f.attrs)) for f in self.faces],
                [(g, copy.deepcopy(g.material), g.hidden) for g in self.groups], scene.georef)

    @staticmethod
    def restore(scene, state):
        from core.history import _dirty_group_chunks
        registry, data, faces, groups, georef = state
        scene.georef = georef
        scene.materials.clear()
        scene.materials.update(registry)
        if data is None:
            scene.plugin_data.pop("archcontrol", None)
        else:
            scene.plugin_data["archcontrol"] = copy.deepcopy(data)
        for face, attrs in faces:
            face.attrs.clear()
            face.attrs.update(copy.deepcopy(attrs))
        for group, material, hidden in groups:
            group.material = copy.deepcopy(material)
            group.hidden = hidden
        _dirty_group_chunks(scene)
        scene.version += 1

    def do(self, scene):
        if self.before is None:
            self.before = self.capture(scene)
            try:
                self.action(scene)
                self.after = self.capture(scene)
            except BaseException:
                self.restore(scene, self.before)
                raise
        self.restore(scene, self.after)

    def undo(self, scene):
        self.restore(scene, self.before)


def setup_extension(app):
    from .ui import ArchControlPanel
    from .materials_ui import MaterialPalette, MaterialDialog
    from .zones_ui import ZonePalette
    from .windows_ui import WindowGridDialog
    from .help_ui import HelpDialog
    from .live_ui import LivePanel
    service = PanelService(app)
    app.add_context_menu(lambda menu, selection: section_slice_context_menu(service, menu, selection))
    app.window._skp_import_handler = service.import_path
    panel = ArchControlPanel(service)
    dock = app.add_panel("ArchControl", panel)
    menu = app.add_menu("ArchControl")
    palette = MaterialPalette(service)
    palette_dock = app.add_panel("Materiály ArchControl", palette, name="materials", start_hidden=True)
    def material_sampled(name):
        palette.select_sampled_material(name)
        app.show_panel(palette_dock)
    app.on_material_sampled(material_sampled)
    zones = ZonePalette(service)
    zone_dock = app.add_panel("Zóny ArchControl", zones, name="zones", start_hidden=True)
    for report, report_dock in ((panel, dock), (palette, palette_dock), (zones, zone_dock)):
        report.bind_dock(report_dock)
    live = live_controller(service)
    live_panel = LivePanel(live)
    live_dock = app.add_panel("ASTRA LIVE", live_panel, name="astra-live", start_hidden=True)
    from .toolbar import create_toolbar
    app.window._archcontrol_toolbar = create_toolbar(app.window, menu, [
        ("panel", "Otevřít panel", "Tabulka ploch, sever modelu a energetické reporty.", lambda: app.show_panel(dock)),
        ("live", "ASTRA LIVE propojení", "Otevřít propojení modelu s APP.", lambda: app.show_panel(live_dock)),
        ("materials", "Paleta materiálů", "Materiály, barvy a rychlé akce u každého materiálu.", lambda: app.show_panel(palette_dock)),
        ("zones", "Paleta zón", "Zóny, jejich objemy a obálka.", lambda: app.show_panel(zone_dock)),
        ("material_new", "Nový materiál…", "Vytvořit stavební materiál ArchControl.", lambda: MaterialDialog(service, parent=app.window).exec()),
        ("windows", "Vložit mřížku oken na fasádu…", "Rozmístit okna na vybranou fasádu.", lambda: WindowGridDialog(service, app.window).exec()),
        ("library_import", "Import knihovny materiálů JSON…", "Načíst knihovnu materiálů ve formátu JSON.", lambda: palette.run(palette.import_library)),
        ("library_export", "Export knihovny materiálů JSON…", "Uložit knihovnu materiálů ve formátu JSON.", lambda: palette.run(palette.export_library)),
        ("csv_complex", "Komplexní CSV…", "Exportovat komplexní tabulku ploch.", lambda: panel.export_dialog("complex")),
        ("csv_energy", "Energie — zóny CSV…", "Exportovat energetické plochy podle zón.", lambda: panel.export_dialog("energy")),
        ("csv_rp", "Renovační pas CSV…", "Exportovat Renovační pas se shodnými výpočty původního pluginu.", lambda: panel.export_dialog("rp")),
        ("north", "Sever dvěma body", "Kliknout na počáteční bod a potom ve směru severu; Esc ukončí nástroj.", service.start_north_tool),
        ("help", "Nápověda ArchControl", "Otevřít místní návod k ArchControlu.", lambda: HelpDialog(app.window).exec()),
    ])
    menu.addSeparator()
    menu.addAction("Importovat .skp se zónami…", service.import_file)
    app.on_document_changed(live.on_change)
    app.add_overlay(lambda viewport, painter: north_overlay(app, viewport, painter))
    app.add_overlay(lambda viewport, painter: window_overlay(app, viewport, painter))
    last_report_version = None
    def reports_changed():
        nonlocal last_report_version
        key = (id(app.scene), app.scene.version)
        if key != last_report_version:
            last_report_version = key
            for report in (panel, palette, zones):
                report.schedule_refresh()
    app.on_document_changed(reports_changed)
    panel.refresh()
