#!/usr/bin/env node
/**
 * Stáhne STAV.md a DENIK.md z projektových repů do `tmp-stavy/<repo>/`,
 * odkud je pak přečte prehled.py.
 *
 * Seznam repů je v `projekty/_zdroje.json`. Token musí mít na těch repech
 * právo číst obsah — repozitáře jsou privátní.
 */
import { readFileSync, writeFileSync, mkdirSync, cpSync, existsSync } from 'node:fs';

const TOKEN = process.env.GITHUB_TOKEN;
const CIL = 'tmp-stavy';

if (!TOKEN) {
  console.error('Chybí GITHUB_TOKEN (secret PROJEKTY_SYNC). Bez něj privátní repa nepřečtu.');
  process.exit(1);
}

const zdroje = JSON.parse(readFileSync('projekty/_zdroje.json', 'utf8')).repos;

async function soubor(repo, cesta) {
  const r = await fetch(`https://api.github.com/repos/${repo}/contents/${cesta}`, {
    headers: {
      authorization: `Bearer ${TOKEN}`,
      accept: 'application/vnd.github+json',
      'user-agent': 'prehled-projektu',
    },
  });
  if (r.status === 404) return null;
  if (!r.ok) throw new Error(`${repo}/${cesta} → ${r.status} ${await r.text()}`);
  const d = await r.json();
  return Buffer.from(d.content, 'base64').toString('utf8');
}

let stazeno = 0;
for (const repo of zdroje) {
  const slozka = `${CIL}/${repo.split('/')[1]}`;
  const stav = await soubor(repo, 'STAV.md');
  if (!stav) { console.log(`— ${repo}: STAV.md tam není, přeskakuji`); continue; }
  mkdirSync(slozka, { recursive: true });
  writeFileSync(`${slozka}/STAV.md`, stav, 'utf8');
  const denik = await soubor(repo, 'DENIK.md');
  if (denik) writeFileSync(`${slozka}/DENIK.md`, denik, 'utf8');
  console.log(`✓ ${repo}${denik ? ' (STAV.md + DENIK.md)' : ' (jen STAV.md)'}`);
  stazeno++;
}

// Projekty bez vlastního repa žijí přímo tady
const OSTATNI = 'projekty/_ostatni';
if (existsSync(OSTATNI)) {
  cpSync(OSTATNI, CIL, { recursive: true });
  console.log(`✓ projekty bez repa z ${OSTATNI}/`);
}

if (!stazeno) { console.error('Nestáhl jsem ani jeden STAV.md — nebudu generovat prázdný přehled.'); process.exit(1); }
console.log(`Staženo ${stazeno} z ${zdroje.length} projektů.`);
