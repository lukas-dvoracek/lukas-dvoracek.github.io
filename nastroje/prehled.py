#!/usr/bin/env python3
"""Vygeneruje přehled projektů a úkolů ze souborů STAV.md a DENIK.md.

Použití:
  python3 nastroje/prehled.py                          # projde složku projekt-log
  python3 nastroje/prehled.py --root /cesta            # projde zadaný strom
  python3 nastroje/prehled.py --root /cesta --out web/ # zapíše index.html + data.json

Výstup je jedna samostatná stránka — data jsou v ní vložená, takže funguje
i jako Artifact (kde se externí soubory nesmí načítat). Vedle ní se zapíše
data.json pro strojové použití.
"""
import html as H
import json
import pathlib
import re
import sys
import urllib.parse
from datetime import date

ROOT = pathlib.Path(__file__).resolve().parent.parent
DNES = date.today()

STAVY = {"aktivní": "act", "pauza": "pau", "nápad": "nap", "hotovo": "hot"}
PORADI = {"aktivní": 0, "pauza": 1, "nápad": 2, "hotovo": 3}


# ---------------------------------------------------------------- parsování

def fm(txt, klic, vychozi=""):
    m = re.search(rf"^{klic}:\s*(.+)$", txt, re.M)
    return m.group(1).strip() if m else vychozi


def sekce(txt, nadpis):
    m = re.search(rf"^## {re.escape(nadpis)}\n(.*?)(?=^## |\Z)", txt, re.M | re.S)
    return m.group(1).strip() if m else ""


def polozky(txt, nadpis):
    return [r.strip()[2:].strip() for r in sekce(txt, nadpis).splitlines()
            if r.strip().startswith("- ")]


def skupiny_ukolu(txt):
    """Rozdělí sekci Úkoly na skupiny podle `### Nadpis`.

    Projekt bez nadpisů má jednu skupinu s nazev=None.
    """
    blok = sekce(txt, "Úkoly")
    skupiny, aktualni = [], (None, [])
    for radek in blok.splitlines():
        h = re.match(r"\s*###\s+(.+)", radek)
        if h:
            if aktualni[1]:
                skupiny.append(aktualni)
            aktualni = (h.group(1).strip(), [])
            continue
        u = _ukol(radek)
        if u:
            aktualni[1].append(u)
    if aktualni[1] or not skupiny:
        skupiny.append(aktualni)
    vaha = {"vysoka": 0, "normal": 1, "nizka": 2}
    return [{"nazev": n, "ukoly": sorted(us, key=lambda x: (x["hotovo"], vaha.get(x["prio"], 1)))}
            for n, us in skupiny]


def _ukol(radek):
    m = re.match(r"\s*- \[( |x|X)\]\s*(.+)", radek)
    if not m:
        return None
    hotovo = m.group(1).lower() == "x"
    text = m.group(2).strip()
    tagy = re.findall(r"@([\w-]+)", text)
    mi = re.search(r"\(#(\d+)\)", text)
    issue = int(mi.group(1)) if mi else None
    md_ = re.search(r"\((\d{4}-\d{2}-\d{2})\)", text)
    termin = md_.group(1) if md_ else None
    prio = "vysoka" if re.search(r"(?<!\S)!(?!\S)", text) else (
        "nizka" if re.search(r"(?<!\S)~(?!\S)", text) else "normal")
    cisty = re.sub(r"@[\w-]+|\(\d{4}-\d{2}-\d{2}\)|\(#\d+\)|(?<!\S)[!~](?!\S)", "", text)
    return {"text": " ".join(cisty.split()), "hotovo": hotovo, "issue": issue,
            "tagy": tagy, "termin": termin, "prio": prio}


def ukoly(txt):
    out = []
    for radek in sekce(txt, "Úkoly").splitlines():
        m = re.match(r"\s*- \[( |x|X)\]\s*(.+)", radek)
        if not m:
            continue
        hotovo = m.group(1).lower() == "x"
        text = m.group(2).strip()
        tagy = re.findall(r"@([\w-]+)", text)
        termin = None
        md = re.search(r"\((\d{4}-\d{2}-\d{2})\)", text)
        if md:
            termin = md.group(1)
        prio = "vysoka" if re.search(r"(?<!\S)!(?!\S)", text) else (
            "nizka" if re.search(r"(?<!\S)~(?!\S)", text) else "normal")
        cisty = re.sub(r"@[\w-]+|\(\d{4}-\d{2}-\d{2}\)|(?<!\S)[!~](?!\S)", "", text)
        out.append({"text": " ".join(cisty.split()), "hotovo": hotovo,
                    "tagy": tagy, "termin": termin, "prio": prio})
    return out


def dni(datum_str):
    try:
        return (DNES - date.fromisoformat(datum_str)).days
    except (ValueError, TypeError):
        return None


def paruj(root):
    """Najde dvojice (STAV.md, DENIK.md) kdekoli pod root.

    Podporuje nasazené rozložení (<projekt>/STAV.md + DENIK.md vedle sebe)
    i rozpracované (stav/<slug>-STAV.md + denik/<slug>-DENIK.md).
    """
    root = pathlib.Path(root)
    nalez = []
    for f in sorted(root.rglob("*STAV.md")):
        if f.name == "STAV-sablona.md":
            continue
        if f.name == "STAV.md":
            denik = f.with_name("DENIK.md")
        else:
            slug = f.name[:-len("-STAV.md")]
            denik = f.parent.parent / "denik" / f"{slug}-DENIK.md"
            if not denik.exists():
                denik = f.with_name(f"{slug}-DENIK.md")
        nalez.append((f, denik))
    return nalez


