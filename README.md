<!-- SPDX-License-Identifier: GPL-3.0-or-later; Modifications © 2026 ArchEnergy s.r.o. -->
# EnergySketch

**Otevřený 3D modelář pro přípravu podkladů k energetickým výpočtům budov.**

EnergySketch je upravená verze [IngeTrazo](https://github.com/ingelibre/ingetrazo)
od Marca Sumariho Telleze a dalších přispěvatelů. Úpravy a integrace ArchControlu:
**ArchEnergy s.r.o.** Původní autory uvádí [AUTHORS](AUTHORS), změny [NOTICE](NOTICE).

Chceme energetickým specialistům nabídnout pracovní nástroj bez nutnosti
pořizovat komerční 3D modelář a samostatný energetický doplněk. EnergySketch
spojuje modelování budov a přípravu podkladů pro energetické výpočty v jednom
otevřeném programu. Samotný EnergySketch lze používat bez povinného předplatného.

## Stav projektu

Alfa verze **0.1 alfa 2**, založená na IngeTrazo **0.5.11**.
[Stažení pro Windows](https://github.com/pet84/EnergySketch/releases/tag/v0.1.0-alfa.2)
a [produktová stránka](https://energyapp.cz/energysketch).
Naše sestavení je ověřované na Windows; ostatní platformy vyžadují další ověření.

- České rozhraní, výchozí světlý motiv, modré zvýraznění a 114 vybraných ikon.
- Dvě horní řady nástrojů, dvousloupcové kreslení vlevo a panely vpravo.
- Hladiny včetně nové lišty, filtrů a vlastností z IngeTrazo 0.5.11.
- Import SKP, práce s plochami, hranami, skupinami, komponentami a materiály.
- ArchControl: tabulka ploch, materiály, zóny, orientace a určení severu.
- Tři CSV exporty: Komplexní CSV, Energie po zónách a Renovační pas.
- Palety materiálů a zón, rychlé akce, kapátko a mřížka oken na fasádě.
- Vytvoření skupiny z průřezu, Zpět/Znovu a uložení do IGZ.
- České instrukce AI a MCP most pro externího AI klienta.
- Volitelné napojení ASTRA LIVE na samostatnou APP; kompatibilní AIRIS je zatím návrh.

Pro samostatné modelování a CSV export není potřeba účet APP ani placený AI model.
Externí AI a připojené služby mohou mít vlastní podmínky a náklady.
Program sám nevytváří ověřený PENB ani nenahrazuje kontrolu energetického specialisty.
Omezení a návod: [ARCHENERGY.md](ARCHENERGY.md).

## Spuštění ze zdrojů

Potřebujete **Python 3.12**, Git a grafický ovladač s podporou OpenGL 3.3.
Příklad pro PowerShell na Windows:

```powershell
git clone https://github.com/pet84/EnergySketch.git
cd EnergySketch
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe energysketch.py
```

OpenSKP se instaluje z konkrétního veřejného commitu uvedeného v requirements.txt.
Na Linuxu/macOS použijte ekvivalentní příkazy pro prostředí venv; změny EnergySketch
na těchto platformách ještě nejsou součástí našeho ověření.

## Sestavení pro Windows

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements-build.txt
New-Item -ItemType Directory -Force output/archenergy
.\.venv\Scripts\python.exe scripts/archenergy_fetch_dwg.py
.\.venv\Scripts\python.exe scripts/archenergy_fetch_native.py
.\.venv\Scripts\python.exe scripts/archenergy_prepare_build.py
.\.venv\Scripts\python.exe -m PyInstaller --noconfirm EnergySketch.spec
```

Výsledek je `dist/EnergySketch/EnergySketch.exe` a pomocník `EnergySketch-mcp.exe`.
Přenášejte celou složku EnergySketch včetně `_internal`. K sestavení nejsou potřeba
interní zákaznické modely, protokoly ani původní Ruby plugin.
Windows sestavení obsahuje nezměněné Rust jádro z ověřeného upstream vydání 0.5.11.
Skript archenergy_fetch_native.py kontroluje SHA-256 celého upstream archivu.
Vlastní sestavení jádra ze zdrojů popisuje původní vývojářská dokumentace.
Při spuštění ze zdrojů je bez nativního modulu dostupné Python jádro.

## Kontroly

```powershell
.\.venv\Scripts\python.exe scripts/check_czech_translation.py
.\.venv\Scripts\python.exe -m pytest -q tests/test_archcontrol_core.py tests/test_archcontrol_exports.py tests/test_archcontrol_import.py tests/test_archcontrol_materials.py tests/test_archcontrol_eyedropper.py
```

Testy pracují se syntetickými daty. Interní zákaznické modely, jejich CSV exporty,
snímky a lokální protokoly nejsou součástí veřejného repozitáře. Úplná původní sada
testů je větší; aktuální ověření této verze uvádí [PUBLICATION.md](PUBLICATION.md).

## Licence a původ

**GNU GPL v3 nebo novější** — viz [LICENSE](LICENSE). Při dalším předávání programu
zachovejte licenční oznámení a zajistěte odpovídající zdrojový kód podle GPL.
Převzaté části a závislosti si ponechávají své původní licence.
Značky EnergySketch a ArchEnergy nevyjadřují podporu původních autorů či jiných firem.

Původní dokumentace: [IngeTrazo README](README-INGETRAZO.md),
[vývoj](docs/development.md), [MCP](docs/ai-bridge.md).
Původ a způsob přebírání změn: [UPSTREAM.md](UPSTREAM.md).
