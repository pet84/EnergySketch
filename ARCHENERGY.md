<!-- SPDX-License-Identifier: GPL-3.0-or-later; © 2026 ArchEnergy s.r.o. -->
# EnergySketch — návod a stav

Alfa verze 0.1 alfa 2, stav k 28. 10. 2026; základ IngeTrazo 0.5.11. EnergySketch je upravená verze IngeTrazo;
původní autoři zůstávají uvedeni v AUTHORS a licence v LICENSE.

## Běžná práce

Spusťte `python energysketch.py` ve svém prostředí nebo sestavený EnergySketch.exe.
SKP otevírejte přes **Soubor → Otevřít**. Import nepřepisuje vstupní model.
Pracovní dokument ukládejte jako **IGZ**; přímý zápis do SKP je vypnutý.
DAE lze použít pro přenos geometrie, ale není náhradou IGZ pro metadata ArchControlu.
U instalace pro Windows je nutná celá složka programu včetně `_internal`.
Profil je ve `%APPDATA%/EnergySketch/`; sestavení z tohoto repozitáře nemění
uživatelské nastavení jiných aplikací.

## Rozložení a ikony

Nový profil má dvě horní řady nástrojů, dvousloupcové kreslení a měření vlevo
a panely vpravo s otevřeným ArchControlem. Výběr 114 ikon kombinuje původní
ikony EnergySketch (44), vlastní SVG (64) a šest návrhů Arrow 2 Telos.
Existující uložené rozložení se při aktualizaci zachovává. Výchozí rozložení
lze znovu vyvolat přes **Okno → Obnovit výchozí lišty nástrojů** a
**Okno → Panely → Obnovit výchozí panely**.

## ArchControl

Nabídka **Rozšíření → ArchControl** otevírá tabulku ploch a palety.
Lišta **ArchControl — nástroje** obsahuje přímé akce. Pokud není vidět,
použijte **Vrátit lištu ArchControl nad model** ve stejné nabídce.

- Kapátkem v hlavní liště klikněte na plochu: paleta materiálů se otevře,
  vybere odpovídající pojmenovaný materiál a posune se na jeho řádek.
  Filtr, který by materiál skrýval, se při tom uvolní. U nepojmenované
  barvy se zobrazí informace, že nejde o pojmenovaný materiál knihovny.
- Barevný vzorek zůstává viditelný i ve vybraném řádku.
- Akce u materiálu umožňují malovat, použít na výběr, upravit, duplikovat,
  skrýt a smazat. Smazání nebo úprava sdíleného materiálu ovlivní jeho použití.
- Sever určete číselně nebo dvěma body. Není-li sever ověřený, nepotvrzujte
  automaticky orientaci importovaného modelu podle samotného snímku.
- Zóny vycházejí z komponent a jejich vlastností. Otevřená geometrie nemá
  spolehlivý uzavřený objem. Neznámé U/g ponechte nevyplněné.
- Mřížka oken vytváří plochy na fasádě; nevytváří ostění ani skutečný
  průraz tloušťkou stěny. Úprava sdílené komponenty se projeví v jejích kopiích.

## Přehled funkcí

| Oblast | Stav a praktické omezení |
|---|---|
| Tabulka ploch, materiály, orientace, zóny | Implementováno; kontrolujte importovaná metadata |
| Formulář a paleta materiálů, JSON knihovna | Implementováno |
| Sever číslem a dvěma body | Implementováno |
| Komplexní CSV, Energie po zónách, Renovační pas | Implementováno |
| Paleta zón a objemy | Objem vyžaduje uzavřenou geometrii |
| Mřížka oken na fasádě | Povrchové plochy, bez vyříznutí ostění |
| Skupina z průřezu | Implementováno; nejprve dokončete editaci sdílené komponenty |
| ASTRA LIVE | Implementovaný adaptér; vyžaduje samostatnou kompatibilní APP |
| AIRIS | Návrh, viz docs/ENERGYSKETCH_AIRIS.md |
| Samostatný energetický výpočet / PENB | Není součástí tohoto modeláře |

CSV zachovává specifika původního Ruby pluginu. Renovační pas záměrně používá
lokální plochu a normálu a zahrnuje i skryté plochy; při otočení či změně měřítka
komponent se proto může lišit od hlavní tabulky. Změnu této kompatibility nelze
vydávat za pouhou kosmetickou opravu. Interní referenční zkoušky nejsou
zákaznickými podklady určenými ke zveřejnění; veřejné testy používají syntetická data.

## AI a MCP

Vestavěný chat používá vlastní API klíč poskytovatele nebo podporovaný lokální model.
AI služby mohou mít vlastní předplatné či poplatky. Externí klient s MCP může
využít své přihlášení/předplatné podle podmínek poskytovatele.

1. V cílovém dokumentu zapněte **AI → Propojení AI (MCP) → Spustit propojení**.
2. Připojte důvěryhodného MCP klienta. Pomocníka EnergySketch-mcp.exe spouští klient;
   u zdrojového spuštění použijte příkaz zobrazený aplikací.
3. Nechte klienta nejprve přečíst stav modelu. Pro pokusy otevřete nový dokument.

Most standardně poslouchá pouze na `127.0.0.1:4763`. Nástroj run_python provádí
Python uvnitř aplikace; připojujte důvěryhodného klienta. U více oken zapněte most
pouze v cílovém dokumentu. Nástroje jsou query_model, run_python, screenshot,
undo a redo. ASTRA LIVE tento MCP pomocník nepotřebuje.
Kódy stran nativního house jsou anglické: **N = sever, S = jih, W = západ, E = východ**.
Osa +Y je výchozí sever; orientaci otočeného importu je nutné ověřit.

## Přebírání nových verzí

Postup a původ zdrojů uvádí UPSTREAM.md. ArchControl zůstává v plugins/archcontrol;
menší úpravy hostitele zajišťují české prostředí, branding a integraci nástrojů.
Nová upstream verze vyžaduje sloučení změn, vyřešení konfliktů, testy importu,
uložení/načtení IGZ, exportů, materiálů, Zpět/Znovu a nové sestavení.

## Formulace pro prezentaci

> Pracuje se v tom podobně jako ve SketchUpu — kreslíš hrany a plochy a pak je vytahuješ do objemu.

Jde o popis způsobu práce. EnergySketch je nezávislý projekt ArchEnergy s.r.o.
odvozený od IngeTrazo, nikoliv produkt společnosti Trimble.
