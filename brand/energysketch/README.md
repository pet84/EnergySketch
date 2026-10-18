# EnergySketch: logo a ikony

EnergySketch je doplňkový program k **energyapp**, 3D modelář od ArchEnergy s.r.o. Ikona vychází z kostičky energyapp, aby oba programy působily jako jedna rodina:

- **energyapp** = plná barevná kostička, hotový model,
- **energysketch** = drátěná kostička s modrým vrškem, konstrukce modelu.

Schváleno 18. 10. 2026 (Petr Kvasnička). Původní vzor kostičky je `nabidkovac/public/logo/app/app-cube.svg`.

Náhled všeho najdeš v `nahled.html`.

## Co je kde

| Složka | Obsah | Kdy použít |
|---|---|---|
| `svg/` | zdrojové vektory: ikony, loga, nápis | všude, kde jde vektor (web, tisk, prezentace) |
| `png/` | ikony 16–1024 px, ikony aplikace, loga ve 2× rozlišení | kde vektor nejde (Word, e-mail, sociální sítě) |
| `web/` | favicon, ikony pro telefon, `site.webmanifest`, `head.html` | web a webová aplikace |
| `windows/` | `energysketch.ico` pro exe, okno a hlavní panel | Windows build (Codex) |
| `zaloha/` | schválená verze ikony | jen archiv |
| `zdroj/` | skripty, ze kterých se vše generuje | když se mění tvar nebo barvy |

### Ikona

| Soubor | Použití |
|---|---|
| `svg/energysketch-ikona.svg` | hlavní ikona na světlém pozadí |
| `svg/energysketch-ikona-pro-tmave-pozadi.svg` | na tmavém pozadí (bílé hrany) |
| `svg/energysketch-ikona-maly.svg` (+ `-pro-tmave-pozadi`) | **jen pro 16–32 px** (silnější hrana, aby nezmizela) |
| `svg/energysketch-ikona-mono.svg` / `-mono-bila.svg` | jednobarevná (razítko, fax, jednobarevný tisk) |
| `svg/energysketch-ikona-aplikace-svetla.svg` / `-tmava.svg` | ikona aplikace v zaobleném čtverci (dlaždice, plocha, obchod) |

### Logo s nápisem

| Soubor | Použití |
|---|---|
| `svg/energysketch-logo.svg` | vodorovné logo, světlé pozadí (hlavní) |
| `svg/energysketch-logo-bile.svg` | vodorovné logo, tmavé pozadí |
| `svg/energysketch-logo-pod-sebou.svg` / `-bile.svg` | ikona nad nápisem (úvodní obrazovka, čtvercová místa) |
| `svg/energysketch-napis.svg` / `-bily.svg` | samotný nápis bez ikony |

Nápis je převedený na křivky, takže nepotřebuje nainstalované písmo.

## Pravidla

- **Název se píše malými: energysketch**, stejně jako energyapp. V běžném textu (věta, nadpis v dokumentu) je v pořádku „EnergySketch“.
- Nápis: „energy“ tučně (Plus Jakarta Sans 800), „sketch“ obyčejně (400), stejné písmo jako web energyapp.
- Ikonu nedeformovat, neotáčet, nepřebarvovat, nepřidávat stíny ani efekty.
- Kolem loga nechat volné místo aspoň polovinu výšky ikony.
- Pod 32 px vždy použít `-maly` variantu.
- Na tmavém pozadí použít bílé varianty, ne tmavé logo na tmavém podkladu.

### Barvy

| Barva | Hodnota | Kde |
|---|---|---|
| Tmavě modrá (hrany) | `#0B1B3A` | hrany kostičky, tmavé pozadí ikony |
| Nápis | `#1B2E4A` | nápis na světlém pozadí |
| Modrý vršek | přechod `#5ED8FF` → `#2AB2F7` | horní plocha, stejná jako u energyapp |
| Bílá | `#FFFFFF` | hrany a nápis na tmavém pozadí |

Barvy energyapp pro doplnění (boky plné kostičky): modrá `#2C86FF` → `#0052DB`, zelená `#4CEFA0` → `#18C27A`.

## Pro web

Soubory z `web/` patří do kořene webu (u Next.js do `public/`). Do `<head>` vložit obsah `web/head.html`:

```html
<link rel="icon" href="/favicon.ico" sizes="48x48">
<link rel="icon" href="/favicon.svg" type="image/svg+xml">
<link rel="apple-touch-icon" href="/apple-touch-icon.png">
<link rel="manifest" href="/site.webmanifest">
<meta name="theme-color" content="#0B1B3A">
```

`favicon.svg` se sám přepne na bílé hrany, když má prohlížeč tmavý režim.

## Pro Codex (Windows aplikace EnergySketch)

Pokyn, který stačí Codexu poslat:

> Použij ikony z `brand/energysketch/` podle `brand/energysketch/README.md`:
> - `windows/energysketch.ico` jako ikonu `EnergySketch.exe` (PyInstaller `icon=` v `EnergySketch.spec`) a ikonu instalátoru,
> - `png/energysketch-ikona-aplikace-svetla-256.png` (nebo ICO) jako ikonu okna (`QApplication.setWindowIcon`) a ikonu na hlavním panelu,
> - `svg/energysketch-logo-pod-sebou.svg` na úvodní obrazovku a `svg/energysketch-logo.svg` do okna „O aplikaci“ (na tmavém motivu `-bile` varianty),
> - v nabídkách a malých tlačítkách do 32 px `svg/energysketch-ikona-maly.svg`.
>
> Původní ikonu IngeTrazo v aplikaci nahraď, ale v „O aplikaci“ nech uvedení původních autorů podle GPL. Soubory v `brand/energysketch/` neměň. Pokud ti nějaká velikost chybí, napiš to, nevyráběj vlastní.

## Úpravy

Vše se generuje skripty v `zdroj/`:

```bash
python -I zdroj/generuj_svg.py brand/energysketch
python -I zdroj/generuj_png.py brand/energysketch
```

`generuj_svg.py` přijímá cestu k licencovanému písmu Plus Jakarta Sans jako druhý argument (`python generuj_svg.py vystup font.woff2`). Písmo není součástí tohoto balíčku; schválené SVG/PNG/ICO jsou již přibalené a sestavení je znovu negeneruje. `generuj_png.py` renderuje přes Microsoft Edge v režimu bez okna. Tloušťka hrany je v `generuj_svg.py` jako `EDGE = 50`, malá varianta má 80.
