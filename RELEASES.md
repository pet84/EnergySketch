<!-- SPDX-License-Identifier: GPL-3.0-or-later; © 2026 ArchEnergy s.r.o. -->
# Veřejná vydání

## 0.1 alfa 2 — 28. 10. 2026

Základ IngeTrazo 0.5.11, nová práce s hladinami, doplněná čeština,
114 vybraných ikon a schválené výchozí rozložení. Stávající profily si ponechají
vlastní uložené uspořádání. ArchControl, import SKP, IGZ a CSV exporty zachovány.

Windows ZIP je přiložen k tagu `v0.1.0-alfa.2`. Rozbalte jej celý a spusťte
EnergySketch.exe. Zachovejte složku `_internal`. Instalační průvodce není potřeba.
Odpovídající zdrojový kód je dostupný pod stejným tagem. BUILD-MANIFEST.json
v balíčku uvádí veřejný zdrojový commit a kontrolní součty spustitelných souborů.
Jde o alfa verzi; známá omezení a rozsah kontrol uvádí PUBLICATION.md.

## 0.1 alfa — 19. 10. 2026

První veřejné vydání, základ IngeTrazo 0.5.8, české rozhraní a ArchControl.
Tag `v0.1.0-alfa` zůstává dostupný pro návrat ke starší verzi.

## Sestavení

Postup je v README.md. Balíček musí obsahovat LICENSE, AUTHORS, NOTICE,
licence závislostí a odkaz na odpovídající veřejné zdroje. Původní automatizace
IngeTrazo je archivována v docs/upstream-workflows/. Aktivní workflow EnergySketch
source checks ověřuje český katalog a syntetické testy ArchControlu a rozložení.
