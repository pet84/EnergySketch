"""Generuje SVG balíček EnergySketch (ikona F: drátěná kostička s modrým vrškem)."""
import glob, os, sys
from fontTools.ttLib import TTFont
from fontTools.varLib.instancer import instantiateVariableFont
from fontTools.pens.svgPathPen import SVGPathPen
from fontTools.pens.boundsPen import BoundsPen
from fontTools.pens.transformPen import TransformPen

OUT = sys.argv[1]
FONT = sys.argv[2]  # Path to a licensed Plus Jakarta Sans font, supplied explicitly.
NAVY = "#0B1B3A"      # hrany kostičky (stejně jako app-cube-line.svg)
TEXT = "#1B2E4A"      # nápis (odstín z loga energyapp)
os.makedirs(os.path.join(OUT, "svg"), exist_ok=True)

GRAD = ('<linearGradient id="esT" x1="0" y1="0" x2="1" y2="1">'
        '<stop offset="0" stop-color="#5ED8FF"/><stop offset="1" stop-color="#2AB2F7"/></linearGradient>')

TOP = ("M587.4,161.5 Q627,140 666.6,161.5 L1020.4,353.5 Q1060,375 1020.4,396.5 L642.8,601.4 "
       "Q627,610 611.2,601.4 L233.6,396.5 Q194,375 233.6,353.5 Z")
HEX = ("M587.4,161.5 Q627,140 666.6,161.5 L1020.4,353.5 Q1060,375 1060,420 L1060,820 Q1060,865 1020.4,886.5 "
       "L666.6,1078.5 Q627,1100 587.4,1078.5 L233.6,886.5 Q194,865 194,820 L194,420 Q194,375 233.6,353.5 Z")
YYY = "M203.9,380.9 L627,610 L1050.1,380.9 M627,610 L627,1089.3"
EDGE = 50  # schváleno 18. 10. 2026; pro 16–32 px se používá 80 (energysketch-ikona-maly.svg)

def cube(edge, top="url(#esT)", width=EDGE):
    return (f'<path d="{TOP}" fill="{top}"/>'
            f'<g fill="none" stroke="{edge}" stroke-width="{width}" stroke-linejoin="round" stroke-linecap="round">'
            f'<path d="{HEX}"/><path d="{YYY}"/></g>')

# Kostička: vnější obrys (střed hrany ± půl tloušťky): 194..1060 × 140..1100
CX0, CY0, CW, CH = 194 - EDGE / 2, 140 - EDGE / 2, 866 + EDGE, 960 + EDGE

def svg(vb, body, title):
    return (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="{vb}" role="img"><title>{title}</title>'
            f'<defs>{GRAD}</defs>{body}</svg>\n')

def write(name, content):
    with open(os.path.join(OUT, "svg", name), "w", encoding="utf-8", newline="\n") as f:
        f.write(content)

# --- ikony ---
# čtverec: šířka doplněná na výšku, kostička na střed (okraj 40 kvůli silnější hraně u malé verze)
PAD = 40
side = CH + 2 * PAD
vx = CX0 + CW / 2 - side / 2
vy = CY0 - PAD
vb_icon = f"{vx:.0f} {vy:.0f} {side:.0f} {side:.0f}"
write("energysketch-ikona.svg", svg(vb_icon, cube(NAVY), "EnergySketch"))
write("energysketch-ikona-maly.svg", svg(vb_icon, cube(NAVY, width=80), "EnergySketch"))
write("energysketch-ikona-pro-tmave-pozadi.svg", svg(vb_icon, cube("#FFFFFF"), "EnergySketch"))
write("energysketch-ikona-maly-pro-tmave-pozadi.svg", svg(vb_icon, cube("#FFFFFF", width=80), "EnergySketch"))
write("energysketch-ikona-mono.svg", svg(vb_icon, cube(NAVY, top=NAVY), "EnergySketch"))
write("energysketch-ikona-mono-bila.svg", svg(vb_icon, cube("#FFFFFF", top="#FFFFFF"), "EnergySketch"))

# ikona aplikace: zaoblený čtverec, kostička 64 % plochy
tile = CH / 0.64
tx = CX0 + CW / 2 - tile / 2
ty = CY0 + CH / 2 - tile / 2
vb_tile = f"{tx:.1f} {ty:.1f} {tile:.1f} {tile:.1f}"
rx = tile * 0.22
for name, bg, edge, w in [("energysketch-ikona-aplikace-svetla.svg", "#FFFFFF", NAVY, EDGE),
                          ("energysketch-ikona-aplikace-svetla-maly.svg", "#FFFFFF", NAVY, 80),
                          ("energysketch-ikona-aplikace-tmava.svg", NAVY, "#FFFFFF", EDGE),
                          ("energysketch-ikona-aplikace-tmava-maly.svg", NAVY, "#FFFFFF", 80)]:
    body = (f'<rect x="{tx:.1f}" y="{ty:.1f}" width="{tile:.1f}" height="{tile:.1f}" rx="{rx:.1f}" fill="{bg}"/>'
            + cube(edge, width=w))
    write(name, svg(vb_tile, body, "EnergySketch"))

# --- nápis z Plus Jakarta Sans (800 + 400), převedený na křivky ---
def instance(w):
    return instantiateVariableFont(TTFont(FONT), {"wght": w}, inplace=False)

