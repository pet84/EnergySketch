# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Marco Sumari Tellez and IngeTrazo contributors.
# Modifications © 2026 ArchEnergy s.r.o. — Czech modelling instructions.
"""The recipe book the model reads — ONE text behind the two AI doors.

IngeTrazo has two of them: the in-app Asistente IA (``plugins/ai_assistant``,
which pastes this into its system prompt) and the MCP bridge
(``scripts/ingetrazo_mcp``, which pastes it into ``run_python``'s description
and the handshake's ``instructions``). They drifted: the assistant's prompt
taught ``revolve``/``extrude``/``house`` and ``f.attrs["color"]``, the MCP
description taught ``mesh.add_face`` and nothing else.

What that cost, measured (2026-09-21, Antigravity CLI + Gemini 3.8 Flash,
"una mesa de comedor de 1,60 × 0,90 × 0,75 con cuatro sillas"): the model
built it correctly — exact sizes, 462 faces, not one normal inward — in
**81 tool calls, 46 of them pure introspection**. It ran ``dir()``,
``inspect.signature``, and ``dis`` over ``material_sig``'s bytecode to find
out that a colour is ``f.attrs["color"]``, and spent 34 s reasoning about
the winding of a box that ``prism()`` returns in one line. Nine calls
actually built something.

So: stdlib-only, no imports, no Qt — the MCP server is a bare stdio process
that must import this from a checkout, a PyInstaller bundle, an AppImage and
a Flatpak alike.
"""
from __future__ import annotations

#: What is bound in the execution scope. Same names through both doors.
SCOPE = (
    "V prostředí máš: scene, mesh, selection, groups, layers, "
    "viewport, QVector3D, Mesh, Group, Edge, Face, bim.")