def nacti(root):
    projekty, videno = [], set()
    for f, denik in paruj(root):
        # soubory z Windows chodí s CRLF — srovnat, ať regexy nechytají \r
        txt = f.read_text(encoding="utf-8").replace("\r\n", "\n")
        slug = fm(txt, "slug", f.parent.name)
        if slug in videno:
            continue
        videno.add(slug)
        posl = None
        if denik.exists():
            data = re.findall(r"^## (\d{4}-\d{2}-\d{2})",
                              denik.read_text(encoding="utf-8"), re.M)
            if data:
                posl = sorted(data)[-1]
        sk = skupiny_ukolu(txt)
        u = [x for s in sk for x in s["ukoly"]]
        projekty.append({
            "nazev": fm(txt, "projekt", slug),
            "slug": slug,
            "stav": fm(txt, "stav", "aktivní"),
            "repo": fm(txt, "repo", ""),
            "aktualizovano": fm(txt, "aktualizovano", ""),
            "co": " ".join(sekce(txt, "Co to je").split()),
            "krok": sekce(txt, "Další krok").lstrip("> ").strip(),
            "ukoly": u,
            "skupiny": sk,
            "blokery": [b for b in polozky(txt, "Blokery")
                        if not b.lower().startswith("žádn")],
            "rozhodnuti": polozky(txt, "Čeká na rozhodnutí"),
            "posledni_zaznam": posl,
            "ticho_dni": dni(posl),
        })
    projekty.sort(key=lambda p: (PORADI.get(p["stav"], 9), -(p["ticho_dni"] or 0)))
    return projekty


# ---------------------------------------------------------------- vykreslení

def md(text):
    t = H.escape(text)
    t = re.sub(r"`([^`]+)`", r"<code>\1</code>", t)
    t = re.sub(r"\*\*([^*]+)\*\*", r"<strong>\1</strong>", t)
    return t


def ukol_html(u, repo=""):
    tridy = ["ukol"]
    if u["hotovo"]:
        tridy.append("hotovy")
    if u["prio"] == "vysoka":
        tridy.append("prio")
    meta = "".join(f'<span class="tag">{H.escape(t)}</span>' for t in u["tagy"])
    if u.get("issue") and repo:
        meta += (f'<a class="issue" href="https://github.com/{repo}/issues/{u["issue"]}"'
                 f' target="_blank" rel="noopener">#{u["issue"]}</a>')
    elif repo and not u["hotovo"]:
        q = urllib.parse.urlencode({"title": u["text"], "labels": "stav-md",
                                    "body": "Založeno z přehledu projektů."})
        meta += (f'<a class="issue jen-web" hidden href="https://github.com/{repo}/issues/new?{q}"'
                 f' target="_blank" rel="noopener">+ issue</a>')
    if u["termin"]:
        po = dni(u["termin"])
        pozde = " pozde" if (po is not None and po > 0 and not u["hotovo"]) else ""
        meta += f'<span class="termin{pozde}">{u["termin"]}</span>'
    return (f'<li class="{" ".join(tridy)}" data-hotovo="{int(u["hotovo"])}" '
            f'data-ukol="{H.escape(u["text"])}" '
            f'data-tagy="{H.escape(" ".join(u["tagy"]))}">'
            f'<span class="box" aria-hidden="true"></span>'
            f'<span class="text">{md(u["text"])}</span>{meta}</li>')


def projekt_html(p):
    otevrene = [u for u in p["ukoly"] if not u["hotovo"]]
    nutne = len([u for u in otevrene if u["prio"] == "vysoka"])
    pocet = f'{len(otevrene)} otevřených'
    if nutne:
        pocet += f' · <b>{nutne} nutných</b>'
    ticho = ""
    if p["ticho_dni"] is not None:
        t = p["ticho_dni"]
        slovo = "dnes" if t == 0 else ("včera" if t == 1 else f"před {t} dny")
        ticho = f'<span class="ticho{" tiche" if t >= 14 else ""}">{slovo}</span>'
    pozn = "".join(f'<li class="blok">{md(b)}</li>' for b in p["blokery"])
    pozn += "".join(f'<li class="rozh">{md(r)}</li>' for r in p["rozhodnuti"])
    pozn = f'<ul class="pozn">{pozn}</ul>' if pozn else ""
    bloky = []
    for s in p["skupiny"]:
        if not s["ukoly"]:
            continue
        hlava = (f'<p class="skupina">{H.escape(s["nazev"])}</p>'
                 if s["nazev"] else "")
        polozky_ = "".join(ukol_html(u, p["repo"]) for u in s["ukoly"])
        bloky.append(f'<div class="skupina-blok">{hlava}'
                     f'<ul class="ukoly">{polozky_}</ul>'
                     f'<button class="vice" type="button" hidden></button></div>')
    seznam = "".join(bloky)
    pozn_odkaz = ""
    if p["repo"]:
        q = urllib.parse.urlencode({
            "title": f'Poznámka: {p["nazev"]}',
            "labels": "poznamka",
            "body": "Co se změnilo nebo co chci změnit:\n\n"})
        pozn_odkaz = (f'<a class="poznamka-odkaz jen-web" hidden'
                      f' href="https://github.com/{p["repo"]}/issues/new?{q}"'
                      f' target="_blank" rel="noopener">+ poznámka</a>')
    tagy = sorted({t for u in p["ukoly"] for t in u["tagy"]})
    return f"""<article class="projekt{' pozor' if p['blokery'] else ''}"
  id="{p['slug']}" data-slug="{p['slug']}" data-stav="{H.escape(p['stav'])}"
  data-tagy="{H.escape(' '.join(tagy))}">
  <header>
    <h2>{H.escape(p['nazev'])}</h2>
    <span class="chip {STAVY.get(p['stav'], 'nap')}">{H.escape(p['stav'])}</span>
    {ticho}
    {pozn_odkaz}
    <span class="pocet">{pocet}</span>
  </header>
  <p class="co">{md(p['co'])}</p>
  <p class="krok"><span class="krok-label">další krok</span>{md(p['krok'])}</p>
  {seznam}
  {pozn}
</article>"""


