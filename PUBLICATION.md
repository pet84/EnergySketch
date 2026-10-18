<!-- SPDX-License-Identifier: GPL-3.0-or-later; © 2026 ArchEnergy s.r.o. -->
# Ověření prvního veřejného zdrojového snímku

Datum: **19. 10. 2026**. Ověřováno přímo v oddělené veřejné kopii, Python 3.12
na Windows, Qt offscreen, samostatný dočasný uživatelský profil.

- `scripts/check_czech_translation.py`: **2986 požadovaných a 2986 přeložených
  položek, žádné strukturální chyby**. Kontrola klíčů, duplicit, neprázdných hodnot,
  parametrů a odřádkování nenahrazuje jazykovou odbornou revizi.
- `python -m pytest -q tests/test_archcontrol*.py`: **297 testů prošlo za 41,89 s**.
  Testy pokrývají jádro, CSV exporty, import, materiály, kapátko, zóny, sever,
  UI panely, lištu, průřez a LIVE transport/příkazy na syntetických datech.
- **230 souborů běhového zdrojového kódu a build specifikací** je bajtově shodných
  s ověřeným vývojovým zdrojem. Při veřejném exportu se upravovaly návody,
  zdrojová oznámení a přenositelnost několika vývojářských pomocníků.
- LICENSE a AUTHORS zůstaly bajtově zachované. Licence algoritmu Ruby qs6
  je součástí pluginu.
- Zákaznické modely, referenční CSV, snímky, lokální protokoly, zástupce Windows
  ani interní historie nejsou součástí tohoto snímku.
- Kontrola textových souborů na konkrétní soukromé cesty, známé zákaznické
  identifikátory a obvyklé formáty přístupových údajů nenalezla skutečné přístupové
  údaje. Nalezené ukázky přihlašovací URL a neplatného klíče jsou syntetické
  vstupy bezpečnostních testů.

Nejde o nový běh celé původní sady IngeTrazo ani o certifikaci produktu.
Binární veřejné vydání se připravuje samostatně, viz RELEASES.md.
