# SPDX-License-Identifier: GPL-3.0-or-later
# © 2026 ArchEnergy s.r.o.
"""Adapt the owner's original help for the offline native EnergySketch reader."""
from pathlib import Path
import re
import shutil

import os
SOURCE = Path(os.environ.get("ARCHCONTROL_RUBY_SOURCE", "reference/arch_control"))
DEST = Path(__file__).resolve().parents[1] / "plugins/archcontrol"

INTRO = '''<h1>ArchControl pro EnergySketch</h1>
<p><b>ArchEnergy s.r.o. — nativní plugin v Pythonu.</b></p>
<h2>Začínáme v EnergySketch</h2>
<ol><li>Soubor → Otevřít načte .skp do prázdného dokumentu. Názvy materiálů
a komponent se zachovají. Originální soubor se při importu nepřepisuje.</li>
<li>Rozšíření → ArchControl → Otevřít panel zobrazí tabulku ploch.
Neznámý sever nejprve potvrďte v panelu nebo určete nástrojem Sever dvěma body.
Úhel ArchControlu se měří proti směru hodinových ručiček od osy +Y.</li>
<li>Filtr omezuje tabulku; Sčítat stejné slučuje shodné konstrukce.
Pro výběr konkrétních ploch jedné komponenty slučování vypněte.
Změny materiálů, skrývání i sever lze vrátit pomocí Zpět.</li>
<li>Paleta materiálů umožňuje nový materiál, úpravu, duplikaci, malování,
smazání a přenos knihovny JSON. Jedinečnost se kontroluje podle Typ–Číslo–Varianta.
Neznámé U/g ponechte prázdné. RP má samostatná pole v materiálovém formuláři.</li>
<li>Paleta zón zobrazuje komponenty, objem uzavřených těles a plochy obálky.
Plošná nebo otevřená komponenta nemá doložitelný objem.</li>
<li>Vložit mřížku oken: nastavte počet řad/sloupců, místní rozměry, mezery
a materiál, potom klikněte do středu mřížky na fasádě. Červený náhled ukazuje
budoucí polohu. Esc zruší nástroj, Zpět vrátí celou vloženou mřížku.
Vzniknou plochy na povrchu s materiálem na líci i rubu, nikoli ostění ani
proříznutí tloušťky stěny. U komponent se úprava sdílí mezi jejich kopiemi.</li>
<li>Ukládejte jako .igz, aby se zachovala geometrie a údaje pluginu.</li></ol>
<h2>Výstupy a kompatibilita</h2>
<p>Panel nabízí Komplexní CSV, Energie po zónách a Renovační pas.
Energie má 20 sloupců, oddělovač středník a UTF-8 s BOM.
Renovační pas má 16 sloupců, čárku a UTF-8 bez BOM. Podle výslovného rozhodnutí
zadavatele zachovává původní Ruby výpočty: místní plochu/normálu a zahrnutí
skrytých ploch. Proto se může lišit od hlavní tabulky transformované geometrie.</p>
<p>Úplná shoda všech CSV se současným referenčním exportem dosud není potvrzena.
Podrobný aktuální stav a omezení jsou v ARCHENERGY.md.</p>
<h2>Původní návod pro import CSV do Energie</h2>
<p>Následující tabulky a obrázky pocházejí z původního ArchControlu. Popisují
historicky ověřené nastavení v Energii, nikoli nové ověření této distribuce.
Hodnoty Un odpovídají původnímu pluginu a jeho číselníku.</p>
'''


def main():
    text = (SOURCE / "help.html").read_text(encoding="utf-8")
    body = re.search(r"<body[^>]*>(.*)</body>", text, re.S | re.I).group(1)
    body = re.sub(r"<script\b[^>]*>.*?</script>", "", body, flags=re.S | re.I)
    body = re.sub(r"<button\b[^>]*>.*?</button>", "", body, flags=re.S | re.I)
    body = re.sub(r"<h1\b[^>]*>.*?</h1>", "", body, count=1, flags=re.S | re.I)
    body = re.sub(r'<p class="verze">.*?</p>',
                  '<p>EnergySketch · ArchControl · ArchEnergy s.r.o. — úpravy 18. 10. 2026</p>',
                  body, flags=re.S)
    document = ('<!-- SPDX-License-Identifier: GPL-3.0-or-later; '
                'Úpravy © 2026 ArchEnergy s.r.o.; převzato z vlastního ArchControlu. -->\n'
                '<!doctype html><html lang="cs"><head><meta charset="utf-8">'
                '<title>ArchControl pro EnergySketch</title></head><body>' + INTRO + body + '</body></html>\n')
    (DEST / "help.html").write_text(document, encoding="utf-8", newline="\n")
    for image in (SOURCE / "help_assets").rglob("*.png"):
        target = DEST / image.relative_to(SOURCE)
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(image, target)
    print("Offline native help and four original Energie screenshots ready")


if __name__ == "__main__":
    main()