def stranka(ps):
    vsechny_tagy = sorted({t for p in ps for u in p["ukoly"] for t in u["tagy"]})
    otevrene = sum(len([u for u in p["ukoly"] if not u["hotovo"]]) for p in ps)
    nutne = sum(len([u for u in p["ukoly"]
                     if not u["hotovo"] and u["prio"] == "vysoka"]) for p in ps)
    blok = sum(len(p["blokery"]) for p in ps)
    rozh = sum(len(p["rozhodnuti"]) for p in ps)
    souhrn = " · ".join(
        f"{sum(1 for p in ps if p['stav'] == s)}× {s}"
        for s in ("aktivní", "pauza", "nápad", "hotovo")
        if any(p["stav"] == s for p in ps))

    metriky = "".join(
        f'<div class="metrika"><span class="cislo">{c}</span>'
        f'<span class="popis">{t}</span></div>'
        for c, t in [(len(ps), "projektů"), (otevrene, "otevřených úkolů"),
                     (nutne, "naléhavých"), (blok, "blokerů"),
                     (rozh, "čeká na tebe")])

    f_proj = "".join(
        f'<button class="f" data-filtr="projekt" data-hodnota="{p["slug"]}">'
        f'{H.escape(p["nazev"])}</button>' for p in ps)
    f_stav = "".join(
        f'<button class="f" data-filtr="stav" data-hodnota="{s}">{s}</button>'
        for s in ("aktivní", "pauza", "nápad", "hotovo")
        if any(p["stav"] == s for p in ps))
    f_tag = "".join(
        f'<button class="f" data-filtr="tag" data-hodnota="{t}">{t}</button>'
        for t in vsechny_tagy)

    f_pozn = "".join(
        f'        <option value="{p["slug"]}">{H.escape(p["nazev"])}</option>'
        for p in ps)
    telo = "\n".join(projekt_html(p) for p in ps)
    data = json.dumps({"generovano": DNES.isoformat(), "projekty": ps},
                      ensure_ascii=False, indent=1)

    return f"""<title>Rozdělaná práce</title>
<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Fraunces:opsz,wght@9..144,400;9..144,600&family=Public+Sans:wght@400;500;600&family=IBM+Plex+Mono:wght@400;500&display=swap">
<style>
:root {{
  --ground:#F2F4F1; --surface:#FFFFFF; --ink:#1A1E1A; --muted:#5D655C;
  --line:#DCE0D8; --pine:#2F5D4A; --amber:#8A6714; --rust:#A0402C;
  --slate:#5B6472; --steel:#2E5C7A; --stin:rgba(26,30,26,.06);
  --serif:"Fraunces",Georgia,serif;
  --sans:"Public Sans",system-ui,-apple-system,sans-serif;
  --mono:"IBM Plex Mono",ui-monospace,Menlo,monospace;
}}
@media (prefers-color-scheme: dark) {{
  :root:not([data-theme="light"]) {{
    --ground:#121513; --surface:#1A1E1A; --ink:#E7EAE4; --muted:#98A195;
    --line:#2A2F29; --pine:#7FB79C; --amber:#D3A84C; --rust:#E08D78;
    --slate:#98A3B2; --steel:#83B1D1; --stin:rgba(0,0,0,.3);
  }}
}}
:root[data-theme="dark"] {{
  --ground:#121513; --surface:#1A1E1A; --ink:#E7EAE4; --muted:#98A195;
  --line:#2A2F29; --pine:#7FB79C; --amber:#D3A84C; --rust:#E08D78;
  --slate:#98A3B2; --steel:#83B1D1; --stin:rgba(0,0,0,.3);
}}
* {{ box-sizing:border-box; }}
body {{
  margin:0; background:var(--ground); color:var(--ink);
  font-family:var(--sans); font-size:15px; line-height:1.55;
  -webkit-font-smoothing:antialiased;
}}
.wrap {{ max-width:880px; margin:0 auto; padding-inline:20px; padding-block:44px 72px; }}

.hlavicka {{ display:flex; flex-direction:column; gap:16px; margin-bottom:22px; }}
.hlavicka h1 {{
  font-family:var(--serif); font-weight:600; font-size:clamp(30px,5vw,42px);
  line-height:1.1; margin:0; letter-spacing:-0.015em; text-wrap:balance;
}}
.datum {{
  font-family:var(--mono); font-size:11.5px; letter-spacing:0.08em;
  text-transform:uppercase; color:var(--muted); margin:0;
}}
.metriky {{ display:flex; flex-wrap:wrap; gap:8px 28px; padding-block:16px; border-block:1px solid var(--line); }}
.metrika {{ display:flex; align-items:baseline; gap:7px; }}
.metrika .cislo {{ font-family:var(--serif); font-weight:600; font-size:26px; font-variant-numeric:tabular-nums; line-height:1; }}
.metrika .popis {{ font-size:12.5px; color:var(--muted); }}

.filtry {{
  position:sticky; top:env(safe-area-inset-top, 0px); z-index:5;
  background:var(--ground); padding-block:12px; margin-bottom:14px;
  border-bottom:1px solid var(--line);
  display:flex; flex-direction:column; gap:9px;
}}
.radek {{ display:flex; flex-wrap:wrap; gap:6px; align-items:center; }}
.radek > .label {{
  font-family:var(--mono); font-size:10px; letter-spacing:0.11em;
  text-transform:uppercase; color:var(--muted); margin-right:3px; min-width:52px;
}}
.f {{
  font-family:var(--sans); font-size:12.5px; color:var(--muted);
  background:var(--surface); border:1px solid var(--line); border-radius:3px;
  padding:3px 9px; cursor:pointer; transition:.12s;
}}
.f:hover {{ color:var(--ink); border-color:var(--muted); }}
.f[aria-pressed="true"] {{ background:var(--pine); border-color:var(--pine); color:var(--ground); }}
.f:focus-visible, #hledat:focus-visible {{ outline:2px solid var(--pine); outline-offset:1px; }}
#hledat {{
  flex:1 1 180px; min-width:0; font-family:var(--sans); font-size:13px;
  color:var(--ink); background:var(--surface); border:1px solid var(--line);
  border-radius:3px; padding:5px 9px;
}}
#reset {{ margin-left:auto; }}

.seznam {{ display:flex; flex-direction:column; gap:2px; }}
.projekt {{
  background:var(--surface); border:1px solid var(--line); border-left:3px solid var(--line);
  padding:20px 22px; display:flex; flex-direction:column; gap:9px;
}}
.projekt.pozor {{ border-left-color:var(--rust); }}
.projekt header {{ display:flex; align-items:baseline; flex-wrap:wrap; gap:9px; }}
.projekt h2 {{ font-family:var(--serif); font-weight:600; font-size:20px; margin:0; letter-spacing:-0.01em; flex:1 1 auto; min-width:0; }}
.chip {{
  font-family:var(--mono); font-size:10.5px; font-weight:500; letter-spacing:0.09em;
  text-transform:uppercase; padding:3px 8px; border:1px solid currentColor;
  border-radius:2px; white-space:nowrap;
}}
.chip.act {{ color:var(--pine); }} .chip.pau {{ color:var(--amber); }}
.chip.nap {{ color:var(--slate); }} .chip.hot {{ color:var(--steel); }}
.ticho, .pocet {{ font-family:var(--mono); font-size:11px; color:var(--muted); font-variant-numeric:tabular-nums; white-space:nowrap; }}
.ticho.tiche {{ color:var(--rust); }}
.pocet {{ margin-left:auto; }}
.co {{ margin:0; font-size:13.5px; color:var(--muted); }}
.krok {{ margin:2px 0 0; font-size:15px; line-height:1.5; padding-left:13px; border-left:2px solid var(--pine); }}
.krok-label {{
  display:block; font-family:var(--mono); font-size:10px; font-weight:500;
  letter-spacing:0.11em; text-transform:uppercase; color:var(--pine); margin-bottom:3px;
}}

.ukoly {{ margin:6px 0 0; padding:0; list-style:none; display:flex; flex-direction:column; gap:1px; }}
.ukol {{
  display:flex; align-items:baseline; flex-wrap:wrap; gap:7px;
  font-size:13.5px; padding:4px 0; border-top:1px solid var(--line);
}}
.ukol .box {{
  flex:none; width:9px; height:9px; border:1.5px solid var(--muted);
  border-radius:2px; transform:translateY(1px);
}}
.ukol.prio .box {{ border-color:var(--rust); background:var(--rust); }}
.ukol.hotovy .box {{ border-color:var(--pine); background:var(--pine); }}
.ukol .text {{ flex:1 1 auto; min-width:0; }}
.ukol.hotovy .text {{ color:var(--muted); text-decoration:line-through; text-decoration-color:var(--line); }}
.tag, .termin {{
  font-family:var(--mono); font-size:10px; letter-spacing:0.05em;
  color:var(--muted); border:1px solid var(--line); border-radius:2px;
  padding:1px 5px; white-space:nowrap;
}}
.termin {{ color:var(--amber); border-color:var(--amber); }}
.issue {{
  font-family:var(--mono); font-size:10px; letter-spacing:0.05em; text-decoration:none;
  color:var(--steel); border:1px solid var(--steel); border-radius:2px;
  padding:1px 5px; white-space:nowrap;
}}
.issue:hover {{ background:var(--steel); color:var(--ground); }}
.poznamka-odkaz {{
  font-family:var(--sans); font-size:11.5px; text-decoration:none; color:var(--muted);
  border:1px solid var(--line); border-radius:3px; padding:2px 7px; white-space:nowrap;
}}
.poznamka-odkaz:hover {{ color:var(--amber); border-color:var(--amber); }}
.poznamka-odkaz:focus-visible, .issue:focus-visible {{ outline:2px solid var(--pine); outline-offset:1px; }}
.issue:focus-visible {{ outline:2px solid var(--pine); outline-offset:1px; }}
.termin.pozde {{ color:var(--rust); border-color:var(--rust); }}

.skupina-blok {{ display:flex; flex-direction:column; }}
.skupina {{
  margin:10px 0 2px; font-family:var(--mono); font-size:10px; font-weight:500;
  letter-spacing:0.11em; text-transform:uppercase; color:var(--muted);
}}
.vice {{
  align-self:flex-start; margin-top:2px; font-family:var(--sans); font-size:12px;
  color:var(--muted); background:none; border:1px solid var(--line);
  border-radius:3px; padding:3px 9px; cursor:pointer;
}}
.vice:hover {{ color:var(--ink); border-color:var(--muted); }}
.vice:focus-visible {{ outline:2px solid var(--pine); outline-offset:1px; }}
.pocet b {{ font-weight:500; color:var(--rust); }}

.pozn {{ margin:6px 0 0; padding:0; list-style:none; display:flex; flex-direction:column; gap:5px; }}
.pozn li {{ font-size:13px; color:var(--muted); padding-left:19px; position:relative; }}
.pozn li::before {{ position:absolute; left:0; top:0; font-family:var(--mono); font-size:11px; font-weight:500; }}
.blok::before {{ content:"✕"; color:var(--rust); }}
.rozh::before {{ content:"?"; color:var(--amber); }}
code {{ font-family:var(--mono); font-size:0.9em; }}
strong {{ font-weight:600; color:var(--ink); }}

.prazdno {{ padding:28px 4px; color:var(--muted); font-size:14px; }}

.poznamky {{ margin-top:34px; padding-top:22px; border-top:1px solid var(--line); }}
.poznamky h2 {{ font-family:var(--serif); font-weight:600; font-size:19px; margin:0 0 4px; letter-spacing:-0.01em; }}
.napoveda {{ margin:0 0 12px; font-size:13px; color:var(--muted); }}
#pform {{ display:flex; flex-wrap:wrap; gap:8px; align-items:flex-start; }}
#pprojekt, #ptext {{
  font-family:var(--sans); font-size:13.5px; color:var(--ink);
  background:var(--surface); border:1px solid var(--line); border-radius:3px; padding:7px 9px;
}}
#pprojekt {{ flex:0 0 auto; }}
#ptext {{ flex:1 1 320px; min-width:0; resize:vertical; line-height:1.5; }}
#pulozit {{
  font-family:var(--sans); font-size:13px; font-weight:500;
  background:var(--pine); color:var(--ground); border:1px solid var(--pine);
  border-radius:3px; padding:7px 14px; cursor:pointer;
}}
#pulozit:hover {{ opacity:.88; }}
#pulozit[disabled] {{ opacity:.5; cursor:default; }}
#pulozit:focus-visible, #pprojekt:focus-visible, #ptext:focus-visible {{ outline:2px solid var(--pine); outline-offset:1px; }}
#pstav {{ font-family:var(--mono); font-size:11px; color:var(--muted); align-self:center; }}
#pseznam {{ margin:16px 0 0; padding:0; list-style:none; display:flex; flex-direction:column; gap:1px; }}
#pseznam li {{
  display:flex; align-items:baseline; gap:9px; flex-wrap:wrap;
  font-size:13.5px; padding:7px 0; border-top:1px solid var(--line);
}}
#pseznam .kdy {{ font-family:var(--mono); font-size:10.5px; color:var(--muted); white-space:nowrap; }}
#pseznam .kam {{
  font-family:var(--mono); font-size:10px; letter-spacing:0.05em; color:var(--pine);
  border:1px solid var(--pine); border-radius:2px; padding:1px 5px; white-space:nowrap;
}}
#pseznam .obsah {{ flex:1 1 200px; min-width:0; white-space:pre-wrap; }}
#pseznam .smazat {{
  font-family:var(--sans); font-size:11.5px; color:var(--muted);
  background:none; border:1px solid var(--line); border-radius:3px;
  padding:2px 7px; cursor:pointer;
}}
#pseznam .smazat:hover {{ color:var(--rust); border-color:var(--rust); }}

.pridat {{
  flex:none; font-family:var(--sans); font-size:11px; color:var(--muted);
  background:none; border:1px solid var(--line); border-radius:3px;
  padding:1px 6px; cursor:pointer; opacity:0; transition:opacity .12s;
}}
.ukol:hover .pridat, .pridat:focus-visible {{ opacity:1; }}
.pridat:hover {{ color:var(--pine); border-color:var(--pine); }}
.ukol-pozn {{ margin:0; padding:2px 0 6px 16px; list-style:none; display:flex; flex-direction:column; gap:4px; }}
.ukol-pozn li {{
  display:flex; align-items:baseline; gap:8px; font-size:12.5px; color:var(--ink);
  border-left:2px solid var(--amber); padding-left:9px;
}}
.ukol-pozn .obsah {{ flex:1 1 auto; min-width:0; white-space:pre-wrap; }}
.ukol-pozn .kdy {{ font-family:var(--mono); font-size:10px; color:var(--muted); white-space:nowrap; }}
.ukol-pozn .smazat {{
  font-family:var(--sans); font-size:11px; color:var(--muted); background:none;
  border:1px solid var(--line); border-radius:3px; padding:1px 6px; cursor:pointer;
}}
.ukol-pozn .smazat:hover {{ color:var(--rust); border-color:var(--rust); }}
#pcil {{
  flex:1 1 100%; font-size:12.5px; color:var(--muted);
  display:flex; align-items:center; gap:8px;
}}
#pcil strong {{ font-weight:500; color:var(--ink); }}
#pzrusitcil {{
  font-family:var(--sans); font-size:11px; color:var(--muted); background:none;
  border:1px solid var(--line); border-radius:3px; padding:1px 6px; cursor:pointer;
}}
footer {{ margin-top:34px; padding-top:18px; border-top:1px solid var(--line); font-size:12.5px; color:var(--muted); }}
footer code {{ color:var(--ink); }}
[hidden] {{ display:none !important; }}
@media (max-width:480px) {{
  .projekt {{ padding:17px 16px; }}
  .metriky {{ gap:8px 20px; }}
  .radek > .label {{ min-width:100%; }}
}}
@media (prefers-reduced-motion: reduce) {{ * {{ transition:none !important; }} }}
</style>

<div class="wrap">
  <header class="hlavicka">
    <p class="datum">Stav k {DNES.isoformat()} · {souhrn}</p>
    <h1>Rozdělaná práce</h1>
    <div class="metriky">{metriky}</div>
  </header>

  <div class="filtry">
    <div class="radek"><span class="label">projekt</span>{f_proj}</div>
    <div class="radek"><span class="label">stav</span>{f_stav}</div>
    <div class="radek"><span class="label">štítek</span>{f_tag}</div>
    <div class="radek">
      <input id="hledat" type="search" placeholder="Hledat v úkolech…" aria-label="Hledat v úkolech">
      <button class="f" id="skryt" data-filtr="hotove" aria-pressed="true">skrýt hotové</button>
      <button class="f" id="reset">zrušit filtry</button>
    </div>
  </div>

  <main class="seznam" id="seznam">
{telo}
  </main>
  <p class="prazdno" id="prazdno" hidden>Nic neodpovídá filtru.</p>

  <section class="poznamky" id="poznamky">
    <h2>Poznámky pro Clauda</h2>
    <p class="napoveda" id="pnapoveda">Zapiš, co se změnilo nebo co chceš změnit. Při příští práci to přečtu a promítnu do <code>STAV.md</code> a <code>DENIK.md</code>.</p>
    <p class="napoveda" id="poffline" hidden>Tady se poznámky píšou jako <strong>issues na GitHubu</strong> — u projektu tlačítkem „+ poznámka", k úkolu komentářem pod jeho issue. Claude je čte odtamtud stejně jako poznámky z privátní verze na claude.ai.</p>
    <form id="pform" hidden>
      <p id="pcil" hidden>k úkolu: <strong id="pciltext"></strong>
        <button type="button" id="pzrusitcil">zrušit</button></p>
      <select id="pprojekt" aria-label="Kterého projektu se poznámka týká">
        <option value="obecne">— obecné —</option>
{f_pozn}
      </select>
      <textarea id="ptext" rows="3" placeholder="Např.: Homing je hotový a otestovaný, P1 pořád ne." aria-label="Text poznámky"></textarea>
      <button type="submit" id="pulozit">Uložit</button>
      <span id="pstav" role="status"></span>
    </form>
    <ul id="pseznam" hidden></ul>
  </section>

  <footer>
    Generováno ze souborů <code>STAV.md</code> a <code>DENIK.md</code> skriptem
    <code>nastroje/prehled.py</code>. Zdroj pravdy jsou ty soubory, ne tahle stránka —
    uprav je a přegeneruj. Odškrtnout úkol tady nejde.
  </footer>
</div>

<script type="application/json" id="data">{data}</script>
<script>
(function () {{
  var LIMIT = 5;
  var stav = {{ projekt: new Set(), stav: new Set(), tag: new Set(), hotove: true, text: "" }};
  var rozbaleno = {{}};
  var projekty = Array.prototype.slice.call(document.querySelectorAll(".projekt"));
  var prazdno = document.getElementById("prazdno");

  function prekresli() {{
    var videt = 0;
    projekty.forEach(function (el) {{
      var ok = (!stav.projekt.size || stav.projekt.has(el.dataset.slug))
            && (!stav.stav.size || stav.stav.has(el.dataset.stav));
      var ukoly = Array.prototype.slice.call(el.querySelectorAll(".ukol"));
      var vidUkol = 0;
      ukoly.forEach(function (u) {{
        var tagy = (u.dataset.tagy || "").split(" ").filter(Boolean);
        var t = (!stav.tag.size || tagy.some(function (x) {{ return stav.tag.has(x); }}))
             && (!stav.hotove || u.dataset.hotovo === "0")
             && (!stav.text || u.textContent.toLowerCase().indexOf(stav.text) > -1);
        u.hidden = !t;
        if (t) vidUkol++;
      }});
      if (ok && (stav.tag.size || stav.text) && ukoly.length && !vidUkol) ok = false;

      /* zkrácení dlouhých seznamů — zvlášť pro každou skupinu */
      Array.prototype.forEach.call(el.querySelectorAll(".skupina-blok"), function (blok, i) {{
        var vice = blok.querySelector(".vice");
        if (!vice) return;
        var klic = el.dataset.slug + "#" + i;
        var viditelne = Array.prototype.filter.call(
          blok.querySelectorAll(".ukol"), function (u) {{ return !u.hidden; }});
        var skryto = 0;
        if (!rozbaleno[klic] && viditelne.length > LIMIT) {{
          viditelne.slice(LIMIT).forEach(function (u) {{ u.hidden = true; skryto++; }});
        }}
        if (skryto) {{
          vice.textContent = "+ " + skryto + " " + sklonuj(skryto);
          vice.hidden = false;
        }} else if (rozbaleno[klic] && viditelne.length > LIMIT) {{
          vice.textContent = "zabalit";
          vice.hidden = false;
        }} else {{
          vice.hidden = true;
        }}
        blok.hidden = viditelne.length === 0 && (stav.tag.size > 0 || stav.text !== "" || stav.hotove);
      }});

      el.hidden = !ok;
      if (ok) videt++;
    }});
    prazdno.hidden = videt > 0;
    ulozDoUrl();
  }}

  function sklonuj(n) {{
    if (n === 1) return "další úkol";
    if (n < 5) return "další úkoly";
    return "dalších úkolů";
  }}

  projekty.forEach(function (el) {{
    Array.prototype.forEach.call(el.querySelectorAll(".skupina-blok"), function (blok, i) {{
      var vice = blok.querySelector(".vice");
      if (!vice) return;
      var klic = el.dataset.slug + "#" + i;
      vice.addEventListener("click", function () {{
        rozbaleno[klic] = !rozbaleno[klic];
        prekresli();
      }});
    }});
  }});

  function ulozDoUrl() {{
    var c = [];
    ["projekt", "stav", "tag"].forEach(function (k) {{
      if (stav[k].size) c.push(k + "=" + Array.from(stav[k]).join(","));
    }});
    if (stav.hotove) c.push("otevrene");
    history.replaceState(null, "", c.length ? "#" + c.join("&") : location.pathname);
  }}

  function zUrl() {{
    var h = (location.hash || "").replace(/^#/, "");
    if (h) stav.hotove = false;
    h.split("&").filter(Boolean).forEach(function (c) {{
      if (c === "otevrene") {{ stav.hotove = true; return; }}
      var d = c.split("="), k = d[0];
      if (stav[k] instanceof Set && d[1]) d[1].split(",").forEach(function (v) {{ stav[k].add(v); }});
    }});
    document.querySelectorAll(".f[data-filtr]").forEach(function (b) {{
      var k = b.dataset.filtr;
      if (k === "hotove") b.setAttribute("aria-pressed", String(stav.hotove));
      else b.setAttribute("aria-pressed", String(stav[k].has(b.dataset.hodnota)));
    }});
  }}

  document.querySelectorAll(".f[data-filtr]").forEach(function (b) {{
    b.addEventListener("click", function () {{
      var k = b.dataset.filtr;
      if (k === "hotove") stav.hotove = !stav.hotove;
      else {{
        var v = b.dataset.hodnota;
        if (stav[k].has(v)) stav[k].delete(v); else stav[k].add(v);
      }}
      b.setAttribute("aria-pressed", String(k === "hotove" ? stav.hotove : stav[k].has(b.dataset.hodnota)));
      prekresli();
    }});
  }});

  document.getElementById("hledat").addEventListener("input", function (e) {{
    stav.text = e.target.value.trim().toLowerCase();
    prekresli();
  }});

  document.getElementById("reset").addEventListener("click", function () {{
    stav.projekt.clear(); stav.stav.clear(); stav.tag.clear();
    stav.hotove = true; stav.text = "";
    rozbaleno = {{}};
    document.getElementById("hledat").value = "";
    document.querySelectorAll(".f[data-filtr]").forEach(function (b) {{
      b.setAttribute("aria-pressed", b.dataset.filtr === "hotove" ? "true" : "false");
    }});
    prekresli();
  }});

  zUrl();
  prekresli();
}})();

/* Poznámky — jen v publikovaném Artifactu, kde běží claude.use("db").
   Na GitHub Pages window.claude neexistuje a sekce zůstane skrytá. */
(function () {{
  var offline = document.getElementById("poffline");
  var napoveda = document.getElementById("pnapoveda");
  napoveda.hidden = true;
  /* Bez runtime (GitHub Pages) víme hned. S runtime počkáme, jak dopadne
     use("db") — jinak by hláška v privátní verzi na chvíli probliknula. */
  function odhalWebOdkazy() {{
    Array.prototype.forEach.call(document.querySelectorAll(".jen-web"), function (e) {{
      e.hidden = false;
    }});
  }}
  if (!(window.claude && typeof window.claude.use === "function")) {{
    offline.hidden = false;
    odhalWebOdkazy();
    return;
  }}
  var sekce = document.getElementById("poznamky");
  var form = document.getElementById("pform");
  var text = document.getElementById("ptext");
  var projekt = document.getElementById("pprojekt");
  var tlacitko = document.getElementById("pulozit");
  var hlaska = document.getElementById("pstav");
  var seznam = document.getElementById("pseznam");
  var nazvy = {{}};
  Array.prototype.forEach.call(projekt.options, function (o) {{ nazvy[o.value] = o.text; }});

  function rekni(t) {{ hlaska.textContent = t || ""; }}

  var cil = document.getElementById("pcil");
  var cilText = document.getElementById("pciltext");
  var aktualniUkol = null;

  function nastavCil(slug, ukol) {{
    aktualniUkol = ukol;
    if (ukol) {{
      projekt.value = slug;
      cilText.textContent = ukol;
      cil.hidden = false;
    }} else {{
      cil.hidden = true;
    }}
  }}

  document.getElementById("pzrusitcil").addEventListener("click", function () {{
    nastavCil(null, null);
  }});

  function radekPoznamky(v, smazFn, trida) {{
    var li = document.createElement("li");
    var kdy = document.createElement("span");
    kdy.className = "kdy";
    kdy.textContent = (v.vytvoreno || "").slice(0, 16).replace("T", " ");
    li.appendChild(kdy);
    if (trida === "seznam") {{
      var kam = document.createElement("span");
      kam.className = "kam";
      kam.textContent = nazvy[v.projekt] || v.projekt || "obecné";
      li.appendChild(kam);
    }}
    var obsah = document.createElement("span");
    obsah.className = "obsah";
    obsah.textContent = v.text || "";
    li.appendChild(obsah);
    var smazat = document.createElement("button");
    smazat.className = "smazat";
    smazat.type = "button";
    smazat.textContent = "smazat";
    smazat.addEventListener("click", smazFn);
    li.appendChild(smazat);
    return li;
  }}

  window.claude.use("db").then(function (db) {{
    if (!db) {{ offline.hidden = false; odhalWebOdkazy(); return; }}
    napoveda.hidden = false;
    form.hidden = false;
    seznam.hidden = false;
    var kolekce = db.collection("poznamky");

    function smaz(id) {{
      return function () {{
        kolekce.doc(id).delete().then(function () {{ rekni("smazáno"); }},
          function (e) {{ rekni("smazat se nepovedlo (" + e.code + ")"); }});
      }};
    }}

    /* tlačítko u každého úkolu */
    document.querySelectorAll(".projekt").forEach(function (art) {{
      var slug = art.dataset.slug;
      art.querySelectorAll(".ukol").forEach(function (u) {{
        var b = document.createElement("button");
        b.className = "pridat";
        b.type = "button";
        b.textContent = "+ poznámka";
        b.title = "Přidat poznámku k tomuhle úkolu";
        b.addEventListener("click", function () {{
          nastavCil(slug, u.dataset.ukol || "");
          text.focus();
          sekce.scrollIntoView({{ behavior: "smooth", block: "center" }});
        }});
        u.appendChild(b);
      }});
    }});

    kolekce.orderBy("vytvoreno", "desc").limit(200).onSnapshot(function (snap) {{
      seznam.textContent = "";
      document.querySelectorAll(".ukol-pozn").forEach(function (e) {{ e.remove(); }});

      snap.docs.forEach(function (d) {{
        var v = d.data() || {{}};
        if (v.ukol) {{
          var art = document.querySelector('.projekt[data-slug="' + v.projekt + '"]');
          var li = art && Array.prototype.filter.call(
            art.querySelectorAll(".ukol"),
            function (x) {{ return x.dataset.ukol === v.ukol; }})[0];
          if (li) {{
            var box = li.nextElementSibling;
            if (!box || !box.classList.contains("ukol-pozn")) {{
              box = document.createElement("ul");
              box.className = "ukol-pozn";
              li.parentNode.insertBefore(box, li.nextSibling);
            }}
            box.appendChild(radekPoznamky(v, smaz(d.id), "ukol"));
            return;
          }}
        }}
        seznam.appendChild(radekPoznamky(v, smaz(d.id), "seznam"));
      }});
    }}, function (e) {{ rekni("poznámky se nenačetly (" + e.code + ")"); }});

    form.addEventListener("submit", function (e) {{
      e.preventDefault();
      var obsah = text.value.trim();
      if (!obsah) return;
      tlacitko.disabled = true;
      rekni("ukládám…");
      var telo = {{
        projekt: projekt.value,
        text: obsah,
        vytvoreno: new Date().toISOString(),
        stav: "nova"
      }};
      if (aktualniUkol) telo.ukol = aktualniUkol;
      kolekce.add(telo).then(function () {{
        text.value = "";
        nastavCil(null, null);
        rekni("uloženo");
        setTimeout(function () {{ rekni(""); }}, 2500);
      }}, function (err) {{
        rekni("neuložilo se (" + err.code + ")");
      }}).then(function () {{ tlacitko.disabled = false; }},
               function () {{ tlacitko.disabled = false; }});
    }});
  }});
}})();
</script>
"""


