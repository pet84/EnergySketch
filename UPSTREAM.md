<!-- SPDX-License-Identifier: GPL-3.0-or-later; © 2026 ArchEnergy s.r.o. -->
# Původ a aktualizace

EnergySketch je odvozená upravená verze IngeTrazo.

- Původní projekt: https://github.com/ingelibre/ingetrazo
- Původní autor: Marco Sumari Tellez a přispěvatelé uvedení v AUTHORS.
- Základ tohoto snímku: veřejný upstream commit `a94a2f7ed7481d08eb113874884aaa4e200f49ce`.
- Interní zdrojový commit před veřejným exportem: `6c2a936256202a66df45c09174dcee44c2ed118e`.
- Úpravy a integrace ArchControlu: © 2026 ArchEnergy s.r.o.
- Veřejný export a přenositelné návody: 19. 10. 2026.

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