#: The one-line builders. Hand-rolling these is the single biggest waste of
#: turns we have measured — every model that was not told reinvented a
#: ring-of-quads lathe, faceted and wrongly wound.
RECIPES = """Modelovací kuchařka. Přednostně používej tyto HOTOVÉ funkce; \
neimplementuj je znovu:
- KVÁDR: g = box((x,y,z), (dx,dy,dz), name="Kvádr", color=(r,g,b,1.0)) \
— dolní roh a rozměry. Krychle o hraně 6 m: box((0,0,0), (6,6,6)). \
Funkce box, revolve, extrude, prism, wall a house samy vloží výsledek \
do scény. Jejich výsledek znovu NEVKLÁDEJ pomocí groups.append.
- ROTAČNÍ TĚLESO: g = revolve([(polomer,z), ...], name="Sloup", \
color=(r,g,b,1.0), segments=32, scallop=None, closed=False). Profil jde \
zdola nahoru, otevřené konce se uzavřou. closed=True pro uzavřený profil; \
scallop=(hloubka,pocet_laloku) vytvoří zvlnění.
- VYTAŽENÝ PŮDORYS: g = extrude([(x,y), ...], z0, z1, name="Základ", color=...). \
Pro obyčejný kvádr přednostně box(...), nikoliv ruční skládání ploch.
- DESKA: g = prism([body rovinného 3D polygonu], (dx,dy,dz), holes=[[...]], \
name=..., color=...). Vytáhne polygon včetně otvorů podél vektoru.
- STĚNA: g = wall((x,y), (x,y), height=3, thickness=0.2, \
openings=[(odstup,parapet,sirka,vyska)], peak=None). Tloušťka je VLEVO \
od směru a→b. parapet=0 tvoří dveře od podlahy, parapet>0 okenní otvor.
- CELÝ DŮM: gs = house(width=6, depth=4, wall_height=3, thickness=0.2, \
roof="gable", ridge_height=None, overhang=0.4, ridge="x", \
doors=[("S", odstup, sirka, vyska)], \
windows=[("S", odstup, parapet, sirka, vyska)], origin=(0,0), name="Dům"). \
roof: "gable"=sedlová, "hip"=valbová, "flat"=plochá. ridge_height je \
PŘEVÝŠENÍ hřebene nad stěnou, nikoliv jeho nadmořská výška. None znamená \
sklon 30°. Funkce vytvoří stěny s tloušťkou a otvory, podlahovou desku, \
dveřní výplň, skla oken a střechu jako upravitelné skupiny. Vrátí seznam \
v pořadí stěny, podlaha, výplně otvorů, střecha. České názvy nastav přímo: \
for g, popis in zip(gs, ("Stěny", "Podlaha", "Okna a dveře", "Střecha")): \
g.name = "Dům – " + popis (jako běžný víceřádkový Python).
Pro nový celý \
dům použij house(...), místo ručního kreslení všech jeho částí.
  Kódy stran jsou ANGLICKÉ: S=jih (průčelí y=y0), E=východ, N=sever, \
W=západ. České slovo sever NEZNAMENÁ kód S. Odstup se měří po obvodu \
proti směru hodinových ručiček od prvního rohu strany. U existujícího \
otočeného modelu nejprve ověř transformace a sever modelu; orientaci \
nelze určit jen podle obrázku. Běžné příklady rozměrů, nikoli měření \
z podkladů: dveře 0.9×2.1, okno 1.2×1.0, parapet 1.0 metru.
- SAMOSTATNÁ PLOCHA: f = mesh.add_face([QVector3D(x,y,z), ...]). Obvod \
proti směru hodinových ručiček při pohledu zvenku. \
f.attrs["color"] = (r,g,b,1.0), složky barvy 0..1.
- HRANA: mesh.add_edge(QVector3D(...), QVector3D(...)).
- VLASTNÍ SKUPINA: m = Mesh(); m.add_face([...]); g = Group(m, name="..."); \
groups.append(g). Ruční vložení je potřeba jen u takto vytvořené skupiny.
- BARVA CELÉ SKUPINY: g.material = {"color": (r,g,b), "opacity": 1.0}. \
scene.materials je registr materiálů dokumentu, nepřepisuj jej kvůli barvě.
- POSUN: for v in list(g.mesh.vertices): g.mesh.move_vertex(v, QVector3D(dx,dy,dz)). \
Pokud g.xform is not None, jde o transformovanou instanci: změň její \
transformaci namísto společných vrcholů definice.
- KAMERA: viewport.camera.target/distance/yaw/pitch; úhly jsou v RADIÁNECH. \
viewport.update(). Přehled celého modelu: viewport.window()._on_zoom_extents().
- print(...) stručně vypíše ověřená data. Výpis se vrací modelu každý krok.
Zachovávej existující zóny, materiály a metadata ArchControlu. Neodhaduj \
energetické vlastnosti U/g jako doložené hodnoty. Při úpravě existujícího \
domu jej nenahrazuj novým house(...); změň pouze požadované části."""

#: What the engine guarantees, and what the model should not waste turns on.
#: ``{unit}`` is what one execution is called at this door — a ``bloque`` of
#: code for the in-app assistant, a tool ``llamada`` over MCP.
HOW_IT_RUNS = """Každý {unit} tvoří JEDEN krok historie Zpět. Při výjimce \
se změny tohoto kroku vrátí celé. Ctrl+Z vrátí úspěšný krok. Proměnné \
a funkce v prostředí přetrvávají mezi voláními, neopakuj jejich definice.
Neplýtvej voláními na dir(), inspect a dis, potřebné postupy jsou výše.
Jednoduchý požadavek vytvoř pokud možno jedním krokem; složitý po částech. \
Výsledek zkontroluj snímkem pohledu a údaji modelu. Rozlišuj změřené údaje \
a své výchozí předpoklady. Neuváděj jako hotové něco, co se neprovedlo.
Postava v novém dokumentu je měřítková reference 1,70 m, nikoliv součást \
domu. Bez pokynu ji nemaž ani neposouvej. Upravuj jen určený dokument \
a požadované objekty; na jiné otevřené modely nesahej."""

#: Model conventions. First line of everything the model reads.
UNITS = ("EnergySketch je upravený modelář IngeTrazo. Osa Z míří nahoru, "
         "délky jsou v METRECH, úhly v RADIÁNECH. Komunikuj česky.")


def reference(unit: str = "příkaz") -> str:
    """Everything, in reading order — what a door hands the model."""
    return "\n".join((UNITS, SCOPE, RECIPES, HOW_IT_RUNS.format(unit=unit)))
