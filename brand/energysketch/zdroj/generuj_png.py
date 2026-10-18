"""PNG, ICO a webové soubory pro balíček EnergySketch (render přes Edge headless)."""
import os, re, subprocess, sys, tempfile, json, shutil
from PIL import Image

ROOT = sys.argv[1]
SVG = os.path.join(ROOT, "svg")
PNG = os.path.join(ROOT, "png"); WEB = os.path.join(ROOT, "web"); WIN = os.path.join(ROOT, "windows")
for d in (PNG, WEB, WIN):
    os.makedirs(d, exist_ok=True)
EDGE = r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe"
TMP = tempfile.mkdtemp(prefix="es-render-")

def read(name):
    with open(os.path.join(SVG, name), encoding="utf-8") as f:
        return f.read()

def write_svg(path, content):
    with open(path, "w", encoding="utf-8", newline="\n") as f:
        f.write(content)

# Varianta pro malé velikosti (16–32 px): silnější hrany, jinak se čáry rozmažou
small = read("energysketch-ikona-maly.svg")

_n = 0

def render(svg_name, w, h, out, bg="transparent"):
    src = os.path.join(SVG, svg_name).replace("\\", "/")
    html = os.path.join(TMP, "p.html")
    with open(html, "w", encoding="utf-8") as f:
        f.write(f'<!doctype html><html><body style="margin:0;background:{bg};overflow:hidden">'
                f'<img src="file:///{src}" style="display:block;width:{w}px;height:{h}px"></body></html>')
    shot = os.path.join(TMP, "s.png")
    if os.path.exists(shot):
        os.remove(shot)
    global _n
    _n += 1
    prof = os.path.join(TMP, f"prof{_n}")
    for attempt in range(3):
      subprocess.run([EDGE, "--headless=new", "--disable-gpu", "--hide-scrollbars", "--allow-file-access-from-files",
                    "--default-background-color=00000000", f"--window-size={w},{h}",
                    f"--user-data-dir={prof}{attempt}", f"--screenshot={shot}", "file:///" + html.replace("\\", "/")],
                   capture_output=True, timeout=60)
      if os.path.exists(shot):
          break
    Image.open(shot).convert("RGBA").crop((0, 0, w, h)).save(out)
    return out

def ratio(svg_name):
    vb = re.search(r'viewBox="([^"]+)"', read(svg_name)).group(1).split()
    return float(vb[2]) / float(vb[3])

# Ikona s průhledným pozadím
for s in (16, 24, 32):
    render("energysketch-ikona-maly.svg", s, s, os.path.join(PNG, f"energysketch-ikona-{s}.png"))
for s in (48, 64, 128, 256, 512, 1024):
    render("energysketch-ikona.svg", s, s, os.path.join(PNG, f"energysketch-ikona-{s}.png"))
render("energysketch-ikona-pro-tmave-pozadi.svg", 512, 512, os.path.join(PNG, "energysketch-ikona-pro-tmave-pozadi-512.png"))
render("energysketch-ikona-mono.svg", 512, 512, os.path.join(PNG, "energysketch-ikona-mono-512.png"))
# Ikona aplikace (zaoblený čtverec)
for s in (16, 24, 32, 48, 64, 128, 256, 512, 1024):
    render("energysketch-ikona-aplikace-svetla.svg", s, s, os.path.join(PNG, f"energysketch-ikona-aplikace-svetla-{s}.png"))
render("energysketch-ikona-aplikace-tmava.svg", 512, 512, os.path.join(PNG, "energysketch-ikona-aplikace-tmava-512.png"))
# Loga
for name, w in [("energysketch-logo.svg", 1200), ("energysketch-logo-bile.svg", 1200),
                ("energysketch-logo-pod-sebou.svg", 800), ("energysketch-logo-pod-sebou-bile.svg", 800),
                ("energysketch-napis.svg", 1200)]:
    h = round(w / ratio(name))
    render(name, w, h, os.path.join(PNG, name.replace(".svg", ".png")))

