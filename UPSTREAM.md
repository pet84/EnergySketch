<!-- SPDX-License-Identifier: GPL-3.0-or-later; © 2026 ArchEnergy s.r.o. -->
# Původ a aktualizace

EnergySketch je odvozená upravená verze IngeTrazo.

- Původní projekt: https://github.com/ingelibre/ingetrazo
- Původní autor: Marco Sumari Tellez a přispěvatelé uvedení v AUTHORS.
- Základ tohoto snímku: IngeTrazo **v0.5.11**, commit `a369d1ed` (28. 10. 2026).
- Úpravy a integrace ArchControlu: © 2026 ArchEnergy s.r.o.
- První veřejný snímek: 19. 10. 2026; aktualizace: 28. 10. 2026.

Veřejná historie začíná čistým snímkem aktuálních zdrojů. Interní historie obsahuje
také zákaznické podklady a měření; nepřenáší se do veřejného repozitáře.
Původní autorské hlavičky, LICENSE a AUTHORS jsou zachovány.

Vývojové sloučení s upstreamem probíhá v původním vývojovém checkoutu, který si
ponechává společnou historii s IngeTrazo. Před aktualizací uložte vlastní práci,
vytvořte pracovní větev, načtěte upstream a slučte požadovanou ověřenou verzi.
Vyřešte konflikty a ověřte importy, metadata, CSV, IGZ, Zpět/Znovu, UI a sestavení.
Neprovádějte reset vlastních úprav na upstream/main.

Pro veřejné aktualizace přeneste ověřený nový zdrojový strom do tohoto repozitáře
jako další commit a zachovejte zdejší veřejnou historii. Interní git historii,
zákaznické soubory, exporty, přístupové údaje ani logy nepřenášejte.
Samotný veřejný checkout je plnohodnotný zdroj pro spuštění a sestavení; nepoužívá
interní cestu vývojáře ani interní historie jako závislost sestavení.