def kern_table(font):
    """Párové vyrovnání z GPOS (PairPos formát 1 a 2)."""
    pairs = {}
    if "GPOS" not in font:
        return pairs
    gpos = font["GPOS"].table
    for lookup in gpos.LookupList.Lookup:
        subs = lookup.SubTable
        if lookup.LookupType == 9:
            subs = [s.ExtSubTable for s in subs]
        elif lookup.LookupType != 2:
            continue
        for st in subs:
            if getattr(st, "LookupType", 2) != 2:
                continue
            cov = st.Coverage.glyphs
            if st.Format == 1:
                for i, g1 in enumerate(cov):
                    for pvr in st.PairSet[i].PairValueRecord:
                        v = getattr(pvr.Value1, "XAdvance", 0) if pvr.Value1 else 0
                        pairs.setdefault((g1, pvr.SecondGlyph), v)
            elif st.Format == 2:
                c1 = st.ClassDef1.classDefs if st.ClassDef1 else {}
                c2 = st.ClassDef2.classDefs if st.ClassDef2 else {}
                for g1 in cov:
                    k1 = c1.get(g1, 0)
                    rec = st.Class1Record[k1]
                    for g2, k2 in list(c2.items()):
                        v = rec.Class2Record[k2].Value1
                        x = getattr(v, "XAdvance", 0) if v else 0
                        if x:
                            pairs.setdefault((g1, g2), x)
    return pairs

def run(font, text, x0, tracking=0):
    gs = font.getGlyphSet(); cmap = font.getBestCmap(); hmtx = font["hmtx"]
    kern = kern_table(font)
    names = [cmap[ord(c)] for c in text]
    d, x = [], x0
    for i, g in enumerate(names):
        pen = SVGPathPen(gs)
        gs[g].draw(TransformPen(pen, (1, 0, 0, -1, x, 0)))
        d.append(pen.getCommands())
        x += hmtx[g][0] + tracking
        if i + 1 < len(names):
            x += kern.get((g, names[i + 1]), 0)
    return " ".join(d), x

bold, reg = instance(800), instance(400)
TRACK = -10  # jemně stažené jako v logu energyapp
d1, x = run(bold, "energy", 0, TRACK)
d2, x_end = run(reg, "sketch", x, TRACK)

def bbox(font, text, x0):
    gs = font.getGlyphSet(); bp = BoundsPen(gs); cmap = font.getBestCmap(); x = x0
    b = None
    for c in text:
        g = cmap[ord(c)]
        tp = TransformPen(bp, (1, 0, 0, 1, x, 0)); gs[g].draw(tp); x += font["hmtx"][g][0] + TRACK
    return bp.bounds
b1 = bbox(bold, "energy", 0); b2 = bbox(reg, "sketch", x)
ymin = min(b1[1], b2[1]); ymax = max(b1[3], b2[3])  # v jednotkách fontu (y nahoru)
XH = 536

# Vodorovně: x-výška = 0,40 výšky kostičky, střed x-výšky na středu kostičky, mezera 0,40 výšky
scale = 0.40 * CH / XH
gap = 0.40 * CH
tx0 = CX0 + CW + gap - b1[0] * scale
baseline = CY0 + CH / 2 + (XH * scale) / 2
text_w = (max(b1[2], b2[2]) - b1[0]) * scale
def words(fill, ox, oy, s):
    return (f'<g transform="translate({ox:.1f} {oy:.1f}) scale({s:.4f})">'
            f'<path fill="{fill}" d="{d1}"/><path fill="{fill}" d="{d2}"/></g>')
top = min(CY0, baseline - ymax * scale); bottom = max(CY0 + CH, baseline - ymin * scale)
M = 40
vb_h = f"{CX0-M:.0f} {top-M:.0f} {tx0 + max(b1[2],b2[2])*scale - CX0 + 2*M:.0f} {bottom-top+2*M:.0f}"
for name, edge, fill in [("energysketch-logo.svg", NAVY, TEXT), ("energysketch-logo-bile.svg", "#FFFFFF", "#FFFFFF")]:
    write(name, svg(vb_h, cube(edge) + words(fill, tx0, baseline, scale), "EnergySketch"))

# Pod sebou: šířka nápisu = 1,9 × šířka kostičky, mezera 0,22 výšky
s2 = 1.9 * CW / ((max(b1[2], b2[2]) - b1[0]))
tw = (max(b1[2], b2[2]) - b1[0]) * s2
ox = CX0 + CW / 2 - tw / 2 - b1[0] * s2
oy = CY0 + CH + 0.22 * CH + ymax * s2 * 0 + XH * s2  # x-výška pod kostičkou
oy = CY0 + CH + 0.22 * CH + 745 * s2  # účaří = horní okraj ascenderů + výška verzálek
left = min(CX0, ox + b1[0] * s2); right = max(CX0 + CW, ox + max(b1[2], b2[2]) * s2)
bottom2 = oy - ymin * s2
vb_v = f"{left-M:.0f} {CY0-M:.0f} {right-left+2*M:.0f} {bottom2-CY0+2*M:.0f}"
for name, edge, fill in [("energysketch-logo-pod-sebou.svg", NAVY, TEXT), ("energysketch-logo-pod-sebou-bile.svg", "#FFFFFF", "#FFFFFF")]:
    write(name, svg(vb_v, cube(edge) + words(fill, ox, oy, s2), "EnergySketch"))

# Samotný nápis
vb_w = f"{b1[0]-20:.0f} {-ymax-20:.0f} {max(b1[2],b2[2])-b1[0]+40:.0f} {ymax-ymin+40:.0f}"
for name, fill in [("energysketch-napis.svg", TEXT), ("energysketch-napis-bily.svg", "#FFFFFF")]:
    body = f'<path fill="{fill}" d="{d1}"/><path fill="{fill}" d="{d2}"/>'
    write(name, svg(vb_w, body, "EnergySketch"))
print("hotovo", sorted(os.listdir(os.path.join(OUT, "svg"))))