# --- Windows: ICO pro exe (ikona aplikace, čitelná na světlém i tmavém hlavním panelu) ---
def ico(prefix, sizes, out):
    imgs = [Image.open(os.path.join(PNG, f"{prefix}-{s}.png")) for s in sizes]
    imgs[-1].save(out, sizes=[(s, s) for s in sizes], append_images=imgs[:-1])
for s_ in (16, 24, 32):
    render("energysketch-ikona-aplikace-svetla-maly.svg", s_, s_, os.path.join(PNG, f"energysketch-ikona-aplikace-svetla-{s_}.png"))
ico("energysketch-ikona-aplikace-svetla", (16, 24, 32, 48, 64, 128, 256), os.path.join(WIN, "energysketch.ico"))
ico("energysketch-ikona", (16, 24, 32, 48, 64, 128, 256), os.path.join(WIN, "energysketch-pruhledna.ico"))

# --- Web ---
fav = small.replace("<defs>", '<defs><style>@media (prefers-color-scheme: dark){.e{stroke:#FFFFFF}}</style>')
fav = fav.replace('<g fill="none" stroke="#0B1B3A"', '<g class="e" fill="none" stroke="#0B1B3A"')
write_svg(os.path.join(WEB, "favicon.svg"), fav)
ico("energysketch-ikona", (16, 32, 48), os.path.join(WEB, "favicon.ico"))
# apple-touch: plný čtverec bez zaoblení (iOS si roh zaoblí sám)
apple = read("energysketch-ikona-aplikace-svetla.svg")
apple = re.sub(r'rx="[^"]+"', 'rx="0"', apple)
write_svg(os.path.join(TMP, "apple.svg"), apple)
shutil.copy(os.path.join(TMP, "apple.svg"), os.path.join(SVG, "energysketch-ikona-ctverec.svg"))
render("energysketch-ikona-ctverec.svg", 180, 180, os.path.join(WEB, "apple-touch-icon.png"))
render("energysketch-ikona-ctverec.svg", 512, 512, os.path.join(WEB, "icon-maskable-512.png"))
shutil.copy(os.path.join(PNG, "energysketch-ikona-aplikace-svetla-512.png"), os.path.join(WEB, "icon-512.png"))
render("energysketch-ikona-aplikace-svetla.svg", 192, 192, os.path.join(WEB, "icon-192.png"))
manifest = {
    "name": "EnergySketch", "short_name": "EnergySketch",
    "icons": [
        {"src": "/icon-192.png", "sizes": "192x192", "type": "image/png"},
        {"src": "/icon-512.png", "sizes": "512x512", "type": "image/png"},
        {"src": "/icon-maskable-512.png", "sizes": "512x512", "type": "image/png", "purpose": "maskable"}],
    "theme_color": "#0B1B3A", "background_color": "#FFFFFF", "display": "standalone"}
with open(os.path.join(WEB, "site.webmanifest"), "w", encoding="utf-8", newline="\n") as f:
    json.dump(manifest, f, ensure_ascii=False, indent=2); f.write("\n")
with open(os.path.join(WEB, "head.html"), "w", encoding="utf-8", newline="\n") as f:
    f.write('<link rel="icon" href="/favicon.ico" sizes="48x48">\n'
            '<link rel="icon" href="/favicon.svg" type="image/svg+xml">\n'
            '<link rel="apple-touch-icon" href="/apple-touch-icon.png">\n'
            '<link rel="manifest" href="/site.webmanifest">\n'
            '<meta name="theme-color" content="#0B1B3A">\n')
shutil.rmtree(TMP, ignore_errors=True)
print("PNG:", len(os.listdir(PNG)), "WEB:", sorted(os.listdir(WEB)), "WIN:", sorted(os.listdir(WIN)))
