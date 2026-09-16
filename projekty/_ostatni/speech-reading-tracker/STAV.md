---
projekt: Transkripce
slug: speech-reading-tracker
stav: hotovo
aktualizovano: 2026-09-16
---

## Co to je
Jednoduchý Windows nástroj pro přepis zvukových souborů (m4a, mp3, wav, mp4) na text. Běží lokálně a offline přes faster-whisper. Default čeština.

## Kde to stojí
- Funkční a zabalené: `setup.bat`, `run.bat`, `run-console.bat`, `package.bat`, `Transkripce.spec` pro PyInstaller, hotový `dist/` i `Transkripce.zip`.
- GUI `transcribe_gui.py` — přidání více souborů najednou, volba modelu, jazyka a zařízení, volitelné časové značky `[mm:ss -> mm:ss]`. Výstup `.txt` vedle původního souboru.
- Modely tiny/base/small/medium/large-v3, default `small` + `cs` + `auto`. Pro češtinu doporučeno small nebo medium.
- GPU zrychlení přes `setup-gpu.bat` (cuBLAS + cuDNN). Režim `auto` zkusí CUDA a při jakémkoli problému sám spadne na CPU. Typ výpočtu volí sám: GPU `int8_float16`, CPU `int8` + všechna jádra.
- VAD filtr zapnutý napevno. Samostatný ffmpeg není potřeba — dekódování zajistí PyAV.
- README je kompletní: instalace, použití, tabulka modelů, GPU, kam se ukládá model.

## Další krok
> Nic akutního. Nástroj je hotový a použitelný.

## Úkoly
- [ ] Ověřit identitu projektu vůči Speech Reading Trackeru @otazka
- [ ] Přesunout `Transkripce.zip` (100 MB) mimo git repo a historii @docs
- [ ] Projít `backups/` — archivovat nebo uklidit staré zálohy @docs ~
- [x] GUI s dávkovým přepisem více souborů @app
- [x] Volba modelu, jazyka a zařízení @app
- [x] Časové značky `[mm:ss -> mm:ss]` @app
- [x] GPU zrychlení přes cuBLAS a cuDNN s fallbackem na CPU @perf
- [x] Zabalení přes PyInstaller — `dist/` i ZIP @release
- [x] README s instalací, modely a GPU @docs

## Blokery
- Žádné.

## Čeká na rozhodnutí
- **Pozor, ověř identitu projektu.** V dřívějších konverzacích figuroval „Speech Reading Tracker" — Python aplikace na trénink čtení nahlas (zvýrazňování slov během čtení, statistiky WPM a přesnosti, tkinter GUI, enginy Vosk / PocketSphinx / Google Speech API, IDLE kompatibilita). To je jiná aplikace než Transkripce. Buď se z jednoho vyvinulo druhé, nebo ten reading tracker leží někde jinde. Řekni které, a STAV.md se opraví.

## Autority
- `README.md` ve složce projektu.