def main():
    argv = sys.argv[1:]
    scan, out_dir, out_file = ROOT, None, None
    if "--root" in argv:
        i = argv.index("--root"); scan = pathlib.Path(argv[i + 1]); del argv[i:i + 2]
    if "--out" in argv:
        i = argv.index("--out"); out_dir = pathlib.Path(argv[i + 1]); del argv[i:i + 2]
    if argv:
        out_file = pathlib.Path(argv[0])

    ps = nacti(scan)
    html = stranka(ps)
    data = json.dumps({"generovano": DNES.isoformat(), "projekty": ps},
                      ensure_ascii=False, indent=1)

    cile = []
    if out_dir:
        out_dir.mkdir(parents=True, exist_ok=True)
        (out_dir / "index.html").write_text(html, encoding="utf-8")
        (out_dir / "data.json").write_text(data + "\n", encoding="utf-8")
        cile += [out_dir / "index.html", out_dir / "data.json"]
    if out_file or not out_dir:
        cil = out_file or (ROOT / "prehled.html")
        cil.write_text(html, encoding="utf-8")
        cile.append(cil)

    otevrene = sum(len([u for u in p["ukoly"] if not u["hotovo"]]) for p in ps)
    print(f"{len(ps)} projektů, {otevrene} otevřených úkolů → "
          + ", ".join(str(c) for c in cile))


if __name__ == "__main__":
    main()
