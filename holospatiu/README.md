# Holospațiu — Kelion generează spațiul 3D după subiect

Cerut de Adrian (24 oct 2026): în camera holospațiu de pe `kelionai.app/app/voce`, Kelion are **dreptul să genereze singur spațiul 3D real** potrivit subiectului conversației — nu doar un obiect lângă el, ci tot locul în care stă.

## Ce face

Unealta creierului **`holo_space`** (în `/opt/kelion-voce/server.js`) → pagina (`index.html`) → `avatar.js` (`setSpace`) → modulul **`th/spatiu3d.js`** (acest folder).

### 1. Mod `real` — orice loc de pe Pământ, la scară 1:1
- **Relief real**: AWS Terrain Tiles (Terrarium PNG), două niveluri de detaliu (aproape ~10 m/pixel, departe până la ~4 km).
- **Clădiri reale** cu înălțimile lor (`render_height`, `render_min_height`, părțile clădirilor), **străzi, apă, parcuri, păduri**: OpenStreetMap prin tile-urile vectoriale OpenFreeMap. Fațade cu ferestre la scară (etaj 2,9–4,1 m, variat pe clădire); monumentul-țintă e din piatră, fără ferestre.
- **Soarele pe poziția reală** pentru locul respectiv, la ora reală de acum sau la `hour` (ora solară locală).
- **Alegerea punctului de stat**: ținta = cea mai proeminentă clădire de lângă punct (înălțime × suprafață × apropiere, cu părțile ei grupate). Kelion e pus pe un loc liber (nu în clădiri, nu pe apă, cu loc și pentru cameră), la o distanță la care ținta încape în cadru, din direcția cu **linie de vedere liberă** (16 direcții testate, sau `view_from` cerut).
- Geocodare după nume: Nominatim (OSM).
- Toate sursele sunt **gratuite, fără cheie, cu CORS deschis** → cost zero (plafonul de 100 GBP nu e atins).
- Limită onestă: clădirile sunt volume (forma + înălțimea reale), nu fotografii; monumente complicate (ex. Turnul Eiffel) apar ca volume simplificate.

### 2. Mod `generat` — un cadru după subiect
Presetări: `plaja, ocean, insula, subacvatic, cosmos, luna, marte, vulcan, jungla, savana, arctica, pestera, oras, oras_noapte, templu, sala, birou, camera, cer, lac, padure, munte, zapada, desert, campie, apus, noapte`.
Totul se poate personaliza: `sky`, `ground`, `water`, `fog`, `elements` (înlocuiesc) / `extra_elements` (se adaugă) cu `kind` din: brazi, copaci, chiparosi, acacii, palmieri, ferigi, iarba, flori, cactusi, pietre, stalagmite, cristale, gheata, coloane, ruine, cladiri, felinare, nori, mare_de_nori, stele, nebuloasa, planete, asteroizi, corali, alge, pesti, bule, ninsoare, ploaie, praf, scantei, licurici, raze, vulcan.

În ambele moduri: `objects` (obiecte 3D ca la `holo_create`: `{name}` din catalog sau `{parts}` construite), `label`, `off:true` (închide).

## Exemple de apel (creierul le trimite singur)
```json
{ "mode": "real", "place": "Colosseum, Roma" }
{ "mode": "real", "lat": 45.6427, "lon": 25.5887, "label": "Piata Sfatului", "hour": 17 }
{ "preset": "subacvatic" }
{ "preset": "cosmos", "label": "Sistemul solar", "extra_elements": [{ "kind": "planete", "count": 6 }] }
{ "preset": "templu", "label": "Atena antica", "hour": 18 }
{ "off": true }
```
Rezultatul întors creierului spune exact ce s-a generat (ex. „556 clădiri reale, relief real, Kelion stă la 153 m de țintă, privind dinspre sud, cu vederea liberă”), ca să nu raporteze nimic neconfirmat.

## Ce trebuie să știe Kelion și Dots
- Regulile pentru Kelion sunt în `/opt/kelion-voce/work/corp-instructiuni.txt` (secțiunea „SPATIUL 3D DUPA SUBIECT”): generează **singur** spațiul când subiectul are un loc sau un cadru; îl schimbă doar când se schimbă subiectul; spune doar ce confirmă rezultatul.
- Comenzile vocale vechi rămân: „pune peisaj munte/pădure/…” (lume3d.js); `oras`, `cer`, `savana` merg acum pe presetările noi din spatiu3d.js.
- Modulul se încarcă doar la nevoie (import dinamic) și nu schimbă nimic din pagină până nu e apelat.

## Verificare
- Banc de test pe Contabo (Chrome headless separat, profil temporar, port local 8799 — nu atinge sesiunile lui Adrian): 26 de spații, toate generate fără erori de pagină.
- Test pe pagina reală `http://127.0.0.1:8796/app/voce/` (avatarul Kelion real): `window.kelion.space(...)` pentru Roma, Londra, București, Brașov, sub apă, sistem solar (+ obiect robot), Marte, Atena antică, oraș, plajă; plus calea motorului (`scene: oras`) și închiderea.
- Fișierul live are sha256 egal cu `holospatiu/spatiu3d.js` din acest branch.
