<!-- SPDX-License-Identifier: GPL-3.0-or-later; © 2026 ArchEnergy s.r.o. -->
# AIRIS v EnergySketchi — návrh návazného kroku

18. 10. 2026. Jde o návrh, nikoliv o implementovaný kompatibilní server AIRIS.
Zdroje návrhu v původním Ruby pluginu a v tomto modeláři:
`arch_control_airis.rb`, `_editing.rb`, `_materials.rb`, `_north.rb`,
`docs/ai-bridge.md`, `plugins/ai_bridge.py`, `core/ai.py` a současný adaptér
ArchControlu. Existující spojení AIRIS s původní aplikací se nepřesměrovalo.

## Co už stačí z přibaleného AI Bridge

Most na 127.0.0.1:4763, MCP obal, zpracování v hlavním vlákně přes
`Signal(object)`, snímek viewportu, přehled modelu a běžné geometrické
recepty není nutné psát znovu. V sestavení je `EnergySketch-mcp.exe`.
Most se zapíná ručně v sekci AI a při zavření aplikace končí. Pro běžné
kreslení zůstávají původní nástroje `run_python`, `query_model`, `screenshot`,
`undo` a `redo`. Souřadnice tohoto rozhraní jsou v metrech.

To samo nezajišťuje smlouvu AIRIS: ta používá mm, logická ID, revizi,
materiálové kódy, doložení severu a dávku s úplným vrácením při chybě.
Obecná transakce AI navíc neobnovuje všechny vlastní slovníky dokumentu
a registr materiálů jako nová transakce ArchControlu. Pouhé volání služby
panelu uvnitř `run_python` by vytvořilo vnořenou historii. Takový obal
proto nedoporučujeme vydávat za kompatibilní AIRIS.

## Doporučené propojení

Ponechat jeden most a doplnit do jeho dispatcheru rozšiřující registr
typovaných nástrojů. Registraci nabídnout přes veřejné ExtensionApp,
nikoliv přepisem soukromých metod mostu. Registr vlastní dokument,
při jeho zavření se ruší; handler vždy běží v hlavním vlákně.
MCP obal pouze předá JSON. Slabá místa původního obecného `run_python`
se tím nerozšiřují na nové nástroje.

| Nástroj AIRIS | Existující část a potřebné doplnění |
|---|---|
| model_state, materials, north | Čtení přes adaptér, přehled ploch/zón/objemů a doložení severu; revize dokumentu, ne jen číslo LIVE serveru |
| geometry | `live_snapshot` již vrací světové mm, otvory a vazby; přidat stabilní ID sdílených vrcholů pro přesné posuny |
| set_north | Výpočet v čistém Pythonu; použít stejný vratný krok i georeferenci jako panel, uložit zdroj a míru jistoty |
| apply_batch | Jeden `LiveMutationCommand`, předem validovat celý whitelist, ID, meze a očekávanou revizi; žádná vnořená historie |
| create_material_auto / update_material | Současný parser, první volné číslo pro daný typ, kontrola duplicity, RP slovníky; změnu sdíleného materiálu uvádět výslovně |
| create_zone / add_faces / edit_faces | Nativní pomocníci LIVE, přesná kontrola výsledku, mm → m jen v adaptéru; zachovat logická ID a otvory |
| move_vertices | Vlastní plán se sdílenými vrcholy; neslučovat topologii potichu, odmítnout zámek a opakovanou sdílenou definici |
| undo_last_ai | Povolit jen pokud poslední vrchol historie i revize stále patří poslední dávce AIRIS; ruční změna oprávnění zruší |
| focus_zone / capture_view | Použít existující viewport/most; není třeba druhý renderer |
| save_copy | Nová kopie IGZ se samostatným názvem, žádné přepsání vstupního SKP; server neobsahuje zapisovač SKP |

Nezavádět druhý proces sledující souborovou schránku původního Ruby
AIRIS. Jeho `session_id`, expiraci a deduplikaci převzít do typovaného
dispatcheru: jedna odpověď pro stejné request_id a shodný obsah, odmítnutí
znovupoužitého ID s jinými daty. Ověřit živý dokument, očekávanou revizi,
neprobíhající ruční editaci a dokončený předchozí krok. Tokeny LIVE ani
klíče poskytovatele AI nesmí být ve stavu modelu, snímku, logu či IGZ.

## Převzetí a zkoušky před zapnutím

První etapa pouze čtení a snímek; druhá materiály/sever; třetí atomické
geometrické dávky. Pro každou ověřit úspěch, druhé doručení, starou revizi,
změněný dokument, chybu uprostřed dávky, Zpět/Znovu a uložení/načtení IGZ.
Geometrie musí projít stejným nezávislým srovnáním obrysů jako LIVE,
včetně otvoru a otočené/zvětšené/vnořené komponenty. Ukázkové modelování
spustit pouze ve zvláštním novém dokumentu a po testu most vypnout.

Základní modelování přes původní AI Bridge je přibalené už nyní. Tento
typovaný adaptér a kompatibilní nástroje `archcontrol_*` zůstávají dalším
krokem, jak dovoluje bod 13 zadání. Žádný produkční AI účet se při vývoji
nepoužil a na serveru APP se kvůli EnergySketchi nic neměnilo.
