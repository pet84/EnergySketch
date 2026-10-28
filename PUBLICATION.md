<!-- SPDX-License-Identifier: GPL-3.0-or-later; © 2026 ArchEnergy s.r.o. -->
# Ověření vydání 0.1 alfa 2

Datum: **28. 10. 2026**. Základ IngeTrazo v0.5.11. Ověřeno na Windows,
Python 3.12, samostatné dočasné profily; běžný uživatelský dokument se neměnil.

- Český katalog: **3218 požadovaných, 3220 přeložených položek**, žádné
  strukturální chyby (kontrola klíčů, hodnot, parametrů a odřádkování).
- V oddělené veřejné kopii prošlo **35 cílených testů** rozložení, původních
  akcí/klávesových zkratek, dvousloupcových lišt, obnovy a ArchControlu.
- Ve vývojovém ověření vyšlo s návratovým kódem 0 celkem **5721 testů**
  rychlé sady a dalších **132 testů nativního modulu**.
- Šest dalších dávek skončilo nativní Windows chybou `0xC0000005` po vypsání
  úspěšných assertions; **nejsou započítány jako úspěšné procesy**. Stejná
  chyba se reprodukovala také v čistém upstream v0.5.11. Celá sada tedy není zelená.
- Hotový Windows EXE: kontrola závislostí a rozšíření, skutečné OpenGL vykreslení,
  Rust jádro, 114 vybraných ikon a přepínání motivu. Jeden souběžný OpenGL
  pokus selhal nativně; následná samostatná kontrola prošla s návratovým kódem 0.
- Import modelů, metadata a objemy, IGZ a šest CSV porovnání proti nezávislým
  referencím prošly. Vstupní modely zůstaly bajtově nezměněné.
- Zdrojový kód a prostředky běhu se přenášejí z ověřeného sestavení bez změn;
  veřejné návody a oznámení neobsahují soukromé vývojářské cesty. Součástí
  publikace nejsou zákaznické modely, exporty, interní historie ani protokoly.
- Nezměněné Rust jádro pochází z oficiálního Windows archivu IngeTrazo v0.5.11.
  Jeho SHA-256 i dostupné zdroje uvádí scripts/archenergy_fetch_native.py.

Jde o **alfa verzi**, ne certifikaci produktu ani potvrzení, že prošla celá
upstream sada. Před převzetím výměr a energetických dat zkontrolujte vlastní
model a výsledky. Praktická omezení a návod jsou v ARCHENERGY.md.
