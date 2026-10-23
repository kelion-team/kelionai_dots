// SPATIU 3D DUPA SUBIECT pentru holopuntea lui Kelion.
// Doua moduri:
//  1) REAL: orice loc de pe Pamant, la scara 1:1, in jurul lui Kelion: relief real (AWS Terrarium), cladiri reale cu
//     inaltimile lor, strazi, apa, parcuri si paduri (OpenStreetMap prin OpenFreeMap), soarele pe pozitia reala pentru ora locului.
//     Toate sursele sunt gratuite, fara cheie, cu CORS deschis. Date (c) OpenStreetMap contributors; relief: Mapzen/AWS Terrain Tiles.
//  2) GENERAT: spatiu compus dupa subiect din presetari (ocean, sub apa, cosmos, luna, marte, vulcan, jungla, oras, templu, pestera,
//     sala, birou...) si/sau elemente cerute de creier (copaci, coloane, cladiri, planete, pesti, corali, cristale...).
// Kelion sta in (0,0,0) cu fata spre camera (+z); privitorul vede ce e in spatele lui (-z = nord in modul real).
import * as THREE from 'three';
import { Sky } from 'three/addons/objects/Sky.js';
import { ImprovedNoise } from 'three/addons/math/ImprovedNoise.js';
import { mergeGeometries } from 'three/addons/utils/BufferGeometryUtils.js';

const D2R = Math.PI / 180;
const clamp = (v, a, b) => Math.max(a, Math.min(b, v));
const num = (v, d) => (v === undefined || v === null || v === '' || !isFinite(+v)) ? d : +v;
const col = (v, d) => { try { return new THREE.Color(v === undefined || v === null || v === '' ? d : v); } catch { return new THREE.Color(d); } };
const rnd = (a, b) => a + Math.random() * (b - a);
const pick = a => a[Math.floor(Math.random() * a.length)];
const withTimeout = (p, ms, what) => Promise.race([p, new Promise((_, ko) => setTimeout(() => ko(new Error('timeout ' + what)), ms))]);
const fetchT = (url, ms = 15000, opt = {}) => withTimeout(fetch(url, opt), ms, url.split('/')[2]);

// ---------------------------------------------------------------- PRESETARI (spatii generate)
// ground.type: teren | plat | apa | nimic | interior | pestera
// sky.type: fizic (cer real cu soare, ora din hour) | gradient (top/horizon/bottom) | cosmos (negru cu stele)
export const PRESETS = {
  plaja: { label: 'Plaja', sky: { type: 'fizic', hour: 15 }, ground: { type: 'teren', elev: 6, mount: 0.4, low: '#e3cf98', mid: '#d8c089', high: '#8f9a5a', peak: '#7a7a6a', beach: 16 }, water: { level: -0.9, color: '#2f7fa8', waves: true }, fog: { color: '#cfe4f2', near: 60, far: 600 },
    elements: [{ kind: 'palmieri', count: 70, min: 6, radius: 50 }, { kind: 'pietre', count: 40, min: 6, radius: 80, color: '#9b9182' }] },
  ocean: { label: 'Ocean', sky: { type: 'fizic', hour: 16 }, ground: { type: 'apa' }, water: { level: -0.02, color: '#1f5f86', waves: true }, platform: true, fog: { color: '#c9dcea', near: 80, far: 900 },
    elements: [{ kind: 'nori', count: 40 }] },
  insula: { label: 'Insula tropicala', sky: { type: 'fizic', hour: 13 }, ground: { type: 'teren', elev: 10, mount: 0.8, low: '#e6d3a0', mid: '#4f8a35', high: '#3d6e2c', peak: '#6b6458', island: 70 }, water: { level: -0.9, color: '#2a8bb0', waves: true }, fog: { color: '#d4e8f4', near: 80, far: 900 },
    elements: [{ kind: 'palmieri', count: 70, min: 7, radius: 65 }, { kind: 'copaci', count: 120, min: 15, radius: 60, color: '#2f6b2a' }] },
  subacvatic: { label: 'Sub apa', sky: { type: 'gradient', top: '#3fa9d6', horizon: '#0f4c75', bottom: '#06223a' }, ground: { type: 'teren', elev: 4, mount: 0.5, low: '#c9b98a', mid: '#b3a47a', high: '#8c8a76', peak: '#6d6a5c' }, fog: { color: '#0d4a6e', density: 0.045 }, underwater: true,
    elements: [{ kind: 'corali', count: 260, min: 3, radius: 45 }, { kind: 'alge', count: 220, min: 3, radius: 50 }, { kind: 'pesti', count: 90, radius: 25 }, { kind: 'bule', count: 900, radius: 20 }, { kind: 'raze', count: 10 }, { kind: 'pietre', count: 80, min: 4, radius: 50, color: '#5d6b6a' }] },
  cosmos: { label: 'Spatiul cosmic', sky: { type: 'cosmos' }, ground: { type: 'nimic' }, platform: true, background: '#000005',
    elements: [{ kind: 'stele', count: 9000 }, { kind: 'nebuloasa', count: 14 }, { kind: 'planete', count: 4 }, { kind: 'asteroizi', count: 220 }] },
  luna: { label: 'Pe Luna', sky: { type: 'cosmos' }, ground: { type: 'teren', elev: 7, mount: 1.2, low: '#8c8c8c', mid: '#7a7a7a', high: '#9a9a9a', peak: '#b0b0b0', craters: 60 }, background: '#000003', sunLight: { color: '#ffffff', intensity: 3.2, alt: 25, az: 130 },
    elements: [{ kind: 'stele', count: 8000 }, { kind: 'planete', count: 1, preset: 'pamant', distance: 700, size: 70, alt: 8, az: 12 }, { kind: 'pietre', count: 260, min: 5, radius: 120, color: '#8a8a8a' }] },
  marte: { label: 'Pe Marte', sky: { type: 'gradient', top: '#c98b5b', horizon: '#e3b48a', bottom: '#8a4a2a' }, ground: { type: 'teren', elev: 18, mount: 1.6, low: '#b5562f', mid: '#9c4a28', high: '#7d3b22', peak: '#c97a52' }, fog: { color: '#d9a07a', near: 40, far: 420 }, sunLight: { color: '#ffe2c4', intensity: 2.2, alt: 35, az: 150 },
    elements: [{ kind: 'pietre', count: 420, min: 5, radius: 140, color: '#7a3a22' }, { kind: 'praf', count: 1500, radius: 30, color: '#e0a27a' }] },
  vulcan: { label: 'Vulcan', sky: { type: 'gradient', top: '#1a1414', horizon: '#5a2a1a', bottom: '#120c0c' }, ground: { type: 'teren', elev: 8, mount: 1, low: '#2a2522', mid: '#1f1b19', high: '#3a2e28', peak: '#4a3a30', lava: true }, fog: { color: '#2a1a16', near: 60, far: 1400 }, sunLight: { color: '#ff9a66', intensity: 0.9, alt: 30, az: 220 },
    elements: [{ kind: 'vulcan', count: 1 }, { kind: 'scantei', count: 900, radius: 25 }, { kind: 'pietre', count: 300, min: 5, radius: 110, color: '#1e1a18' }] },
  jungla: { label: 'Jungla', sky: { type: 'fizic', hour: 12 }, ground: { type: 'teren', elev: 12, mount: 0.8, low: '#3e6b24', mid: '#2f5a1f', high: '#4a5a32', peak: '#6b6458' }, water: { level: -1.2, color: '#3d6f5f' }, fog: { color: '#a9c4a0', near: 18, far: 220 },
    elements: [{ kind: 'copaci', count: 900, min: 6, radius: 120, color: '#255c1f', size: 1.5 }, { kind: 'palmieri', count: 160, min: 6, radius: 70 }, { kind: 'ferigi', count: 900, min: 2.5, radius: 26 }, { kind: 'flori', count: 300, min: 2, radius: 18 }, { kind: 'licurici', count: 200, radius: 14 }] },
  savana: { label: 'Savana', sky: { type: 'fizic', hour: 17.5 }, ground: { type: 'teren', elev: 10, mount: 0.7, low: '#b9a35a', mid: '#a8924a', high: '#8a7a4a', peak: '#7a6a50' }, fog: { color: '#e3cfa6', near: 50, far: 600 },
    elements: [{ kind: 'acacii', count: 90, min: 10, radius: 160 }, { kind: 'iarba', count: 9000, color: '#b8a052', radius: 18 }, { kind: 'pietre', count: 90, min: 8, radius: 120, color: '#8a7b62' }] },
  arctica: { label: 'Arctica', sky: { type: 'fizic', hour: 11 }, ground: { type: 'teren', elev: 14, mount: 1.2, low: '#e9f1f7', mid: '#dfe9f2', high: '#cfdbe6', peak: '#ffffff' }, water: { level: -1.0, color: '#3b6f8f' }, fog: { color: '#e2ecf4', near: 30, far: 450 },
    elements: [{ kind: 'gheata', count: 120, min: 8, radius: 140 }, { kind: 'ninsoare', count: 4000, radius: 25 }] },
  pestera: { label: 'Pestera', sky: { type: 'gradient', top: '#050506', horizon: '#0c0b0a', bottom: '#050505' }, ground: { type: 'pestera', low: '#3a332c', mid: '#2e2924', high: '#4a4038', peak: '#574a40' }, fog: { color: '#0b0a09', near: 6, far: 60 }, sunLight: { color: '#ffb070', intensity: 0.25, alt: 60, az: 180 },
    elements: [{ kind: 'cristale', count: 180, min: 3, radius: 22 }, { kind: 'stalagmite', count: 160, min: 3, radius: 24 }, { kind: 'licurici', count: 120, radius: 10, color: '#66e0ff' }] },
  oras: { label: 'Oras', sky: { type: 'fizic', hour: 16 }, ground: { type: 'plat', color: '#5d6066', texture: 'asfalt' }, fog: { color: '#c6d2de', near: 60, far: 700 },
    elements: [{ kind: 'cladiri', count: 260, min: 14, radius: 260 }, { kind: 'felinare', count: 24, radius: 40 }, { kind: 'copaci', count: 60, min: 9, radius: 60, color: '#3f6f2c', size: 0.8 }] },
  oras_noapte: { label: 'Oras noaptea', sky: { type: 'fizic', hour: 22.5 }, ground: { type: 'plat', color: '#3a3c42', texture: 'asfalt' }, fog: { color: '#141a28', near: 40, far: 600 },
    elements: [{ kind: 'stele', count: 2500 }, { kind: 'cladiri', count: 280, min: 14, radius: 260 }, { kind: 'felinare', count: 30, radius: 45 }] },
  templu: { label: 'Templu antic', sky: { type: 'fizic', hour: 17 }, ground: { type: 'plat', color: '#d9ccb0', texture: 'marmura', size: 60, around: { elev: 10, low: '#8a9a5a', mid: '#7a8a50', high: '#8a8070', peak: '#9a9080' } }, fog: { color: '#e6dccb', near: 60, far: 600 },
    elements: [{ kind: 'coloane', count: 16, radius: 11, height: 9, color: '#efe6d2' }, { kind: 'ruine', count: 40, min: 14, radius: 60, color: '#d8cdb6' }, { kind: 'chiparosi', count: 60, min: 30, radius: 140 }] },
  sala: { label: 'Sala', ground: { type: 'interior', width: 18, depth: 26, height: 7, floor: 'marmura', floorColor: '#e8e2d6', wall: '#e9e4da', ceiling: '#f4f1ea', windows: true, lights: 6 } },
  birou: { label: 'Birou', ground: { type: 'interior', width: 10, depth: 14, height: 3.2, floor: 'lemn', floorColor: '#b08a60', wall: '#dfe3e6', ceiling: '#f2f2f2', windows: true, lights: 4 } },
  camera: { label: 'Camera', ground: { type: 'interior', width: 8, depth: 10, height: 2.9, floor: 'lemn', floorColor: '#9c7a55', wall: '#efe7dc', ceiling: '#f7f5f0', windows: true, lights: 2 } },
  cer: { label: 'Deasupra norilor', sky: { type: 'fizic', alt: 9, az: 20 }, ground: { type: 'nimic' }, platform: true, fog: { color: '#f2e4d6', near: 300, far: 2600 },
    elements: [{ kind: 'mare_de_nori', count: 1 }, { kind: 'nori', count: 60 }] },
  padure: { label: 'Padure', sky: { type: 'fizic', hour: 10 }, ground: { type: 'teren', elev: 22, mount: 1, low: '#4f7a2e', mid: '#3f6a28', high: '#6b6458', peak: '#f2f4f7' }, fog: { color: '#b8c8d8', near: 25, far: 300 },
    elements: [{ kind: 'brazi', count: 900, min: 9, radius: 150 }, { kind: 'copaci', count: 300, min: 9, radius: 120 }, { kind: 'iarba', count: 8000 }, { kind: 'pietre', count: 160, min: 6, radius: 100 }] },
  munte: { label: 'Munte', sky: { type: 'fizic', hour: 11 }, ground: { type: 'teren', elev: 45, mount: 1.9, low: '#5b7c35', mid: '#4a6a2c', high: '#77705f', peak: '#ffffff' }, fog: { color: '#c4d2e0', near: 40, far: 650 },
    elements: [{ kind: 'brazi', count: 600, min: 9, radius: 160 }, { kind: 'pietre', count: 320, min: 5, radius: 140 }, { kind: 'iarba', count: 6000 }] },
  zapada: { label: 'Iarna', sky: { type: 'fizic', hour: 12 }, ground: { type: 'teren', elev: 30, mount: 1.4, low: '#e9eef3', mid: '#e2e9f0', high: '#c9d2db', peak: '#ffffff' }, fog: { color: '#dfe7ef', near: 25, far: 380 },
    elements: [{ kind: 'brazi', count: 600, min: 9, radius: 150, color: '#2c4a32' }, { kind: 'ninsoare', count: 4000 }] },
  desert: { label: 'Desert', sky: { type: 'fizic', hour: 14, turbidity: 6 }, ground: { type: 'teren', elev: 16, mount: 1.1, low: '#e2c08a', mid: '#d6b27a', high: '#c9a06a', peak: '#a9714a' }, fog: { color: '#e8d6b8', near: 50, far: 650 },
    elements: [{ kind: 'cactusi', count: 140, min: 9, radius: 140 }, { kind: 'pietre', count: 200, min: 6, radius: 140, color: '#a9714a' }] },
  campie: { label: 'Campie', sky: { type: 'fizic', hour: 14 }, ground: { type: 'teren', elev: 8, mount: 0.6, low: '#6d9a3a', mid: '#5f8a32', high: '#7a7465', peak: '#9a9488' }, fog: { color: '#c8d8e6', near: 50, far: 600 },
    elements: [{ kind: 'copaci', count: 220, min: 12, radius: 160 }, { kind: 'iarba', count: 9000 }, { kind: 'flori', count: 300 }] },
  apus: { label: 'Apus', sky: { type: 'fizic', alt: 3, az: 0 }, ground: { type: 'teren', elev: 26, mount: 1.3, low: '#4a6a2c', mid: '#3f5f28', high: '#5f584d', peak: '#f4e9e0' }, water: { level: -0.9, color: '#3a5a7a', waves: true }, fog: { color: '#d9a37a', near: 40, far: 600 },
    elements: [{ kind: 'brazi', count: 500, min: 10, radius: 150 }, { kind: 'iarba', count: 6000 }] },
  noapte: { label: 'Noapte', sky: { type: 'fizic', hour: 23 }, ground: { type: 'teren', elev: 26, mount: 1.3, low: '#22331a', mid: '#1e2e18', high: '#3a3833', peak: '#b8c4d6' }, fog: { color: '#0b1020', near: 30, far: 400 },
    elements: [{ kind: 'brazi', count: 600, min: 10, radius: 150, color: '#16301a' }, { kind: 'licurici', count: 160 }] },
  lac: { label: 'Lac de munte', sky: { type: 'fizic', hour: 9 }, ground: { type: 'teren', elev: 30, mount: 2, low: '#4f7a2e', mid: '#3f6a28', high: '#77705f', peak: '#ffffff', valley: true, lake: 45 }, water: { level: -0.6, color: '#2f6a7f', waves: true }, fog: { color: '#c4d4e2', near: 60, far: 700 },
    elements: [{ kind: 'brazi', count: 900, min: 9, radius: 160 }, { kind: 'pietre', count: 160, min: 5, radius: 100 }] }
};
const ALIAS = { beach: 'plaja', sea: 'ocean', mare: 'ocean', underwater: 'subacvatic', 'sub apa': 'subacvatic', space: 'cosmos', spatiu: 'cosmos', moon: 'luna', mars: 'marte', volcano: 'vulcan', jungle: 'jungla',
  city: 'oras', temple: 'templu', cave: 'pestera', hall: 'sala', office: 'birou', room: 'camera', sky: 'cer', clouds: 'cer', lake: 'lac', arctic: 'arctica', polar: 'arctica', island: 'insula', 'oras noaptea': 'oras_noapte' };

// ---------------------------------------------------------------- texturi procedurale (canvas)
function canvasTex(w, h, draw, repeat) { const cv = document.createElement('canvas'); cv.width = w; cv.height = h; draw(cv.getContext('2d'), w, h); const t = new THREE.CanvasTexture(cv);
  t.colorSpace = THREE.SRGBColorSpace; t.anisotropy = 8; if (repeat) { t.wrapS = t.wrapT = THREE.RepeatWrapping; t.repeat.set(repeat[0], repeat[1]); } return t; }
function floorTex(kind, color, rep) {
  const c = col(color, '#cccccc');
  return canvasTex(512, 512, (g, w, h) => {
    g.fillStyle = '#' + c.getHexString(); g.fillRect(0, 0, w, h);
    if (kind === 'lemn') { for (let i = 0; i < 8; i++) { const y = i * h / 8, k = c.clone().offsetHSL(0, 0, rnd(-0.07, 0.05)); g.fillStyle = '#' + k.getHexString(); g.fillRect(0, y, w, h / 8 - 2);
        g.strokeStyle = 'rgba(0,0,0,0.08)'; for (let j = 0; j < 14; j++) { g.beginPath(); const yy = y + rnd(4, h / 8 - 4); g.moveTo(0, yy); g.bezierCurveTo(w / 3, yy + rnd(-4, 4), 2 * w / 3, yy + rnd(-4, 4), w, yy); g.stroke(); }
        g.fillStyle = 'rgba(0,0,0,0.35)'; g.fillRect(((i * 197) % w), y, 2, h / 8); } }
    else if (kind === 'marmura') { for (let i = 0; i < 2; i++) for (let j = 0; j < 2; j++) { const k = c.clone().offsetHSL(0, 0, (i + j) % 2 ? -0.04 : 0.02); g.fillStyle = '#' + k.getHexString(); g.fillRect(i * w / 2, j * h / 2, w / 2, h / 2); }
      g.strokeStyle = 'rgba(80,80,90,0.16)'; g.lineWidth = 1.5; for (let i = 0; i < 26; i++) { g.beginPath(); let x = rnd(0, w), y = rnd(0, h); g.moveTo(x, y); for (let s = 0; s < 8; s++) { x += rnd(-40, 40); y += rnd(-40, 40); g.lineTo(x, y); } g.stroke(); }
      g.fillStyle = 'rgba(0,0,0,0.25)'; g.fillRect(w / 2 - 1, 0, 2, h); g.fillRect(0, h / 2 - 1, w, 2); g.fillRect(0, 0, 2, h); g.fillRect(0, 0, w, 2); }
    else if (kind === 'asfalt') { const im = g.getImageData(0, 0, w, h); for (let i = 0; i < im.data.length; i += 4) { const n = rnd(-14, 14); im.data[i] += n; im.data[i + 1] += n; im.data[i + 2] += n; } g.putImageData(im, 0, 0); }
    else if (kind === 'dale') { g.fillStyle = 'rgba(0,0,0,0.22)'; for (let i = 0; i <= 4; i++) { g.fillRect(i * w / 4 - 1, 0, 2, h); g.fillRect(0, i * h / 4 - 1, w, 2); } }
  }, rep);
}
// atlas de fatade: 8x8 ferestre = 32 m latime x 24 m inaltime (fereastra la 4 m, etaj la 3 m); noaptea, ferestre aprinse aleator
function facadeTextures() {
  const N = 8, S = 64; const lit = [];
  const map = canvasTex(N * S, N * S, (g) => { g.fillStyle = '#ffffff'; g.fillRect(0, 0, N * S, N * S);
    for (let i = 0; i < N; i++) for (let j = 0; j < N; j++) { const x = i * S, y = j * S; g.fillStyle = 'rgba(0,0,0,0.06)'; g.fillRect(x, y + S - 4, S, 4);
      g.fillStyle = Math.random() < 0.5 ? '#4d5b68' : '#62707d'; g.fillRect(x + 22, y + 14, S - 44, S - 32); g.fillStyle = 'rgba(255,255,255,0.22)'; g.fillRect(x + 22, y + 14, (S - 44) / 2, 5); g.fillStyle = 'rgba(0,0,0,0.12)'; g.fillRect(x + 20, y + S - 19, S - 40, 3);
      lit.push(Math.random() < 0.38); } }, [1 / 32, 1 / 24]);
  const em = canvasTex(N * S, N * S, (g) => { g.fillStyle = '#000'; g.fillRect(0, 0, N * S, N * S); let k = 0;
    for (let i = 0; i < N; i++) for (let j = 0; j < N; j++) { if (lit[k++]) { g.fillStyle = pick(['#ffd28a', '#ffe3b0', '#fff1d6', '#cfe6ff']); g.fillRect(i * S + 22, j * S + 14, S - 44, S - 32); } } }, [1 / 32, 1 / 24]);
  return { map, em };
}
function gradientDome(top, hor, bot, r = 4000) {
  const tex = canvasTex(4, 512, (g, w, h) => { const gr = g.createLinearGradient(0, 0, 0, h); gr.addColorStop(0, top); gr.addColorStop(0.5, hor); gr.addColorStop(1, bot); g.fillStyle = gr; g.fillRect(0, 0, w, h); });
  const m = new THREE.Mesh(new THREE.SphereGeometry(r, 32, 24), new THREE.MeshBasicMaterial({ map: tex, side: THREE.BackSide, fog: false, depthWrite: false }));
  m.renderOrder = -10; return m;
}
function textSprite(text, h) { const cv = document.createElement('canvas'), x = cv.getContext('2d'); const fs = 64; x.font = 'bold ' + fs + 'px system-ui, sans-serif';
  const w = Math.ceil(x.measureText(text).width) + 60; cv.width = w; cv.height = fs + 40; x.font = 'bold ' + fs + 'px system-ui, sans-serif';
  x.fillStyle = 'rgba(8,24,40,0.55)'; x.fillRect(0, 0, w, cv.height); x.strokeStyle = '#46e0ff'; x.lineWidth = 4; x.strokeRect(2, 2, w - 4, cv.height - 4); x.fillStyle = '#e8fbff'; x.textBaseline = 'middle'; x.fillText(text, 30, cv.height / 2);
  const t = new THREE.CanvasTexture(cv); t.colorSpace = THREE.SRGBColorSpace; const sp = new THREE.Sprite(new THREE.SpriteMaterial({ map: t, transparent: true, depthWrite: false, fog: false }));
  sp.scale.set(h * w / cv.height, h, 1); return sp; }
const softDot = (() => { let t; return () => t || (t = canvasTex(128, 128, (g) => { const gr = g.createRadialGradient(64, 64, 4, 64, 64, 64); gr.addColorStop(0, 'rgba(255,255,255,1)'); gr.addColorStop(1, 'rgba(255,255,255,0)'); g.fillStyle = gr; g.fillRect(0, 0, 128, 128); })); })();
function waterNormals() { // harta de normale pentru valuri (se deruleaza in timp)
  const S = 256, p = new ImprovedNoise(); const cv = document.createElement('canvas'); cv.width = cv.height = S; const g = cv.getContext('2d'); const im = g.createImageData(S, S);
  const h = (x, y) => p.noise(x / 22, y / 22, 0.5) + 0.5 * p.noise(x / 9, y / 9, 3.1);
  for (let y = 0; y < S; y++) for (let x = 0; x < S; x++) { const dx = h((x + 1) % S, y) - h((x - 1 + S) % S, y), dy = h(x, (y + 1) % S) - h(x, (y - 1 + S) % S); const n = new THREE.Vector3(-dx * 3, -dy * 3, 1).normalize(); const i = (y * S + x) * 4;
    im.data[i] = (n.x * 0.5 + 0.5) * 255; im.data[i + 1] = (n.y * 0.5 + 0.5) * 255; im.data[i + 2] = (n.z * 0.5 + 0.5) * 255; im.data[i + 3] = 255; }
  g.putImageData(im, 0, 0); const t = new THREE.CanvasTexture(cv); t.wrapS = t.wrapT = THREE.RepeatWrapping; return t; }
function planetTex(kind) {
  return canvasTex(512, 256, (g, w, h) => {
    const P = { pamant: ['#1d4f91', '#2f6fb3'], gaz: ['#c9a16b', '#e0c49a', '#a8784a', '#f0dcc0'], gheata: ['#9fd6e8', '#c7eef7', '#7fb9d0'], rosu: ['#b5562f', '#d07a4a', '#8a3a22'], violet: ['#6a4aa8', '#9a7ad0', '#4a3080'], stanca: ['#8a8a8a', '#6f6f6f', '#a0a0a0'] }[kind] || ['#888', '#aaa'];
    g.fillStyle = P[0]; g.fillRect(0, 0, w, h);
    if (kind === 'pamant') { const p = new ImprovedNoise(); const im = g.getImageData(0, 0, w, h);
      for (let y = 0; y < h; y++) for (let x = 0; x < w; x++) { const n = p.noise(x / 60, y / 40, 1.7) + 0.5 * p.noise(x / 20, y / 14, 4.2); const i = (y * w + x) * 4; const lat = Math.abs(y / h - 0.5) * 2;
        if (lat > 0.86) { im.data[i] = im.data[i + 1] = im.data[i + 2] = 245; } else if (n > 0.12) { const k = n > 0.45 ? [140, 120, 80] : [58, 120, 52]; im.data[i] = k[0]; im.data[i + 1] = k[1]; im.data[i + 2] = k[2]; } }
      g.putImageData(im, 0, 0); g.fillStyle = 'rgba(255,255,255,0.35)'; for (let i = 0; i < 70; i++) { g.beginPath(); g.ellipse(rnd(0, w), rnd(0, h), rnd(10, 50), rnd(3, 10), 0, 0, 7); g.fill(); } }
    else for (let y = 0; y < h; y += 2) { g.fillStyle = P[Math.floor((Math.sin(y * 0.09) * 0.5 + 0.5 + Math.sin(y * 0.31) * 0.2) * (P.length - 0.01)) % P.length]; g.globalAlpha = 0.55; g.fillRect(0, y, w, 2); g.globalAlpha = 1; }
  });
}

// ---------------------------------------------------------------- pozitia reala a soarelui (aprox. NOAA)
function sunDirection(lat, lon, date) {
  const d = date.getTime() / 86400000 - 10957.5; const g = (357.529 + 0.98560028 * d) * D2R, q = 280.459 + 0.98564736 * d;
  const L = (q + 1.915 * Math.sin(g) + 0.020 * Math.sin(2 * g)) * D2R, e = (23.439 - 0.00000036 * d) * D2R;
  const ra = Math.atan2(Math.cos(e) * Math.sin(L), Math.cos(L)), dec = Math.asin(Math.sin(e) * Math.sin(L));
  const gmst = ((18.697374558 + 24.06570982441908 * d) % 24 + 24) % 24; const H = (gmst * 15 + lon) * D2R - ra; const la = lat * D2R;
  const alt = Math.asin(Math.sin(la) * Math.sin(dec) + Math.cos(la) * Math.cos(dec) * Math.cos(H));
  const az = Math.atan2(-Math.sin(H), Math.tan(dec) * Math.cos(la) - Math.sin(la) * Math.cos(H));
  return { alt, az };
}
function dirFromAltAz(alt, az) { return new THREE.Vector3(Math.sin(az) * Math.cos(alt), Math.sin(alt), -Math.cos(az) * Math.cos(alt)); } // x=est, z=-nord
function dateAtHour(hour, lon) { const n = new Date(); const utcH = hour - lon / 15; return new Date(Date.UTC(n.getUTCFullYear(), n.getUTCMonth(), n.getUTCDate(), 0, 0, 0) + utcH * 3600000); }

// ---------------------------------------------------------------- cer + lumini comune
function addSkyAndLight(ctx, sk, sunAltAz, fogCfg, opts = {}) {
  const { root, scene, renderer } = ctx; const type = sk.type || 'fizic'; let dir, night = false;
  if (type === 'fizic') {
    dir = dirFromAltAz(sunAltAz.alt, sunAltAz.az); night = sunAltAz.alt < -4 * D2R;
    const sky = new Sky(); sky.scale.setScalar(opts.skyScale || 4500); const U = sky.material.uniforms;
    U.turbidity.value = num(sk.turbidity, 3); U.rayleigh.value = night ? 0.25 : num(sk.rayleigh, sunAltAz.alt < 8 * D2R ? 2.8 : 1.4); U.mieCoefficient.value = 0.005; U.mieDirectionalG.value = 0.8;
    U.sunPosition.value.copy(dir); root.add(sky);
    if (night) addStars(ctx, 3000);
  } else if (type === 'gradient') { root.add(gradientDome(sk.top || '#4a7ab0', sk.horizon || '#b8d0e6', sk.bottom || '#3a3a3a', opts.skyScale || 4000)); dir = dirFromAltAz(num(opts.sunAlt, 40) * D2R, num(opts.sunAz, 160) * D2R); }
  else { dir = dirFromAltAz(num(opts.sunAlt, 30) * D2R, num(opts.sunAz, 140) * D2R); }
  if (opts.background) { ctx.prevBg = scene.background; scene.background = col(opts.background, '#000'); ctx.bgSet = true; }
  const sl = opts.sunLight || {}; const sunUp = !night && (type !== 'fizic' || sunAltAz.alt > -1 * D2R);
  const sun = new THREE.DirectionalLight(col(sl.color, sunAltAz && sunAltAz.alt < 10 * D2R && type === 'fizic' ? '#ffb27a' : '#fff3e0'), sunUp ? num(sl.intensity, 2.6) : 0.12);
  if (sl.alt !== undefined) dir = dirFromAltAz(num(sl.alt, 30) * D2R, num(sl.az, 140) * D2R);
  sun.position.copy(dir.clone().normalize()).multiplyScalar(40); if (sun.position.y < 2) sun.position.y = 2; sun.target.position.set(0, 0, -2);
  sun.castShadow = sunUp; sun.shadow.mapSize.set(2048, 2048); const sc = sun.shadow.camera; sc.left = -18; sc.right = 18; sc.top = 18; sc.bottom = -18; sc.near = 1; sc.far = 120; sun.shadow.bias = -0.0005; sun.shadow.normalBias = 0.02;
  root.add(sun, sun.target);
  const hemi = new THREE.HemisphereLight(night ? 0x2a3a66 : col(opts.hemiSky, '#cfe3ff'), night ? 0x0a0a10 : col(opts.hemiGround, '#4a4030'), night ? 0.45 : num(opts.hemi, 0.85)); root.add(hemi);
  if (night) { const moon = new THREE.DirectionalLight(0x9fb6ff, 0.5); moon.position.set(-20, 40, 20); root.add(moon); }
  if (fogCfg) { ctx.prevFog = scene.fog; ctx.fogSet = true; const fc = col(fogCfg.color, night ? '#0b1020' : '#c8d8e6'); if (night && type === 'fizic') fc.set('#0b1020');
    scene.fog = fogCfg.density ? new THREE.FogExp2(fc, num(fogCfg.density, 0.02)) : new THREE.Fog(fc, num(fogCfg.near, 40), num(fogCfg.far, 500)); }
  renderer.shadowMap.enabled = true; renderer.shadowMap.type = THREE.PCFSoftShadowMap;
  return { night, dir };
}
function addStars(ctx, n) { const sp = []; for (let i = 0; i < n; i++) { const v = new THREE.Vector3().randomDirection(); if (v.y < -0.05 && !ctx.allSky) continue; sp.push(v.x * 3000, v.y * 3000, v.z * 3000); }
  const g = new THREE.BufferGeometry(); g.setAttribute('position', new THREE.Float32BufferAttribute(sp, 3));
  ctx.root.add(new THREE.Points(g, new THREE.PointsMaterial({ color: 0xffffff, size: 1.6, sizeAttenuation: false, fog: false }))); }

// ---------------------------------------------------------------- plasare elemente (evita locul lui Kelion si drumul catre camera)
function freeSpot(x, z, minD) { if (Math.hypot(x, z) < minD) return false; if (Math.abs(x) < 3.2 && z > -1.5 && z < 9) return false; return true; }
function scatter(ctx, n, minD, maxD, fn, opt = {}) {
  let k = 0, tries = 0; const hAt = ctx.heightAt;
  while (k < n && tries++ < n * 12) {
    const a = Math.random() * Math.PI * 2, r = Math.sqrt(rnd((minD / maxD) ** 2, 1)) * maxD; const x = Math.cos(a) * r, z = Math.sin(a) * r;
    if (!freeSpot(x, z, minD)) continue; const y = hAt(x, z); if (y < -500) continue;
    if (!opt.underwaterOk && ctx.waterLevel !== null && y < ctx.waterLevel + 0.15) continue; if (opt.maxY !== undefined && y > opt.maxY) continue;
    fn(x, y, z, k++);
  }
  return k;
}
const M4 = new THREE.Matrix4(), Q = new THREE.Quaternion(), S3 = new THREE.Vector3(), V3 = new THREE.Vector3(), E = new THREE.Euler();
function inst(geo, mat, n) { const m = new THREE.InstancedMesh(geo, mat, Math.max(1, n)); m.castShadow = true; m.receiveShadow = true; return m; }

// ---------------------------------------------------------------- ELEMENTE
const ELEM = {
  brazi(ctx, e) { const n = clamp(num(e.count, 300), 1, 3000), s = num(e.size, 1), c = col(e.color, '#2f5a24');
    const tg = new THREE.CylinderGeometry(0.12, 0.18, 1, 6); tg.translate(0, 0.5, 0); const cg = new THREE.ConeGeometry(1, 1, 8); cg.translate(0, 0.5, 0);
    const tr = inst(tg, new THREE.MeshStandardMaterial({ color: 0x5a3d26, roughness: 1 }), n), cn = inst(cg, new THREE.MeshStandardMaterial({ color: c, roughness: 0.9, flatShading: true }), n * 2); let np = 0;
    tr.count = scatter(ctx, n, num(e.min, 8), num(e.radius, 150), (x, y, z, i) => { const h = rnd(4, 9) * s, r = rnd(1.1, 1.8) * s; M4.compose(V3.set(x, y, z), Q.identity(), S3.set(s, h * 0.35, s)); tr.setMatrixAt(i, M4);
      M4.compose(V3.set(x, y + h * 0.22, z), Q, S3.set(r, h * 0.55, r)); cn.setMatrixAt(np++, M4); M4.compose(V3.set(x, y + h * 0.52, z), Q, S3.set(r * 0.7, h * 0.45, r * 0.7)); cn.setMatrixAt(np++, M4); });
    cn.count = np; ctx.root.add(tr, cn); return tr.count; },
  chiparosi(ctx, e) { const n = clamp(num(e.count, 60), 1, 800), s = num(e.size, 1); const g = new THREE.CapsuleGeometry(0.7, 5, 4, 8); g.translate(0, 3.2, 0);
    const m = inst(g, new THREE.MeshStandardMaterial({ color: col(e.color, '#2c4a26'), roughness: 0.95, flatShading: true }), n);
    m.count = scatter(ctx, n, num(e.min, 12), num(e.radius, 120), (x, y, z, i) => { const k = rnd(0.7, 1.3) * s; M4.compose(V3.set(x, y, z), Q.identity(), S3.set(k, k * rnd(0.9, 1.4), k)); m.setMatrixAt(i, M4); }); ctx.root.add(m); return m.count; },
  copaci(ctx, e) { const n = clamp(num(e.count, 300), 1, 3000), s = num(e.size, 1), c = col(e.color, '#3f6f2c');
    const tg = new THREE.CylinderGeometry(0.15, 0.25, 1, 6); tg.translate(0, 0.5, 0); const lg = new THREE.IcosahedronGeometry(1, 1);
    const tr = inst(tg, new THREE.MeshStandardMaterial({ color: 0x5a3d26, roughness: 1 }), n), lf = inst(lg, new THREE.MeshStandardMaterial({ color: 0xffffff, roughness: 0.9, flatShading: true }), n * 2); let nl = 0; const cc = new THREE.Color();
    tr.count = scatter(ctx, n, num(e.min, 8), num(e.radius, 150), (x, y, z, i) => { const h = rnd(3, 6) * s, r = rnd(1.4, 2.6) * s; M4.compose(V3.set(x, y, z), Q.identity(), S3.set(s, h, s)); tr.setMatrixAt(i, M4);
      for (let j = 0; j < 2; j++) { M4.compose(V3.set(x + rnd(-0.6, 0.6) * s, y + h + r * (0.2 + j * 0.5), z + rnd(-0.6, 0.6) * s), Q.setFromEuler(E.set(0, rnd(0, 6), 0)), S3.set(r * (1 - j * 0.25), r * 0.85 * (1 - j * 0.25), r * (1 - j * 0.25))); lf.setMatrixAt(nl, M4); lf.setColorAt(nl++, cc.copy(c).offsetHSL(rnd(-0.03, 0.03), 0, rnd(-0.06, 0.06))); } });
    lf.count = nl; ctx.root.add(tr, lf); return tr.count; },
  acacii(ctx, e) { const n = clamp(num(e.count, 80), 1, 800), s = num(e.size, 1); const tg = new THREE.CylinderGeometry(0.14, 0.22, 1, 6); tg.translate(0, 0.5, 0); const cg = new THREE.CylinderGeometry(1, 0.6, 0.5, 9);
    const tr = inst(tg, new THREE.MeshStandardMaterial({ color: 0x5a4632, roughness: 1 }), n), cp = inst(cg, new THREE.MeshStandardMaterial({ color: col(e.color, '#5e7a2e'), roughness: 0.9, flatShading: true }), n);
    tr.count = cp.count = scatter(ctx, n, num(e.min, 10), num(e.radius, 150), (x, y, z, i) => { const h = rnd(3.5, 6) * s, r = rnd(2.5, 4.5) * s; M4.compose(V3.set(x, y, z), Q.setFromEuler(E.set(rnd(-0.12, 0.12), 0, rnd(-0.12, 0.12))), S3.set(s, h, s)); tr.setMatrixAt(i, M4);
      M4.compose(V3.set(x, y + h + 0.2, z), Q.identity(), S3.set(r, s, r * rnd(0.7, 1))); cp.setMatrixAt(i, M4); }); ctx.root.add(tr, cp); return tr.count; },
  palmieri(ctx, e) { const n = clamp(num(e.count, 60), 1, 800), s = num(e.size, 1);
    const curve = new THREE.CatmullRomCurve3([new THREE.Vector3(0, 0, 0), new THREE.Vector3(0.15, 2.4, 0), new THREE.Vector3(0.55, 4.8, 0), new THREE.Vector3(1.2, 7, 0)]); const trunkG = new THREE.TubeGeometry(curve, 14, 0.17, 7, false); const top = curve.getPoint(1);
    const fr = []; for (let i = 0; i < 9; i++) { const g = new THREE.ConeGeometry(0.32, 3.4, 4); g.scale(1, 1, 0.14); g.translate(0, 1.7, 0); g.rotateZ(-1.15 - rnd(0, 0.45)); g.rotateY(i / 9 * Math.PI * 2 + rnd(-0.15, 0.15)); g.translate(top.x, top.y, top.z); fr.push(g); } const frondG = mergeGeometries(fr);
    const tr = inst(trunkG, new THREE.MeshStandardMaterial({ color: 0x8a6a48, roughness: 1, flatShading: true }), n), fd = inst(frondG, new THREE.MeshStandardMaterial({ color: col(e.color, '#3f7a2a'), roughness: 0.85, flatShading: true, side: THREE.DoubleSide }), n);
    tr.count = fd.count = scatter(ctx, n, num(e.min, 7), num(e.radius, 80), (x, y, z, i) => { const k = rnd(0.7, 1.2) * s; M4.compose(V3.set(x, y, z), Q.setFromEuler(E.set(0, rnd(0, 6.28), 0)), S3.set(k, k, k)); tr.setMatrixAt(i, M4); fd.setMatrixAt(i, M4); }); ctx.root.add(tr, fd); return tr.count; },
  ferigi(ctx, e) { const n = clamp(num(e.count, 600), 1, 5000); const fr = []; for (let i = 0; i < 7; i++) { const g = new THREE.ConeGeometry(0.11, 1.1, 3); g.scale(1, 1, 0.2); g.translate(0, 0.55, 0); g.rotateZ(-0.9 - rnd(0, 0.4)); g.rotateY(i / 7 * Math.PI * 2); fr.push(g); }
    const m = inst(mergeGeometries(fr), new THREE.MeshStandardMaterial({ color: col(e.color, '#3c7a2a'), roughness: 0.9, side: THREE.DoubleSide, flatShading: true }), n); m.castShadow = false;
    m.count = scatter(ctx, n, num(e.min, 2.5), num(e.radius, 25), (x, y, z, i) => { const k = rnd(0.5, 1.3); M4.compose(V3.set(x, y, z), Q.setFromEuler(E.set(0, rnd(0, 6), 0)), S3.set(k, k, k)); m.setMatrixAt(i, M4); }); ctx.root.add(m); return m.count; },
  iarba(ctx, e) { const n = clamp(num(e.count, 6000), 1, 20000); const g = new THREE.ConeGeometry(0.025, 0.3, 3); g.translate(0, 0.15, 0);
    const m = inst(g, new THREE.MeshStandardMaterial({ color: col(e.color, '#5e8a34'), roughness: 1 }), n); m.castShadow = false;
    m.count = scatter(ctx, n, 0.4, num(e.radius, 16), (x, y, z, i) => { const k = rnd(0.6, 1.5); M4.compose(V3.set(x, y, z), Q.setFromEuler(E.set(rnd(-0.3, 0.3), rnd(0, 6), rnd(-0.3, 0.3))), S3.set(k, k, k)); m.setMatrixAt(i, M4); }); ctx.root.add(m); return m.count; },
  flori(ctx, e) { const n = clamp(num(e.count, 300), 1, 4000); const g = new THREE.IcosahedronGeometry(0.07, 0); g.translate(0, 0.32, 0); const st = new THREE.CylinderGeometry(0.008, 0.008, 0.32, 3); st.translate(0, 0.16, 0);
    const m = inst(g, new THREE.MeshStandardMaterial({ color: 0xffffff, roughness: 0.6 }), n), s = inst(st, new THREE.MeshStandardMaterial({ color: 0x3f7a2a }), n); const cc = new THREE.Color(); const pal = (e.colors || ['#ff5a7a', '#ffd24a', '#ffffff', '#b06aff', '#ff8a3a']);
    m.count = s.count = scatter(ctx, n, 1.2, num(e.radius, 14), (x, y, z, i) => { M4.compose(V3.set(x, y, z), Q.identity(), S3.set(1, rnd(0.7, 1.3), 1)); m.setMatrixAt(i, M4); s.setMatrixAt(i, M4); m.setColorAt(i, cc.set(e.color || pick(pal))); }); ctx.root.add(m, s); return m.count; },
  cactusi(ctx, e) { const n = clamp(num(e.count, 120), 1, 1500); const g = new THREE.CapsuleGeometry(0.25, 2, 4, 8); g.translate(0, 1.2, 0); const arm = new THREE.CapsuleGeometry(0.16, 0.8, 4, 6); arm.translate(0.42, 1.5, 0); const ar2 = arm.clone(); ar2.rotateY(Math.PI); ar2.translate(0, -0.3, 0);
    const m = inst(mergeGeometries([g, arm, ar2]), new THREE.MeshStandardMaterial({ color: col(e.color, '#4f7a3a'), roughness: 0.8 }), n);
    m.count = scatter(ctx, n, num(e.min, 7), num(e.radius, 120), (x, y, z, i) => { const k = rnd(0.7, 1.6); M4.compose(V3.set(x, y, z), Q.setFromEuler(E.set(0, rnd(0, 6), 0)), S3.set(k, k, k)); m.setMatrixAt(i, M4); }); ctx.root.add(m); return m.count; },
  pietre(ctx, e) { const n = clamp(num(e.count, 200), 1, 4000), s = num(e.size, 1); const m = inst(new THREE.DodecahedronGeometry(1, 0), new THREE.MeshStandardMaterial({ color: col(e.color, '#77705f'), roughness: 1, flatShading: true }), n);
    m.count = scatter(ctx, n, num(e.min, 5), num(e.radius, 100), (x, y, z, i) => { const r = rnd(0.2, 1.4) * s; M4.compose(V3.set(x, y + r * 0.25, z), Q.setFromEuler(E.set(rnd(0, 3), rnd(0, 3), rnd(0, 3))), S3.set(r, r * rnd(0.5, 1), r * rnd(0.7, 1.2))); m.setMatrixAt(i, M4); }, { underwaterOk: true }); ctx.root.add(m); return m.count; },
  stalagmite(ctx, e) { const n = clamp(num(e.count, 150), 1, 1500); const g = new THREE.ConeGeometry(0.4, 1, 7); g.translate(0, 0.5, 0); const m = inst(g, new THREE.MeshStandardMaterial({ color: col(e.color, '#5a4c40'), roughness: 0.9, flatShading: true }), n * 2); let k = 0;
    scatter(ctx, n, num(e.min, 3), num(e.radius, 24), (x, y, z) => { const h = rnd(0.6, 3.5); M4.compose(V3.set(x, y, z), Q.identity(), S3.set(rnd(0.6, 1.4), h, rnd(0.6, 1.4))); m.setMatrixAt(k++, M4);
      if (ctx.ceilingAt) { const c = ctx.ceilingAt(x, z), h2 = rnd(0.8, 3); M4.compose(V3.set(x + rnd(-1, 1), c, z + rnd(-1, 1)), Q.setFromEuler(E.set(Math.PI, 0, 0)), S3.set(rnd(0.5, 1.1), h2, rnd(0.5, 1.1))); m.setMatrixAt(k++, M4); } }, { underwaterOk: true });
    m.count = k; ctx.root.add(m); return k; },
  cristale(ctx, e) { const n = clamp(num(e.count, 150), 1, 2000); const g = new THREE.OctahedronGeometry(0.4, 0); g.scale(0.5, 1.6, 0.5); g.translate(0, 0.5, 0);
    const m = inst(g, new THREE.MeshStandardMaterial({ color: 0xffffff, emissive: 0xffffff, emissiveIntensity: 0.55, roughness: 0.15, metalness: 0.2, transparent: true, opacity: 0.85 }), n); const cc = new THREE.Color(); const pal = e.colors || ['#66e0ff', '#b07aff', '#7affc8', '#ff7ad8'];
    m.count = scatter(ctx, n, num(e.min, 3), num(e.radius, 22), (x, y, z, i) => { const k = rnd(0.4, 2.2); M4.compose(V3.set(x, y, z), Q.setFromEuler(E.set(rnd(-0.4, 0.4), rnd(0, 6), rnd(-0.4, 0.4))), S3.set(k, k, k)); m.setMatrixAt(i, M4); m.setColorAt(i, cc.set(e.color || pick(pal))); }, { underwaterOk: true });
    ctx.root.add(m); for (let i = 0; i < 4; i++) { const L = new THREE.PointLight(col(e.color || pick(pal), '#66e0ff'), 6, 16, 1.6); L.position.set(rnd(-8, 8), 1.2, -rnd(2, 14)); ctx.root.add(L); } return m.count; },
  gheata(ctx, e) { const n = clamp(num(e.count, 100), 1, 1500); const m = inst(new THREE.IcosahedronGeometry(1, 0), new THREE.MeshStandardMaterial({ color: col(e.color, '#cdeaf7'), roughness: 0.1, metalness: 0.05, transparent: true, opacity: 0.88, flatShading: true }), n);
    m.count = scatter(ctx, n, num(e.min, 8), num(e.radius, 140), (x, y, z, i) => { const r = rnd(1, 5); M4.compose(V3.set(x, y + r * 0.3, z), Q.setFromEuler(E.set(rnd(0, 3), rnd(0, 3), rnd(0, 3))), S3.set(r, r * rnd(0.6, 1.6), r)); m.setMatrixAt(i, M4); }, { underwaterOk: true }); ctx.root.add(m); return m.count; },
  coloane(ctx, e) { // colonada in jurul lui Kelion (sau pe doua randuri spre spate), cu soclu, capitel si arhitrava
    const n = clamp(num(e.count, 12), 2, 60), R = num(e.radius, 10), H = num(e.height, 8), c = col(e.color, '#ece3cf'); const mat = new THREE.MeshStandardMaterial({ color: c, roughness: 0.55 });
    const shaft = new THREE.CylinderGeometry(0.45, 0.55, H, 20); shaft.translate(0, H / 2 + 0.3, 0); const base = new THREE.BoxGeometry(1.4, 0.3, 1.4); base.translate(0, 0.15, 0); const cap = new THREE.BoxGeometry(1.4, 0.35, 1.4); cap.translate(0, H + 0.45, 0);
    const m = inst(mergeGeometries([shaft, base, cap]), mat, n); const pts = [];
    for (let i = 0; i < n; i++) { const a = Math.PI * (0.15 + 0.7 * i / (n - 1)); pts.push([Math.cos(a) * R * 1.1, -Math.sin(a) * R]); } // semicerc in spate
    pts.forEach(([x, z], i) => { M4.compose(V3.set(x, ctx.heightAt(x, z), z), Q.identity(), S3.set(1, 1, 1)); m.setMatrixAt(i, M4); }); m.count = n; ctx.root.add(m);
    for (let i = 0; i < n - 1; i++) { const [x1, z1] = pts[i], [x2, z2] = pts[i + 1]; const L = Math.hypot(x2 - x1, z2 - z1); const b = new THREE.Mesh(new THREE.BoxGeometry(L + 1.2, 0.8, 1.3), mat); b.position.set((x1 + x2) / 2, H + 1.0, (z1 + z2) / 2); b.rotation.y = -Math.atan2(z2 - z1, x2 - x1); b.castShadow = b.receiveShadow = true; ctx.root.add(b); }
    return n; },
  ruine(ctx, e) { const n = clamp(num(e.count, 40), 1, 600), c = col(e.color, '#d8cdb6'); const g1 = new THREE.CylinderGeometry(0.45, 0.5, 1, 14); g1.translate(0, 0.5, 0); const g2 = new THREE.BoxGeometry(1, 1, 1); g2.translate(0, 0.5, 0);
    const a = inst(g1, new THREE.MeshStandardMaterial({ color: c, roughness: 0.7 }), n), b = inst(g2, new THREE.MeshStandardMaterial({ color: c.clone().offsetHSL(0, 0, -0.05), roughness: 0.8 }), n); let na = 0, nb = 0;
    scatter(ctx, n, num(e.min, 12), num(e.radius, 60), (x, y, z) => { if (Math.random() < 0.55) { M4.compose(V3.set(x, y, z), Q.setFromEuler(E.set(Math.random() < 0.3 ? Math.PI / 2 : 0, rnd(0, 6), 0)), S3.set(1, rnd(0.8, 6), 1)); a.setMatrixAt(na++, M4); } else { M4.compose(V3.set(x, y - 0.1, z), Q.setFromEuler(E.set(rnd(-0.2, 0.2), rnd(0, 6), rnd(-0.2, 0.2))), S3.set(rnd(0.8, 3), rnd(0.4, 1.2), rnd(0.6, 1.5))); b.setMatrixAt(nb++, M4); } });
    a.count = na; b.count = nb; ctx.root.add(a, b); return na + nb; },
  cladiri(ctx, e) { // oras procedural: blocuri pe grila de strazi, inaltimi variate, ferestre reale (noaptea aprinse)
    const n = clamp(num(e.count, 200), 1, 1500), R = num(e.radius, 250), minD = num(e.min, 14); const blk = num(e.block, 34), road = num(e.road, 14); const boxes = [];
    for (let gx = -Math.ceil(R / blk); gx <= Math.ceil(R / blk); gx++) for (let gz = -Math.ceil(R / blk); gz <= 1; gz++) {
      const cx = gx * blk + Math.sign(gx) * 6, cz = gz * blk - blk / 2 - road / 2 - 4; const d = Math.hypot(cx, cz); if (d > R || d < minD) continue; if (gx === 0) continue; // bulevardul din spatele lui Kelion ramane liber
      const parts = Math.random() < 0.5 ? 1 : 2; for (let p = 0; p < parts; p++) { const w = (blk - road) / parts - 1, dd = blk - road - 2; const hgt = clamp(rnd(8, 40) * (1 + 2.2 * Math.exp(-d / 120)) * (Math.random() < 0.08 ? 2.5 : 1), 6, 180) * num(e.size, 1);
        boxes.push({ x: cx - (blk - road) / 2 + w / 2 + p * (w + 1) + 0.5, z: cz, w, d: dd, h: hgt }); } }
    boxes.sort((a, b) => Math.hypot(a.x, a.z) - Math.hypot(b.x, b.z)); const use = boxes.slice(0, n); const walls = newBuf(), roofs = newBuf();
    for (const b of use) { const y0 = ctx.heightAt(b.x, b.z) - 0.3; const ring = [[b.x - b.w / 2, b.z - b.d / 2], [b.x + b.w / 2, b.z - b.d / 2], [b.x + b.w / 2, b.z + b.d / 2], [b.x - b.w / 2, b.z + b.d / 2]];
      pushBuilding(walls, roofs, [ring], y0, y0 + b.h + 0.3, colBuilding()); }
    addBuildingMeshes(ctx, walls, roofs); return use.length; },
  felinare(ctx, e) { const n = clamp(num(e.count, 20), 1, 120); const pole = new THREE.CylinderGeometry(0.06, 0.09, 4.2, 8); pole.translate(0, 2.1, 0); const lamp = new THREE.SphereGeometry(0.22, 12, 8); lamp.translate(0, 4.3, 0);
    const p = inst(pole, new THREE.MeshStandardMaterial({ color: 0x2b2e33, metalness: 0.6, roughness: 0.4 }), n), l = inst(lamp, new THREE.MeshStandardMaterial({ color: 0xfff1d0, emissive: 0xffd89a, emissiveIntensity: ctx.night ? 3 : 0.4 }), n); const spots = [];
    p.count = l.count = scatter(ctx, n, 4, num(e.radius, 40), (x, y, z, i) => { M4.compose(V3.set(x, y, z), Q.identity(), S3.set(1, 1, 1)); p.setMatrixAt(i, M4); l.setMatrixAt(i, M4); spots.push([x, y, z]); });
    if (ctx.night) spots.sort((a, b) => Math.hypot(a[0], a[2]) - Math.hypot(b[0], b[2])).slice(0, 6).forEach(([x, y, z]) => { const L = new THREE.PointLight(0xffd08a, 30, 22, 1.8); L.position.set(x, y + 4.1, z); ctx.root.add(L); });
    ctx.root.add(p, l); return p.count; },
  nori(ctx, e) { const n = clamp(num(e.count, 40), 1, 300); const tex = softDot(); const g = new THREE.Group();
    for (let i = 0; i < n; i++) { const sp = new THREE.Sprite(new THREE.SpriteMaterial({ map: tex, color: col(e.color, ctx.night ? '#2a3040' : '#ffffff'), transparent: true, opacity: 0.8, depthWrite: false, fog: false }));
      const a = rnd(Math.PI * 0.1, Math.PI * 0.9), r = rnd(150, 900); sp.position.set(Math.cos(a) * r * 1.6, num(e.height, 60) + rnd(0, 80), -Math.sin(a) * r); sp.scale.set(rnd(80, 220), rnd(30, 70), 1); sp.userData.drift = rnd(0.5, 2); g.add(sp); }
    ctx.root.add(g); ctx.anim.push(dt => { for (const s of g.children) { s.position.x += s.userData.drift * dt; if (s.position.x > 1500) s.position.x = -1500; } }); return n; },
  mare_de_nori(ctx) { const tex = softDot(); const g = new THREE.Group();
    for (let i = 0; i < 700; i++) { const sp = new THREE.Sprite(new THREE.SpriteMaterial({ map: tex, color: 0xffffff, transparent: true, opacity: 0.9, depthWrite: false })); const a = Math.random() * 6.283, r = Math.sqrt(Math.random()) * 900 + 6;
      if (r < 25) continue; sp.position.set(Math.cos(a) * r, -rnd(10, 26) - r * 0.02, Math.sin(a) * r); sp.scale.setScalar(rnd(18, 45) * (1 + r / 300)); g.add(sp); } ctx.root.add(g); return g.children.length; },
  stele(ctx, e) { ctx.allSky = true; addStars(ctx, clamp(num(e.count, 6000), 100, 20000)); return num(e.count, 6000); },
  nebuloasa(ctx, e) { const n = clamp(num(e.count, 12), 1, 60); const tex = softDot(); const pal = e.colors || ['#7a3aff', '#ff3a9a', '#3ab0ff', '#3affc8', '#ff8a3a'];
    for (let i = 0; i < n; i++) { const sp = new THREE.Sprite(new THREE.SpriteMaterial({ map: tex, color: col(e.color || pick(pal), '#7a3aff'), transparent: true, opacity: 0.22, depthWrite: false, blending: THREE.AdditiveBlending, fog: false }));
      const v = new THREE.Vector3(rnd(-1, 1), rnd(-0.2, 0.7), -rnd(0.4, 1)).normalize().multiplyScalar(2500); sp.position.copy(v); sp.scale.setScalar(rnd(600, 1500)); ctx.root.add(sp); } return n; },
  planete(ctx, e) { const n = clamp(num(e.count, 3), 1, 12); const kinds = e.preset ? [e.preset] : (e.kinds || ['gaz', 'gheata', 'rosu', 'violet', 'stanca', 'pamant']); const g = new THREE.Group();
    for (let i = 0; i < n; i++) { const kind = kinds[i % kinds.length]; const size = num(e.size, i === 0 ? 160 : rnd(25, 70)), dist = num(e.distance, i === 0 ? 900 : rnd(500, 1500));
      const alt = num(e.alt, i === 0 ? 14 : rnd(5, 45)) * D2R, az = num(e.az, i === 0 ? rnd(-30, 30) : rnd(-80, 80)) * D2R; const p = new THREE.Mesh(new THREE.SphereGeometry(size, 64, 32), new THREE.MeshStandardMaterial({ map: planetTex(kind), roughness: 0.9, fog: false }));
      p.position.copy(dirFromAltAz(alt, az).multiplyScalar(dist)); p.rotation.z = rnd(-0.4, 0.4); p.userData.spin = rnd(0.01, 0.04); g.add(p);
      if (kind === 'gaz' || e.rings) { const ring = new THREE.Mesh(new THREE.RingGeometry(size * 1.35, size * 2.2, 96), new THREE.MeshBasicMaterial({ color: 0xd8c49a, transparent: true, opacity: 0.45, side: THREE.DoubleSide, fog: false })); ring.rotation.x = Math.PI / 2 - 0.35; p.add(ring); }
      if (kind === 'pamant') { const atm = new THREE.Mesh(new THREE.SphereGeometry(size * 1.04, 48, 24), new THREE.MeshBasicMaterial({ color: 0x6ab0ff, transparent: true, opacity: 0.18, side: THREE.BackSide, fog: false })); p.add(atm); } }
    const sunG = new THREE.Sprite(new THREE.SpriteMaterial({ map: softDot(), color: 0xfff2c8, transparent: true, depthWrite: false, blending: THREE.AdditiveBlending, fog: false })); sunG.position.copy(dirFromAltAz(30 * D2R, 140 * D2R).multiplyScalar(2600)); sunG.scale.setScalar(420); g.add(sunG);
    ctx.root.add(g); ctx.anim.push(dt => { for (const p of g.children) if (p.userData.spin) p.rotation.y += p.userData.spin * dt; }); return n; },
  asteroizi(ctx, e) { const n = clamp(num(e.count, 200), 1, 3000); const m = inst(new THREE.DodecahedronGeometry(1, 1), new THREE.MeshStandardMaterial({ color: col(e.color, '#6f6a64'), roughness: 1, flatShading: true }), n); const R = num(e.radius, 160), r0 = num(e.min, 70); const sp = [];
    for (let i = 0; i < n; i++) { const a = Math.random() * 6.283, r = rnd(r0, R); const x = Math.cos(a) * r, z = -Math.abs(Math.sin(a) * r) - 25, y = rnd(-25, 45); const s = rnd(0.3, 2.6); sp.push({ x, y, z, s, rx: rnd(0, 3), ry: rnd(0, 3), w: rnd(-0.3, 0.3) }); }
    const upd = () => sp.forEach((o, i) => { M4.compose(V3.set(o.x, o.y, o.z), Q.setFromEuler(E.set(o.rx, o.ry, 0)), S3.set(o.s, o.s * 0.8, o.s * 1.1)); m.setMatrixAt(i, M4); }); upd(); m.count = n; ctx.root.add(m);
    ctx.anim.push(dt => { for (const o of sp) { o.rx += o.w * dt; o.ry += o.w * dt * 0.7; } upd(); m.instanceMatrix.needsUpdate = true; }); return n; },
  corali(ctx, e) { const n = clamp(num(e.count, 200), 1, 3000); const g1 = new THREE.IcosahedronGeometry(0.5, 1); g1.translate(0, 0.3, 0); const g2 = new THREE.ConeGeometry(0.12, 1.2, 6); g2.translate(0, 0.6, 0); const a = g2.clone(); a.rotateZ(0.5); const b = g2.clone(); b.rotateZ(-0.5); const g3 = mergeGeometries([g2, a, b]);
    const m1 = inst(g1, new THREE.MeshStandardMaterial({ color: 0xffffff, roughness: 0.8, flatShading: true }), n), m2 = inst(g3, new THREE.MeshStandardMaterial({ color: 0xffffff, roughness: 0.7 }), n); const cc = new THREE.Color(); const pal = e.colors || ['#ff6f61', '#ffb347', '#ff7ad8', '#b07aff', '#7affc8', '#ffe066']; let k1 = 0, k2 = 0;
    scatter(ctx, n, num(e.min, 3), num(e.radius, 45), (x, y, z) => { const s = rnd(0.5, 2); M4.compose(V3.set(x, y, z), Q.setFromEuler(E.set(0, rnd(0, 6), 0)), S3.set(s, s * rnd(0.6, 1.4), s));
      if (Math.random() < 0.5) { m1.setMatrixAt(k1, M4); m1.setColorAt(k1++, cc.set(pick(pal))); } else { m2.setMatrixAt(k2, M4); m2.setColorAt(k2++, cc.set(pick(pal))); } }, { underwaterOk: true });
    m1.count = k1; m2.count = k2; ctx.root.add(m1, m2); return k1 + k2; },
  alge(ctx, e) { const n = clamp(num(e.count, 200), 1, 2000); const g = new THREE.CylinderGeometry(0.02, 0.09, 1, 5, 6); g.scale(2.2, 1, 0.5); g.translate(0, 0.5, 0); { const a = g.attributes.position; for (let i = 0; i < a.count; i++) a.setX(i, a.getX(i) + Math.sin(a.getY(i) * 5) * 0.06); g.computeVertexNormals(); }
    const m = inst(g, new THREE.MeshStandardMaterial({ color: col(e.color, '#3f8a3a'), roughness: 0.8, side: THREE.DoubleSide }), n); const it = [];
    m.count = scatter(ctx, n, num(e.min, 3), num(e.radius, 50), (x, y, z, i) => { it.push({ x, y, z, h: rnd(2, 7), r: rnd(0, 6), p: rnd(0, 6) }); }, { underwaterOk: true }); ctx.root.add(m); let t = 0;
    ctx.anim.push(dt => { t += dt; it.forEach((o, i) => { M4.compose(V3.set(o.x, o.y, o.z), Q.setFromEuler(E.set(Math.sin(t * 0.8 + o.p) * 0.12, o.r, Math.cos(t * 0.6 + o.p) * 0.1)), S3.set(1, o.h, 1)); m.setMatrixAt(i, M4); }); m.instanceMatrix.needsUpdate = true; }); return m.count; },
  pesti(ctx, e) { const n = clamp(num(e.count, 120), 1, 1500); const body = new THREE.SphereGeometry(0.12, 10, 6); body.scale(1, 0.6, 2.2); const tail = new THREE.ConeGeometry(0.1, 0.18, 4); tail.rotateX(-Math.PI / 2); tail.translate(0, 0, -0.32);
    const m = inst(mergeGeometries([body, tail]), new THREE.MeshStandardMaterial({ color: 0xffffff, roughness: 0.4, metalness: 0.3 }), n); m.castShadow = false; const cc = new THREE.Color(); const pal = e.colors || ['#ffb347', '#ffe066', '#5ad1ff', '#ff6f61', '#c0c8d0'];
    const fs = []; const schools = 8; for (let i = 0; i < n; i++) { const s = i % schools; fs.push({ s, r: 5 + (s % 4) * 3.5 + rnd(-0.8, 0.8), y: 1.2 + (s % 3) * 1.5 + rnd(-0.4, 0.4), a: rnd(0, 6.28), w: (s % 2 ? 1 : -1) * rnd(0.18, 0.3), cz: -10 - (s % 4) * 4, k: rnd(0.45, 0.9) }); m.setColorAt(i, cc.set(pick(pal))); }
    m.count = n; ctx.root.add(m); ctx.anim.push(dt => { fs.forEach((f, i) => { f.a += f.w * dt; const x = Math.cos(f.a) * f.r, z = f.cz + Math.sin(f.a) * f.r * 0.6; M4.compose(V3.set(x, f.y + Math.sin(f.a * 3) * 0.15, z), Q.setFromEuler(E.set(0, -f.a + (f.w > 0 ? Math.PI : 0), 0)), S3.set(f.k, f.k, f.k)); m.setMatrixAt(i, M4); }); m.instanceMatrix.needsUpdate = true; }); return n; },
  bule(ctx, e) { return particles(ctx, e, { color: '#cfefff', size: 0.06, speed: 0.8, up: true, height: 12, opacity: 0.6 }); },
  ninsoare(ctx, e) { return particles(ctx, e, { color: '#ffffff', size: 0.08, speed: 1.2, height: 16, sway: 0.4, opacity: 0.95 }); },
  ploaie(ctx, e) { return particles(ctx, e, { color: '#aaccff', size: 0.05, speed: 9, height: 16, opacity: 0.7 }); },
  praf(ctx, e) { return particles(ctx, e, { color: '#e0a27a', size: 0.05, speed: 0.15, height: 8, sway: 1.2, opacity: 0.6 }); },
  scantei(ctx, e) { return particles(ctx, e, { color: '#ff8a3a', size: 0.07, speed: 1.4, up: true, height: 14, opacity: 0.9, additive: true }); },
  licurici(ctx, e) { const n = clamp(num(e.count, 150), 1, 2000), R = num(e.radius, 12); const pos = new Float32Array(n * 3); const ph = []; for (let i = 0; i < n; i++) { pos[i * 3] = rnd(-R, R); pos[i * 3 + 1] = rnd(0.3, 3); pos[i * 3 + 2] = -rnd(0, R * 1.5) + 2; ph.push(rnd(0, 6)); }
    const g = new THREE.BufferGeometry(); g.setAttribute('position', new THREE.BufferAttribute(pos, 3)); const mat = new THREE.PointsMaterial({ color: col(e.color, '#d8ff6a'), size: 0.08, transparent: true, opacity: 0.9, blending: THREE.AdditiveBlending, depthWrite: false });
    const p = new THREE.Points(g, mat); ctx.root.add(p); let t = 0; ctx.anim.push(dt => { t += dt; mat.opacity = 0.55 + 0.4 * Math.sin(t * 2.2); for (let i = 0; i < n; i++) { pos[i * 3 + 1] += Math.sin(t + ph[i]) * dt * 0.2; pos[i * 3] += Math.cos(t * 0.7 + ph[i]) * dt * 0.15; } g.attributes.position.needsUpdate = true; }); return n; },
  raze(ctx, e) { const n = clamp(num(e.count, 8), 1, 30); const g = new THREE.Group(); for (let i = 0; i < n; i++) { const c = new THREE.Mesh(new THREE.CylinderGeometry(0.4, rnd(1.5, 3), 24, 16, 1, true), new THREE.MeshBasicMaterial({ color: 0xbfefff, transparent: true, opacity: 0.06, blending: THREE.AdditiveBlending, depthWrite: false, side: THREE.DoubleSide, fog: false }));
      c.position.set(rnd(-12, 12), 11, -rnd(2, 20)); c.rotation.z = rnd(-0.25, 0.25); c.userData.p = rnd(0, 6); g.add(c); } ctx.root.add(g); let t = 0; ctx.anim.push(dt => { t += dt; for (const c of g.children) c.material.opacity = 0.045 + 0.03 * Math.sin(t * 0.7 + c.userData.p); }); return n; },
  vulcan(ctx, e) { const H = num(e.height, 135), R = num(e.radius, 300), z = -num(e.distance, 640); const g = new THREE.ConeGeometry(R, H, 64, 12, true); g.translate(0, H / 2, 0); const p = new ImprovedNoise(); const a = g.attributes.position;
    for (let i = 0; i < a.count; i++) { const x = a.getX(i), y = a.getY(i), zz = a.getZ(i); const k = 1 + p.noise(x * 0.02, y * 0.03, zz * 0.02) * 0.18; a.setXYZ(i, x * k, Math.min(y, H * 0.93), zz * k); } g.computeVertexNormals();
    const v = new THREE.Mesh(g, new THREE.MeshStandardMaterial({ color: 0x2a2320, roughness: 1, flatShading: true })); v.position.set(0, ctx.heightAt(0, z) - 5, z); ctx.root.add(v);
    const lava = new THREE.Mesh(new THREE.CircleGeometry(R * 0.075, 32), new THREE.MeshBasicMaterial({ color: 0xff5a1a })); lava.rotation.x = -Math.PI / 2; lava.position.set(0, H * 0.92 - 5 + v.position.y + 5, z); ctx.root.add(lava);
    const L = new THREE.PointLight(0xff5a1a, 4000, 700, 1.5); L.position.set(0, H + 30, z); ctx.root.add(L);
    const smoke = new THREE.Group(); for (let i = 0; i < 40; i++) { const s = new THREE.Sprite(new THREE.SpriteMaterial({ map: softDot(), color: 0x3a3330, transparent: true, opacity: 0.55, depthWrite: false })); s.position.set(rnd(-20, 20), H + rnd(0, 200), z + rnd(-20, 20)); s.scale.setScalar(rnd(40, 110)); s.userData.v = rnd(4, 10); smoke.add(s); }
    ctx.root.add(smoke); ctx.anim.push(dt => { for (const s of smoke.children) { s.position.y += s.userData.v * dt; s.position.x += dt * 3; if (s.position.y > H + 260) { s.position.y = H; s.position.x = rnd(-20, 20); } } L.intensity = 3600 + Math.random() * 900; }); return 1; }
};
function particles(ctx, e, d) { const n = clamp(num(e.count, 2000), 10, 20000), R = num(e.radius, 20), H = num(e.height, d.height); const pos = new Float32Array(n * 3);
  for (let i = 0; i < n; i++) { pos[i * 3] = rnd(-R, R); pos[i * 3 + 1] = rnd(0, H); pos[i * 3 + 2] = rnd(-R * 1.6, R * 0.4); }
  const g = new THREE.BufferGeometry(); g.setAttribute('position', new THREE.BufferAttribute(pos, 3));
  const p = new THREE.Points(g, new THREE.PointsMaterial({ color: col(e.color, d.color), size: num(e.size, d.size), transparent: true, opacity: d.opacity, depthWrite: false, blending: d.additive ? THREE.AdditiveBlending : THREE.NormalBlending })); ctx.root.add(p);
  const sp = num(e.speed, d.speed); ctx.anim.push(dt => { for (let i = 0; i < n; i++) { let y = pos[i * 3 + 1] + (d.up ? sp : -sp) * dt; if (d.sway) pos[i * 3] += Math.sin(y + i) * dt * d.sway; if (y < 0) y += H; if (y > H) y -= H; pos[i * 3 + 1] = y; } g.attributes.position.needsUpdate = true; });
  return n; }

// ---------------------------------------------------------------- cladiri (reale sau procedurale) -> 2 geometrii mari (pereti cu ferestre + acoperisuri)
const CNAMES = { light_brown: '#c8a27a', brown: '#8a5a3a', darkbrown: '#5a3a24', dark_brown: '#5a3a24', light_grey: '#cfcfcf', lightgrey: '#cfcfcf', grey: '#9a9a9a', gray: '#9a9a9a', dark_grey: '#5a5a5a', white: '#f2f2f2', beige: '#e3d6b8', cream: '#efe6cf', yellow: '#e8d27a', light_yellow: '#f0e2a0', red: '#b0503a', light_red: '#d08070', orange: '#d8904a', pink: '#e0a8b0', green: '#7a9a6a', light_green: '#a8c098', blue: '#7a90b0', light_blue: '#a8c0d8', black: '#3a3a3a', sand: '#d8c49a', brick: '#a8573e' };
function osmColor(v) { if (!v) return null; const t = String(v).trim().toLowerCase(); if (/^#?[0-9a-f]{6}$/.test(t) || /^#?[0-9a-f]{3}$/.test(t)) return t[0] === '#' ? t : '#' + t; return CNAMES[t.replace(/[\s-]+/g, '_')] || null; }
const BCOL = ['#e8e1d3', '#d9cfbd', '#cfc6b8', '#e6dccb', '#bfb5a8', '#d8c3a5', '#c9b49a', '#eae6df', '#b9b2a6', '#d1b59a', '#a99a8a'];
function colBuilding(hex) { const c = col(osmColor(hex) || pick(BCOL), '#ddd'); return c.offsetHSL(0, rnd(-0.03, 0.03), rnd(-0.05, 0.04)); }
function pushBuilding(walls, roofs, rings0, y0, y1, color, roofColor) {
  const W = walls, R = roofs; const rings = rings0.map(r => { const q = r.slice(); if (q.length > 2 && Math.hypot(q[0][0] - q[q.length - 1][0], q[0][1] - q[q.length - 1][1]) < 0.01) q.pop(); return q; }).filter(r => r.length >= 3); if (!rings.length) return; const rc = roofColor || color.clone().offsetHSL(0, -0.05, -0.12);
  const fv = 3 / rnd(2.9, 4.1), fu = 4 / rnd(3.2, 5.5), u0 = rnd(0, 32), v0 = Math.floor(rnd(0, 8)) * 3 - y0 * fv; // etaj 2.9-4.1 m, fereastra la 3.2-5.5 m
  for (const ring of rings) { let u = u0; const n = ring.length;
    for (let i = 0; i < n; i++) { const [x1, z1] = ring[i], [x2, z2] = ring[(i + 1) % n]; const L = Math.hypot(x2 - x1, z2 - z1); if (L < 0.05) continue;
      const a = y0 * fv + v0, b = y1 * fv + v0, e = L * fu;
      W.pos.push(x1, y0, z1, x2, y0, z2, x2, y1, z2, x1, y0, z1, x2, y1, z2, x1, y1, z1);
      W.uv.push(u, a, u + e, a, u + e, b, u, a, u + e, b, u, b); u += e;
      for (let k = 0; k < 6; k++) W.col.push(color.r, color.g, color.b); } }
  const outer = rings[0].map(([x, z]) => new THREE.Vector2(x, z)), holes = rings.slice(1).map(r => r.map(([x, z]) => new THREE.Vector2(x, z)));
  if (THREE.ShapeUtils.isClockWise(outer)) outer.reverse(); holes.forEach(h => { if (!THREE.ShapeUtils.isClockWise(h)) h.reverse(); });
  let tris; try { tris = THREE.ShapeUtils.triangulateShape(outer, holes); } catch { tris = []; } const all = outer.concat(...holes);
  for (const t of tris) for (const k of [t[0], t[2], t[1]]) { R.pos.push(all[k].x, y1, all[k].y); R.col.push(rc.r, rc.g, rc.b); }
}
function addBuildingMeshes(ctx, walls, roofs, plain) {
  if (plain && walls.pos.length) { // monumentul tinta: piatra, fara grila de ferestre de bloc
    const g = new THREE.BufferGeometry(); g.setAttribute('position', new THREE.Float32BufferAttribute(walls.pos, 3)); g.setAttribute('color', new THREE.Float32BufferAttribute(walls.col, 3)); g.computeVertexNormals();
    const m = new THREE.Mesh(g, new THREE.MeshStandardMaterial({ vertexColors: true, roughness: 0.92, side: THREE.DoubleSide })); m.castShadow = m.receiveShadow = true; ctx.root.add(m); walls = newBuf(); }
  if (walls.pos.length) { const g = new THREE.BufferGeometry(); g.setAttribute('position', new THREE.Float32BufferAttribute(walls.pos, 3)); g.setAttribute('uv', new THREE.Float32BufferAttribute(walls.uv, 2)); g.setAttribute('color', new THREE.Float32BufferAttribute(walls.col, 3)); g.computeVertexNormals();
    const F = ctx.facade || (ctx.facade = facadeTextures()); const m = new THREE.Mesh(g, new THREE.MeshStandardMaterial({ map: F.map, vertexColors: true, roughness: 0.85, side: THREE.DoubleSide, emissiveMap: F.em, emissive: ctx.night ? 0xffffff : 0x000000, emissiveIntensity: ctx.night ? 0.9 : 0 }));
    m.castShadow = m.receiveShadow = true; ctx.root.add(m); }
  if (roofs.pos.length) { const g = new THREE.BufferGeometry(); g.setAttribute('position', new THREE.Float32BufferAttribute(roofs.pos, 3)); g.setAttribute('color', new THREE.Float32BufferAttribute(roofs.col, 3)); g.computeVertexNormals();
    const m = new THREE.Mesh(g, new THREE.MeshStandardMaterial({ vertexColors: true, roughness: 0.9, side: THREE.DoubleSide })); m.castShadow = m.receiveShadow = true; ctx.root.add(m); }
}
const newBuf = () => ({ pos: [], uv: [], col: [] });

// ---------------------------------------------------------------- teren generat
function genTerrain(ctx, G) {
  const perlin = new ImprovedNoise(), seed = Math.random() * 100; const SIZE = num(G.size, 520), SEG = 240, FLAT = num(G.flat, 7);
  const elev = num(G.elev, 20), mount = num(G.mount, 1), island = num(G.island, 0); const craters = [];
  for (let i = 0; i < num(G.craters, 0); i++) craters.push([rnd(-200, 200), -rnd(10, 230), rnd(3, 28)]);
  const h0 = (x, z) => { const d = Math.hypot(x, z + 2); let h = 0, amp = 1, f = 0.012;
    for (let o = 0; o < 5; o++) { h += perlin.noise(x * f + seed, z * f + seed, seed) * amp; amp *= 0.5; f *= 2.1; }
    const far = Math.max(0, (d - 60) / 70); h = h * elev * 0.35 + Math.pow(Math.max(0, perlin.noise(x * 0.008, z * 0.008, seed + 3) + 0.35), 2) * elev * 2.2 * mount * Math.min(1, far);
    if (G.valley) h = h * 0.6 + Math.max(0, d - 40) * 0.12 * mount;
    if (G.beach) { const b = -(z + 2) - num(G.beach, 18); h = h * 0.3 - clamp(b / 25, 0, 1) * 3 - Math.max(0, b) * 0.015; } // plaja: terenul coboara sub apa in spatele lui Kelion
    if (G.lake) { const r = num(G.lake, 40); const q = 1 - Math.hypot(x * 0.7, z + r * 0.75 + 10) / r; if (q > 0) h -= Math.min(1, q * 3) * 12; }
    if (island) h = h - Math.max(0, d - island) * 0.12 + 1.2;
    for (const [cx, cz, r] of craters) { const q = Math.hypot(x - cx, z - cz) / r; if (q < 1.4) h += (q < 1 ? (q * q - 1) * r * 0.25 : (1.4 - q) * r * 0.25 * 0.6); }
    return h; };
  const ref = h0(0, 0); const base = (x, z) => { const d = Math.hypot(x, z + 2); const k = THREE.MathUtils.smoothstep(d, FLAT, FLAT + 14); return (h0(x, z) - ref) * k; };
  const geo = new THREE.PlaneGeometry(SIZE, SIZE, SEG, SEG); geo.rotateX(-Math.PI / 2); const pos = geo.attributes.position, cl = new Float32Array(pos.count * 3), c = new THREE.Color();
  const cLow = col(G.low, '#4f7a2e'), cMid = col(G.mid, '#3f6a28'), cHigh = col(G.high, '#6b6458'), cPeak = col(G.peak, '#f2f4f7'), shore = col(G.shore || G.low, '#d8c089');
  let maxH = 1; for (let i = 0; i < pos.count; i++) { const y = base(pos.getX(i), pos.getZ(i)); pos.setY(i, y); maxH = Math.max(maxH, y); }
  for (let i = 0; i < pos.count; i++) { const x = pos.getX(i), z = pos.getZ(i), y = pos.getY(i); const t = y / Math.max(4, maxH), n = perlin.noise(x * 0.15, z * 0.15, 7) * 0.1;
    if (ctx.waterLevel !== null && y < ctx.waterLevel + 0.4) c.copy(shore); else if (t + n > 0.72) c.copy(cPeak); else if (t + n > 0.42) c.copy(cHigh); else if (t + n > 0.15) c.copy(cMid).lerp(cHigh, (t + n - 0.15) / 0.27); else c.copy(cLow).lerp(cMid, Math.max(0, (t + n) / 0.15));
    if (G.lava && perlin.noise(x * 0.05, z * 0.05, 11) > 0.32 && Math.hypot(x, z) > 9) c.set('#ff4a12');
    c.offsetHSL(0, 0, n * 0.5); cl.set([c.r, c.g, c.b], i * 3); }
  geo.setAttribute('color', new THREE.BufferAttribute(cl, 3)); geo.computeVertexNormals();
  const mat = new THREE.MeshStandardMaterial({ vertexColors: true, roughness: 0.95 }); if (G.lava) { mat.emissive = new THREE.Color(0xffffff); mat.emissiveIntensity = 0; }
  const ground = new THREE.Mesh(geo, mat); ground.receiveShadow = true; ctx.root.add(ground);
  if (G.lava) { // lava straluceste: un al doilea strat emisiv doar pe petele de lava
    const lg = geo.clone(); const lc = lg.attributes.color; for (let i = 0; i < lc.count; i++) { const lava = lc.getX(i) > 0.9 && lc.getY(i) < 0.45; lc.setXYZ(i, lava ? 1 : 0, lava ? 0.35 : 0, lava ? 0.05 : 0); }
    const lm = new THREE.Mesh(lg, new THREE.MeshBasicMaterial({ vertexColors: true, transparent: true, opacity: 0.9, blending: THREE.AdditiveBlending, depthWrite: false })); lm.position.y = 0.02; ctx.root.add(lm); }
  ctx.heightAt = (x, z) => base(x, z); ctx.extent = SIZE;
}
function flatGround(ctx, G) { const size = num(G.size, 900); const tex = floorTex(G.texture || 'asfalt', G.color || '#5d6066', [size / (G.texture === 'marmura' ? 4 : 8), size / (G.texture === 'marmura' ? 4 : 8)]);
  const m = new THREE.Mesh(new THREE.PlaneGeometry(size, size), new THREE.MeshStandardMaterial({ map: tex, roughness: G.texture === 'marmura' ? 0.35 : 0.9, polygonOffset: true, polygonOffsetFactor: -2, polygonOffsetUnits: -2 })); m.rotation.x = -Math.PI / 2; m.position.y = 0.01; m.receiveShadow = true; ctx.root.add(m); ctx.heightAt = () => 0; ctx.extent = size;
  if (G.around) { const sub = { root: ctx.root, waterLevel: null, anim: ctx.anim }; genTerrain(sub, { ...G.around, flat: size / 2 + 4, size: 700 }); ctx.heightAt = (x, z) => Math.abs(x) < size / 2 && Math.abs(z) < size / 2 ? 0 : sub.heightAt(x, z); ctx.extent = 700; } }
function interior(ctx, G) { // camera inchisa: podea, pereti, tavan, ferestre luminoase, lumini de tavan
  const W = num(G.width, 12), Dp = num(G.depth, 16), H = num(G.height, 3.2); const z0 = 7.5, z1 = z0 - Dp; // peretele din spatele camerei e in spatele privitorului
  const floor = new THREE.Mesh(new THREE.PlaneGeometry(W, Dp), new THREE.MeshStandardMaterial({ map: floorTex(G.floor || 'lemn', G.floorColor || '#b08a60', [W / 3, Dp / 3]), roughness: G.floor === 'marmura' ? 0.3 : 0.75 }));
  floor.rotation.x = -Math.PI / 2; floor.position.set(0, 0, (z0 + z1) / 2); floor.receiveShadow = true; ctx.root.add(floor);
  const wm = new THREE.MeshStandardMaterial({ color: col(G.wall, '#e6e1d8'), roughness: 0.9, side: THREE.DoubleSide }); const mk = (w, h, x, y, z, ry) => { const m = new THREE.Mesh(new THREE.PlaneGeometry(w, h), wm); m.position.set(x, y, z); m.rotation.y = ry; m.receiveShadow = true; ctx.root.add(m); return m; };
  mk(W, H, 0, H / 2, z1, 0); mk(Dp, H, -W / 2, H / 2, (z0 + z1) / 2, Math.PI / 2); mk(Dp, H, W / 2, H / 2, (z0 + z1) / 2, -Math.PI / 2); mk(W, H, 0, H / 2, z0, Math.PI);
  const ceil = new THREE.Mesh(new THREE.PlaneGeometry(W, Dp), new THREE.MeshStandardMaterial({ color: col(G.ceiling, '#f4f2ee'), roughness: 1, side: THREE.DoubleSide })); ceil.rotation.x = Math.PI / 2; ceil.position.set(0, H, (z0 + z1) / 2); ctx.root.add(ceil);
  const base = new THREE.MeshStandardMaterial({ color: col(G.wall, '#e6e1d8').offsetHSL(0, 0, -0.25), roughness: 0.7 }); for (const [w, x, z, ry] of [[W, 0, z1 + 0.02, 0], [Dp, -W / 2 + 0.02, (z0 + z1) / 2, Math.PI / 2], [Dp, W / 2 - 0.02, (z0 + z1) / 2, -Math.PI / 2]]) { const b = new THREE.Mesh(new THREE.BoxGeometry(w, 0.12, 0.02), base); b.position.set(x, 0.06, z); b.rotation.y = ry; ctx.root.add(b); }
  if (G.windows !== false) { const glass = new THREE.MeshBasicMaterial({ color: ctx.night ? 0x1a2440 : 0xd8ecff }); const frame = new THREE.MeshStandardMaterial({ color: 0xf0f0f0, roughness: 0.5 });
    const nw = Math.max(1, Math.floor(Dp / 4)); for (let i = 0; i < nw; i++) { const z = z1 + (i + 0.5) * Dp / nw; for (const sx of [-1, 1]) { if (sx > 0 && G.windows === 'stanga') continue; const g = new THREE.Mesh(new THREE.PlaneGeometry(Math.min(2.4, Dp / nw - 0.8), H * 0.55), glass); g.position.set(sx * (W / 2 - 0.03), H * 0.55, z); g.rotation.y = -sx * Math.PI / 2; ctx.root.add(g);
      const f = new THREE.Mesh(new THREE.BoxGeometry(0.06, H * 0.55 + 0.1, 0.06), frame); f.position.set(sx * (W / 2 - 0.05), H * 0.55, z); ctx.root.add(f); } }
    if (!ctx.night) { const d = new THREE.DirectionalLight(0xfff4e0, 1.6); d.position.set(-W, H * 1.5, z1 / 2); d.target.position.set(0, 0, z1 / 2); d.castShadow = true; d.shadow.mapSize.set(2048, 2048); const sc = d.shadow.camera; sc.left = -Dp; sc.right = Dp; sc.top = Dp; sc.bottom = -Dp; ctx.root.add(d, d.target); } }
  const nl = clamp(num(G.lights, 4), 0, 12); const panel = new THREE.MeshBasicMaterial({ color: 0xfffaf0 }); for (let i = 0; i < nl; i++) { const z = z1 + (i + 0.5) * Dp / nl; const p = new THREE.Mesh(new THREE.PlaneGeometry(1.2, 0.5), panel); p.rotation.x = Math.PI / 2; p.position.set(0, H - 0.01, z); ctx.root.add(p);
    const L = new THREE.PointLight(0xfff2dc, num(G.lightPower, 14) * H, Math.max(W, H * 3), 1.6); L.position.set(0, H - 0.3, z); ctx.root.add(L); }
  ctx.root.add(new THREE.HemisphereLight(0xffffff, 0x8a7a6a, 0.7)); ctx.heightAt = () => 0; ctx.extent = Math.max(W, Dp) * 2; ctx.indoor = true;
  ctx.root.userData.bounds = { W, z0, z1, H };
}
function cave(ctx, G) { genTerrain(ctx, { ...G, elev: 3, mount: 0.2, size: 140, flat: 5 }); const p = new ImprovedNoise(); const R = 42;
  const g = new THREE.SphereGeometry(R, 96, 48, 0, Math.PI * 2, 0, Math.PI / 2); const a = g.attributes.position;
  for (let i = 0; i < a.count; i++) { const v = new THREE.Vector3().fromBufferAttribute(a, i); const n = p.noise(v.x * 0.08, v.y * 0.08, v.z * 0.08) * 0.35 + p.noise(v.x * 0.25, v.y * 0.25, v.z * 0.25) * 0.1; v.multiplyScalar(1 + n); v.y *= 0.32; a.setXYZ(i, v.x, v.y, v.z); }
  g.computeVertexNormals(); const dome = new THREE.Mesh(g, new THREE.MeshStandardMaterial({ color: col(G.high, '#3a332c'), roughness: 1, side: THREE.BackSide, flatShading: true })); dome.position.set(0, -1, -10); dome.receiveShadow = true; ctx.root.add(dome);
  ctx.ceilingAt = (x, z) => { const dx = x, dz = z + 10; const r = Math.hypot(dx, dz) / R; return r < 1 ? Math.sqrt(Math.max(0, 1 - r * r)) * R * 0.32 - 1.5 : 2; };
  const L = new THREE.PointLight(0xffa860, 40, 30, 1.6); L.position.set(2, 3, -3); ctx.root.add(L); }
function water(ctx, Wc) { const level = num(Wc.level, -0.8); ctx.waterLevel = level; const nm = waterNormals(); nm.repeat.set(60, 60);
  const m = new THREE.Mesh(new THREE.PlaneGeometry(6000, 6000), new THREE.MeshStandardMaterial({ color: col(Wc.color, '#2f6f8f'), roughness: 0.12, metalness: 0.35, normalMap: nm, normalScale: new THREE.Vector2(0.6, 0.6), transparent: true, opacity: 0.9 }));
  m.rotation.x = -Math.PI / 2; m.position.y = level; m.receiveShadow = true; ctx.root.add(m); if (Wc.waves !== false) ctx.anim.push(dt => { nm.offset.x += dt * 0.004; nm.offset.y += dt * 0.0025; }); }
function platform(ctx) { const g = new THREE.Group(); const d = new THREE.Mesh(new THREE.CylinderGeometry(3.2, 3.4, 0.25, 64), new THREE.MeshStandardMaterial({ color: 0x0b1a28, metalness: 0.6, roughness: 0.3, transparent: true, opacity: 0.8 })); d.position.y = -0.125;
  const r = new THREE.Mesh(new THREE.TorusGeometry(3.3, 0.04, 8, 96), new THREE.MeshBasicMaterial({ color: 0x46e0ff })); r.rotation.x = Math.PI / 2; r.position.y = 0.01; const r2 = r.clone(); r2.scale.setScalar(0.6);
  g.add(d, r, r2); g.position.z = -0.5; ctx.root.add(g); ctx.heightAt = ctx.heightAt || (() => 0); }

// ---------------------------------------------------------------- MOD REAL: loc real la scara 1:1
async function geocode(q) { const r = await fetchT('https://nominatim.openstreetmap.org/search?format=jsonv2&limit=1&accept-language=ro&q=' + encodeURIComponent(q), 12000);
  if (!r.ok) throw new Error('geocodare ' + r.status); const j = await r.json(); if (!j.length) throw new Error('nu am gasit locul: ' + q); return { lat: +j[0].lat, lon: +j[0].lon, name: j[0].name || j[0].display_name.split(',')[0], full: j[0].display_name }; }
const lon2tx = (lon, z) => (lon + 180) / 360 * 2 ** z, lat2ty = (lat, z) => (1 - Math.log(Math.tan(lat * D2R) + 1 / Math.cos(lat * D2R)) / Math.PI) / 2 * 2 ** z;
const tx2lon = (x, z) => x / 2 ** z * 360 - 180, ty2lat = (y, z) => Math.atan(Math.sinh(Math.PI * (1 - 2 * y / 2 ** z))) / D2R;
async function elevationGrid(lat, lon, half, z) { // relief real: Terrarium PNG -> metri; intoarce functie (lat,lon) -> altitudine
  const dLat = half / 110574, dLon = half / (111320 * Math.cos(lat * D2R)); const x0 = Math.floor(lon2tx(lon - dLon, z)), x1 = Math.floor(lon2tx(lon + dLon, z)), y0 = Math.floor(lat2ty(lat + dLat, z)), y1 = Math.floor(lat2ty(lat - dLat, z));
  const nx = x1 - x0 + 1, ny = y1 - y0 + 1; if (nx * ny > 36) throw new Error('prea multe placi de relief');
  const cv = document.createElement('canvas'); cv.width = nx * 256; cv.height = ny * 256; const g = cv.getContext('2d'); let ok = 0;
  await Promise.all([...Array(nx * ny)].map(async (_, i) => { const tx = x0 + (i % nx), ty = y0 + Math.floor(i / nx);
    try { const r = await fetchT(`https://s3.amazonaws.com/elevation-tiles-prod/terrarium/${z}/${tx}/${ty}.png`, 15000); if (!r.ok) return; const bm = await createImageBitmap(await r.blob()); g.drawImage(bm, (tx - x0) * 256, (ty - y0) * 256); ok++; } catch (e) { console.warn('relief', e.message); } }));
  if (!ok) throw new Error('relieful nu s-a putut incarca');
  const d = g.getImageData(0, 0, cv.width, cv.height).data; const W = cv.width, H = cv.height;
  const at = (px, py) => { px = clamp(px, 0, W - 1); py = clamp(py, 0, H - 1); const i = (py * W + px) * 4; return d[i] * 256 + d[i + 1] + d[i + 2] / 256 - 32768; };
  return (la, lo) => { const fx = (lon2tx(lo, z) - x0) * 256 - 0.5, fy = (lat2ty(la, z) - y0) * 256 - 0.5; const ix = Math.floor(fx), iy = Math.floor(fy), ax = fx - ix, ay = fy - iy;
    return at(ix, iy) * (1 - ax) * (1 - ay) + at(ix + 1, iy) * ax * (1 - ay) + at(ix, iy + 1) * (1 - ax) * ay + at(ix + 1, iy + 1) * ax * ay; };
}
let VT = null; async function vtLibs() { return VT || (VT = Promise.all([import('https://cdn.jsdelivr.net/npm/pbf@3.2.1/+esm'), import('https://cdn.jsdelivr.net/npm/@mapbox/vector-tile@2.0.3/+esm')]).then(([a, b]) => ({ Pbf: a.default, VectorTile: b.VectorTile }))); }
let TJ = null; async function tileUrl() { return TJ || (TJ = fetchT('https://tiles.openfreemap.org/planet', 12000).then(r => r.json()).then(j => j.tiles[0]).catch(e => { TJ = null; throw e; })); }
async function osmFeatures(lat, lon, half) { const { Pbf, VectorTile } = await vtLibs(); const URL0 = await tileUrl(); const Z = 14;
  const dLat = half / 110574, dLon = half / (111320 * Math.cos(lat * D2R)); const tiles = [];
  for (let x = Math.floor(lon2tx(lon - dLon, Z)); x <= Math.floor(lon2tx(lon + dLon, Z)); x++) for (let y = Math.floor(lat2ty(lat + dLat, Z)); y <= Math.floor(lat2ty(lat - dLat, Z)); y++) tiles.push([x, y]);
  if (tiles.length > 30) tiles.length = 30; const feats = []; let ok = 0;
  await Promise.all(tiles.map(async ([x, y]) => { try { const r = await fetchT(URL0.replace('{z}', Z).replace('{x}', x).replace('{y}', y), 15000); if (!r.ok) return; ok++;
    const vt = new VectorTile(new Pbf(new Uint8Array(await r.arrayBuffer())));
    for (const L of ['building', 'transportation', 'water', 'waterway', 'park', 'landcover', 'landuse', 'aeroway']) { const ly = vt.layers[L]; if (!ly) continue; for (let i = 0; i < ly.length; i++) { const f = ly.feature(i); feats.push({ L, p: f.properties, g: f.toGeoJSON(x, y, Z).geometry }); } } } catch (e) { console.warn('osm', e.message); } }));
  return { feats, ok, tiles: tiles.length }; }
const polysOf = gm => gm.type === 'Polygon' ? [gm.coordinates] : gm.type === 'MultiPolygon' ? gm.coordinates : [];
const linesOf = gm => gm.type === 'LineString' ? [gm.coordinates] : gm.type === 'MultiLineString' ? gm.coordinates : gm.type === 'Polygon' ? gm.coordinates : [];
function inPoly(x, z, ring) { let c = false; for (let i = 0, j = ring.length - 1; i < ring.length; j = i++) { const [xi, zi] = ring[i], [xj, zj] = ring[j]; if ((zi > z) !== (zj > z) && x < (xj - xi) * (z - zi) / (zj - zi) + xi) c = !c; } return c; }
function distSeg(px, pz, [x1, z1], [x2, z2]) { const dx = x2 - x1, dz = z2 - z1, L = dx * dx + dz * dz; const t = L ? clamp(((px - x1) * dx + (pz - z1) * dz) / L, 0, 1) : 0; return Math.hypot(px - x1 - t * dx, pz - z1 - t * dz); }

async function realSpace(ctx, spec) {
  let { lat, lon } = spec; let name = spec.place || spec.label || ''; let full = '';
  if (!isFinite(+lat) || !isFinite(+lon)) { if (!spec.place) throw new Error('pentru un loc real trimite place (numele locului) sau lat/lon'); const g = await geocode(spec.place); lat = g.lat; lon = g.lon; name = spec.label || g.name || spec.place; full = g.full; }
  lat = +lat; lon = +lon; const R = clamp(num(spec.radius, 450), 150, 1500); const kx = 111320 * Math.cos(lat * D2R), kz = 110574;
  const LX = lo => (lo - lon) * kx, LZ = la => -(la - lat) * kz; // metri locali fata de tinta (x = est, z = -nord)
  const [elevNear, elevFar, osm] = await Promise.all([
    elevationGrid(lat, lon, R * 1.25 + 300, R > 900 ? 13 : 14).catch(e => { console.warn(e); return null; }),
    elevationGrid(lat, lon, 4200, 11).catch(e => { console.warn(e); return null; }),
    osmFeatures(lat, lon, R).catch(e => { console.warn(e); return { feats: [], ok: 0, tiles: 0 }; })]);
  if (!elevNear && !osm.ok) throw new Error('serverele de harti/relief nu raspund acum');
  const E0 = (x, z) => { const la = lat - z / kz, lo = lon + x / kx; if (elevNear && Math.abs(x) < R * 1.25 + 250 && Math.abs(z) < R * 1.25 + 250) return elevNear(la, lo); return elevFar ? elevFar(la, lo) : 0; };
  // cladiri in metri locali
  const blds = []; const roads = []; const areas = [];
  for (const f of osm.feats) {
    if (f.L === 'building') { for (const poly of polysOf(f.g)) { const rings = poly.map(r => r.map(c => [LX(c[0]), LZ(c[1])])); const o = rings[0]; if (o.length < 4) continue; let cx = 0, cz = 0; o.forEach(p => { cx += p[0]; cz += p[1]; }); cx /= o.length; cz /= o.length;
        if (Math.hypot(cx, cz) > R) continue; const hp = +f.p.render_height || (+f.p.levels ? +f.p.levels * 3.2 : 0) || 9, h0 = +f.p.render_min_height || 0; blds.push({ rings, cx, cz, h: Math.max(2.5, hp), h0, colour: f.p.colour, hide: !!f.p.hide_3d }); } }
    else if (f.L === 'transportation' || f.L === 'aeroway' && /runway|taxiway/.test(f.p.class)) { const cls = String(f.p.class || ''); const w = { motorway: 16, trunk: 14, primary: 12, secondary: 10, tertiary: 8, minor: 6.5, service: 4, track: 3, path: 2.2, rail: 3, transit: 3, runway: 45, taxiway: 18 }[cls] || 5;
      if (f.g.type === 'Polygon' || f.g.type === 'MultiPolygon') { for (const poly of polysOf(f.g)) areas.push({ kind: 'paved', ring: poly[0].map(c => [LX(c[0]), LZ(c[1])]) }); continue; }
      for (const ln of linesOf(f.g)) roads.push({ w, cls, brunnel: f.p.brunnel, pts: ln.map(c => [LX(c[0]), LZ(c[1])]) }); }
    else if (f.L === 'waterway') { for (const ln of linesOf(f.g)) roads.push({ w: /river|canal/.test(f.p.class) ? 18 : 4, cls: 'waterway', pts: ln.map(c => [LX(c[0]), LZ(c[1])]) }); }
    else { const cls = String(f.p.class || f.p.subclass || ''); const kind = f.L === 'water' ? 'water' : f.L === 'park' ? 'park' : /wood|forest/.test(cls) ? 'wood' : /grass|meadow|farmland|park|garden|scrub|cemetery|pitch|recreation|golf/.test(cls) ? 'grass' : /sand|beach/.test(cls) ? 'sand' : /ice|glacier/.test(cls) ? 'ice' : /rock|bare/.test(cls) ? 'rock' : /residential|commercial|retail|industrial|square|pedestrian|school|university|hospital/.test(cls) ? 'urban' : null;
      if (!kind) continue; for (const poly of polysOf(f.g)) areas.push({ kind, ring: poly[0].map(c => [LX(c[0]), LZ(c[1])]), holes: poly.slice(1).map(r => r.map(c => [LX(c[0]), LZ(c[1])])) }); }
  }
  // index spatial (celule de 32 m) pentru teste rapide de coliziune si linie de vedere
  const CELL = 32, grid = new Map(), key = (i, j) => i + ',' + j;
  for (const b of blds) { const o = b.rings[0]; let x0 = Infinity, z0 = Infinity, x1 = -Infinity, z1 = -Infinity; for (const [x, z] of o) { x0 = Math.min(x0, x); x1 = Math.max(x1, x); z0 = Math.min(z0, z); z1 = Math.max(z1, z); } b.bb = [x0, z0, x1, z1];
    for (let i = Math.floor(x0 / CELL); i <= Math.floor(x1 / CELL); i++) for (let j = Math.floor(z0 / CELL); j <= Math.floor(z1 / CELL); j++) { const k = key(i, j); if (!grid.has(k)) grid.set(k, []); grid.get(k).push(b); } }
  const around = (x, z, r) => { const out = new Set(); for (let i = Math.floor((x - r) / CELL); i <= Math.floor((x + r) / CELL); i++) for (let j = Math.floor((z - r) / CELL); j <= Math.floor((z + r) / CELL); j++) { const a = grid.get(key(i, j)); if (a) for (const b of a) out.add(b); } return out; };
  const insideB = (x, z, skip) => { for (const b of around(x, z, 0)) { if (b.hide || (skip && skip.has(b))) continue; const q = b.bb; if (x < q[0] || x > q[2] || z < q[1] || z > q[3]) continue; if (inPoly(x, z, b.rings[0])) return b; } return null; };
  const nearB = (x, z, r) => { for (const b of around(x, z, r)) { if (b.hide) continue; const q = b.bb; if (x < q[0] - r || x > q[2] + r || z < q[1] - r || z > q[3] + r) continue; if (inPoly(x, z, b.rings[0])) return true; const o = b.rings[0]; for (let i = 0; i < o.length - 1; i++) if (distSeg(x, z, o[i], o[i + 1]) < r) return true; } return false; };
  // tinta: cea mai proeminenta cladire de langa punct (inaltime x suprafata x apropiere); partile ei (building:part) se grupeaza sub conturul comun
  const areaOf = o => { let a = 0; for (let i = 0, j = o.length - 1; i < o.length; j = i++) a += (o[j][0] + o[i][0]) * (o[j][1] - o[i][1]); return Math.abs(a / 2); };
  const distPoly = (x, z, o) => { if (inPoly(x, z, o)) return 0; let d = Infinity; for (let i = 0; i < o.length - 1; i++) d = Math.min(d, distSeg(x, z, o[i], o[i + 1])); return d; };
  let target = null, bestS = 0; for (const b of around(0, 0, 120)) { if (b.hide) continue; const d = distPoly(0, 0, b.rings[0]); if (d > 120) continue; const sc = (b.h + 1) * Math.pow(Math.max(10, areaOf(b.rings[0])), 0.3) * Math.exp(-d / 45); if (sc > bestS) { bestS = sc; target = b; } }
  if (spec.target === false) target = null;
  const tset = new Set(); let tring = null, tx = 0, tz = 0, tSize = 0, tH = 0;
  if (target) { const outline = blds.find(b => b.hide && b.bb && inPoly(target.cx, target.cz, b.rings[0])); tring = outline ? outline.rings[0] : target.rings[0]; tset.add(target);
    if (outline) for (const b of around((outline.bb[0] + outline.bb[2]) / 2, (outline.bb[1] + outline.bb[3]) / 2, Math.max(outline.bb[2] - outline.bb[0], outline.bb[3] - outline.bb[1]) / 2)) if (!b.hide && inPoly(b.cx, b.cz, tring)) tset.add(b);
    let x0 = Infinity, z0 = Infinity, x1 = -Infinity, z1 = -Infinity; for (const [x, z] of tring) { x0 = Math.min(x0, x); x1 = Math.max(x1, x); z0 = Math.min(z0, z); z1 = Math.max(z1, z); }
    tx = (x0 + x1) / 2; tz = (z0 + z1) / 2; tSize = Math.max(x1 - x0, z1 - z0); for (const b of tset) tH = Math.max(tH, b.h); }
  // punctul de stat: loc liber pentru Kelion si camera + linie de vedere libera spre tinta (tinta apare in spatele lui Kelion, intreaga daca se poate)
  const DIRS = { sud: 180, nord: 0, est: 90, vest: 270, south: 180, north: 0, east: 90, west: 270, 'sud-est': 135, 'sud-vest': 225, 'nord-est': 45, 'nord-vest': 315 };
  const named = spec.view_from_deg !== undefined || (spec.view_from && DIRS[String(spec.view_from).toLowerCase()] !== undefined);
  const az0 = num(spec.view_from_deg, DIRS[String(spec.view_from || 'sud').toLowerCase()] ?? 180);
  const want = num(spec.distance, target ? clamp(Math.max(tH * 2.6, tSize * 1.35) + 10, 22, 520) : 4); // tinta incape in cadru (FOV vertical 28 grade, orizontal ~47)
  const bearings = named ? [az0] : [...Array(16)].map((_, i) => i * 22.5);
  const dists = spec.distance !== undefined ? [want, want * 1.15, want * 0.85, want * 1.35, want * 1.6] : [want, want * 0.75, want * 1.3, want * 1.7, want * 0.5, want * 2.2, want * 3];
  const waters = areas.filter(a => a.kind === 'water'); const wetAt = (x, z) => waters.some(a => inPoly(x, z, a.ring)) || roads.some(r => r.cls === 'waterway' && r.w > 6 && r.pts.some((p, i) => i && distSeg(x, z, r.pts[i - 1], p) < r.w / 2 + 2));
  let pickC = null;
  for (const a of bearings) { const ar = a * D2R, ux = Math.sin(ar), uz = -Math.cos(ar);
    for (const d of dists) { const px0 = tx + ux * d, pz0 = tz + uz * d; if (Math.hypot(px0, pz0) > R * 1.15) continue;
      if (nearB(px0, pz0, 3.2) || nearB(px0 + ux * 2.3, pz0 + uz * 2.3, 1.6) || nearB(px0 + ux * 4.8, pz0 + uz * 4.8, 1.6) || (tring && inPoly(px0, pz0, tring))) continue; // Kelion si camera stau pe loc liber
      let obs = 0; const Lm = target ? d : d + 60;
      for (let t = 3; t < Lm; t += 4) { const qx = px0 - ux * t, qz = pz0 - uz * t; if (tring && inPoly(qx, qz, tring)) break; const ob = insideB(qx, qz, tset); if (ob && ob.h > 3) obs += t < 40 ? 3 : 1; }
      if (wetAt(px0, pz0)) continue; // nu pe apa
      const cost = obs * 4 + Math.abs(d - want) / want * 3 + (named ? 0 : Math.abs(((a - 180 + 540) % 360) - 180) / 180 * 0.6);
      if (!pickC || cost < pickC.cost) pickC = { cost, sx: px0, sz: pz0, a, d, obs }; } }
  if (!pickC) { const ar = az0 * D2R, ux = Math.sin(ar), uz = -Math.cos(ar); let d = want; while (d < want + 400 && nearB(tx + ux * d, tz + uz * d, 3.2)) d += 5; pickC = { sx: tx + ux * d, sz: tz + uz * d, a: az0, d, obs: -1 }; }
  const viewAz = pickC.a * D2R; let sx = pickC.sx, sz = pickC.sz;
  const Hs = E0(sx, sz); const phi = Math.PI - viewAz; // rotatia lumii: directia "spre tinta" devine -z (in spatele lui Kelion, vizibila pentru privitor)
  const cP = Math.cos(phi), sP = Math.sin(phi);
  const toS = (x, z) => { const dx = x - sx, dz = z - sz; return [dx * cP - dz * sP, dx * sP + dz * cP]; };
  const toL = (X, Z) => [X * cP + Z * sP + sx, -X * sP + Z * cP + sz];
  const FLAT = 6; const hAt = (X, Z) => { const [x, z] = toL(X, Z); const h = E0(x, z) - Hs; const d = Math.hypot(X, Z + 2); return h * THREE.MathUtils.smoothstep(d, FLAT, FLAT + 10); };
  ctx.heightAt = hAt; ctx.waterLevel = null;
  // teren apropiat cu textura pictata din OSM (strazi, parcuri, apa) + teren indepartat (munti reali) colorat dupa altitudine
  const HALF = Math.min(1900, (R + Math.hypot(sx, sz)) * 1.05 + 40); const TEX = 4096; const pxPerM = TEX / (2 * HALF);
  const cv = document.createElement('canvas'); cv.width = cv.height = TEX; const g = cv.getContext('2d'); const lat0 = Math.abs(lat);
  g.fillStyle = lat0 > 62 ? '#c9ccb8' : '#8f9a6a'; g.fillRect(0, 0, TEX, TEX);
  const P2 = ([X, Z]) => [(X + HALF) * pxPerM, (Z + HALF) * pxPerM];
  const fillRing = (ring, holes, style) => { g.beginPath(); for (const r of [ring, ...(holes || [])]) { r.forEach((p, i) => { const [u, v] = P2(toS(p[0], p[1])); i ? g.lineTo(u, v) : g.moveTo(u, v); }); g.closePath(); } g.fillStyle = style; g.fill('evenodd'); };
  const AC = { urban: '#a9a49a', grass: '#7fa457', park: '#6f9e4c', wood: '#4d7a3a', sand: '#e0cfa0', ice: '#eef4f8', rock: '#9a9488', paved: '#8d8b88', water: '#3d7fa6' };
  for (const k of ['urban', 'rock', 'sand', 'ice', 'grass', 'park', 'wood', 'paved', 'water']) for (const a of areas) if (a.kind === k) fillRing(a.ring, a.holes, AC[k]);
  g.lineCap = 'round'; g.lineJoin = 'round';
  const stroke = (pts, w, style) => { g.beginPath(); pts.forEach((p, i) => { const [u, v] = P2(toS(p[0], p[1])); i ? g.lineTo(u, v) : g.moveTo(u, v); }); g.strokeStyle = style; g.lineWidth = Math.max(1, w * pxPerM); g.stroke(); };
  for (const r of roads) if (r.cls === 'waterway') stroke(r.pts, r.w, AC.water);
  for (const r of roads) if (r.cls !== 'waterway' && r.cls !== 'rail' && r.cls !== 'path') stroke(r.pts, r.w + 3, '#c9c4ba'); // trotuar
  for (const r of roads) if (r.cls === 'path') stroke(r.pts, r.w, '#cdbf9e');
  for (const r of roads) if (r.cls !== 'waterway' && r.cls !== 'path') stroke(r.pts, r.w, r.cls === 'rail' ? '#6b6158' : '#4a4b4f');
  for (const r of roads) if (/motorway|trunk|primary|secondary/.test(r.cls)) { g.setLineDash([3 * pxPerM, 6 * pxPerM]); stroke(r.pts, 0.25, '#f2efe6'); g.setLineDash([]); }
  const tex = new THREE.CanvasTexture(cv); tex.colorSpace = THREE.SRGBColorSpace; tex.anisotropy = ctx.renderer.capabilities.getMaxAnisotropy();
  const SEG = 256; const ng = new THREE.PlaneGeometry(2 * HALF, 2 * HALF, SEG, SEG); ng.rotateX(-Math.PI / 2); const np = ng.attributes.position; for (let i = 0; i < np.count; i++) np.setY(i, hAt(np.getX(i), np.getZ(i)));
  ng.computeVertexNormals(); const nearM = new THREE.Mesh(ng, new THREE.MeshStandardMaterial({ map: tex, roughness: 0.95 })); nearM.receiveShadow = true; ctx.root.add(nearM);
  // apa ca suprafata usor reflectorizanta peste zonele de apa (doar aproape)
  const FAR = 8400, FS = 200; const fg = new THREE.PlaneGeometry(FAR, FAR, FS, FS); fg.rotateX(-Math.PI / 2); const fp = fg.attributes.position, fc = new Float32Array(fp.count * 3); const cc = new THREE.Color(); let hMin = Infinity, hMax = -Infinity;
  for (let i = 0; i < fp.count; i++) { const X = fp.getX(i), Z = fp.getZ(i); let y = hAt(X, Z); const inside = Math.abs(X) < HALF - FAR / FS * 1.5 && Math.abs(Z) < HALF - FAR / FS * 1.5; if (inside) y -= 3; fp.setY(i, y); const abs = y + Hs; hMin = Math.min(hMin, abs); hMax = Math.max(hMax, abs);
    if (abs < 1 && Hs < 40) cc.set('#3d7fa6'); else if (abs > 2600 || (lat0 > 60 && abs > 900)) cc.set('#f2f4f7'); else if (abs > 1800) cc.set('#8a8478'); else if (abs > 900) cc.set('#5f6f45').lerp(new THREE.Color('#8a8478'), (abs - 900) / 900); else cc.set('#7c9050');
    fc.set([cc.r, cc.g, cc.b], i * 3); }
  fg.setAttribute('color', new THREE.BufferAttribute(fc, 3)); fg.computeVertexNormals();
  const farM = new THREE.Mesh(fg, new THREE.MeshStandardMaterial({ vertexColors: true, roughness: 1, polygonOffset: true, polygonOffsetFactor: 2, polygonOffsetUnits: 2 })); ctx.root.add(farM);
  // cer + soare real pentru ora locului (sau ora ceruta)
  const date = spec.hour !== undefined && spec.hour !== null && spec.hour !== '' ? dateAtHour(+spec.hour, lon) : new Date(); const sunL = sunDirection(lat, lon, date); sunL.az += phi; // aliniat cu rotatia scenei
  const env = addSkyAndLight(ctx, { type: 'fizic' }, sunL, { color: '#c8d6e4', near: R * 0.9, far: FAR * 0.48 }, { skyScale: 4500 }); ctx.night = env.night;
  // cladiri reale
  const walls = newBuf(), roofs = newBuf(), mw = newBuf(), mr = newBuf(); let nb = 0;
  for (const b of blds) { if (b.hide) continue; const rings = b.rings.map(r => r.map(([x, z]) => toS(x, z))); const o = rings[0]; const isT = tset.has(b);
    if (o.some(([X, Z]) => Math.abs(X) < 2.6 && Z > -1.2 && Z < 8.5) || inPoly(0, 0, o)) continue; // nu acopera Kelion sau camera
    let ymin = Infinity; for (const [X, Z] of o) ymin = Math.min(ymin, hAt(X, Z)); const y0 = (b.h0 > 0 ? ymin + b.h0 : ymin - 0.6), y1 = ymin + b.h; if (y1 <= y0) continue;
    if (isT) pushBuilding(mw, mr, rings, y0, y1, col(osmColor(b.colour) || '#d6c8ad', '#d6c8ad').offsetHSL(0, 0, rnd(-0.03, 0.03)));
    else pushBuilding(walls, roofs, rings, y0, y1, colBuilding(b.colour), b.h < 14 && Math.random() < 0.6 ? new THREE.Color('#9a5a3e').offsetHSL(0, 0, rnd(-0.06, 0.05)) : null); nb++; }
  addBuildingMeshes(ctx, walls, roofs); if (mw.pos.length) addBuildingMeshes(ctx, mw, mr, true);
  // copaci in paduri/parcuri reale (pana la 2500)
  let nt = 0; const woods = areas.filter(a => a.kind === 'wood' || a.kind === 'park'); if (woods.length) { const pts = [];
    for (const a of woods) { const bb = new THREE.Box2(); a.ring.forEach(([x, z]) => bb.expandByPoint(new THREE.Vector2(x, z))); const s = new THREE.Vector2(); bb.getSize(s); const dens = a.kind === 'wood' ? 1 / 70 : 1 / 180; const n = Math.min(600, Math.floor(s.x * s.y * dens));
      for (let i = 0; i < n * 2 && pts.length < 2500; i++) { const x = rnd(bb.min.x, bb.max.x), z = rnd(bb.min.y, bb.max.y); if (!inPoly(x, z, a.ring)) continue; const [X, Z] = toS(x, z); if (Math.hypot(X, Z) > HALF || !freeSpot(X, Z, 5)) continue; if (blds.some(b => Math.hypot(b.cx - x, b.cz - z) < 40 && inPoly(x, z, b.rings[0]))) continue; pts.push([X, Z]); } }
    const tg = new THREE.CylinderGeometry(0.18, 0.28, 1, 6); tg.translate(0, 0.5, 0); const lg = new THREE.IcosahedronGeometry(1, 1); const tr = inst(tg, new THREE.MeshStandardMaterial({ color: 0x5a3d26 }), pts.length), lf = inst(lg, new THREE.MeshStandardMaterial({ color: 0xffffff, roughness: 0.9, flatShading: true }), pts.length); const c2 = new THREE.Color();
    pts.forEach(([X, Z], i) => { const y = hAt(X, Z), h = rnd(4, 9), r = rnd(2, 3.6); M4.compose(V3.set(X, y, Z), Q.identity(), S3.set(1, h, 1)); tr.setMatrixAt(i, M4); M4.compose(V3.set(X, y + h + r * 0.4, Z), Q.identity(), S3.set(r, r * 0.9, r)); lf.setMatrixAt(i, M4); lf.setColorAt(i, c2.set(lat0 > 55 ? '#2c4f2a' : '#3f6f2c').offsetHSL(rnd(-0.03, 0.03), 0, rnd(-0.06, 0.06))); });
    ctx.root.add(tr, lf); nt = pts.length; }
  for (const e of (spec.elements || []).slice(0, 12)) { const f = ELEM[String(e.kind || '').toLowerCase()]; if (f) try { f(ctx, e); } catch (err) { console.warn('element', err); } }
  // eticheta cu numele locului
  if (spec.show_label !== false && name) { const sp = textSprite(name, 0.2); sp.position.set(1.35, 1.95, -0.6); ctx.root.add(sp); }
  ctx.extent = FAR; const relief = isFinite(hMin) ? Math.round(hMax - hMin) : 0;
  const ora = date.toISOString().slice(11, 16) + ' UTC';
  return 'spatiu REAL generat: ' + (name || (lat.toFixed(4) + ',' + lon.toFixed(4))) + (full ? ' (' + full.split(',').slice(0, 3).join(',') + ')' : '') + ' la scara 1:1 - ' + nb + ' cladiri reale, ' + roads.filter(r => r.cls !== 'waterway').length + ' segmente de strazi, ' + nt + ' copaci in parcuri/paduri, relief real ' +
    (elevNear ? 'incarcat' : 'indisponibil') + ' (diferenta de nivel ' + relief + ' m in jur), altitudinea ta ' + Math.round(Hs) + ' m; Kelion sta la ' + Math.round(pickC.d) + ' m de tinta, privind dinspre ' + (['nord', 'nord-est', 'est', 'sud-est', 'sud', 'sud-vest', 'vest', 'nord-vest'][Math.round(pickC.a / 45) % 8]) + (target ? ' (tinta, inalta de ' + Math.round(tH) + ' m, e in spatele lui' + (pickC.obs > 0 ? ', partial acoperita de alte cladiri' : ', cu vederea libera') + ')' : '') + '; soarele la ' + Math.round(sunL.alt / D2R) + ' grade (' + ora + ')' + (env.night ? ', e noapte acolo' : '') +
    (osm.ok < osm.tiles ? '; atentie: ' + (osm.tiles - osm.ok) + ' din ' + osm.tiles + ' placi de harta nu s-au incarcat' : '');
}

// ---------------------------------------------------------------- MOD GENERAT
function deepMerge(a, b) { if (Array.isArray(b)) return b.slice(); if (b && typeof b === 'object') { const o = { ...(a && typeof a === 'object' && !Array.isArray(a) ? a : {}) }; for (const k in b) o[k] = deepMerge(o[k], b[k]); return o; } return b === undefined ? a : b; }
async function generatedSpace(ctx, spec) {
  const pname = ALIAS[String(spec.preset || '').toLowerCase()] || String(spec.preset || '').toLowerCase(); const base = PRESETS[pname] || (spec.ground || spec.elements ? {} : PRESETS.campie || {});
  const P = deepMerge(base, spec); if (spec.extra_elements) P.elements = (P.elements || []).concat(spec.extra_elements);
  const sk = P.sky || { type: 'fizic', hour: 14 }; const hour = num(spec.hour, num(sk.hour, 14)); let sunL = sk.type === 'fizic' ? sunDirection(45, 0, dateAtHour(hour, 0)) : null;
  if (sunL && (sk.alt !== undefined || sk.az !== undefined) && spec.hour === undefined) sunL = { alt: num(sk.alt, 20) * D2R, az: num(sk.az, 180) * D2R }; // az 0 = soarele in fata privitorului (apus vizibil), 180 = din spatele privitorului
  ctx.waterLevel = null; if (P.water && (P.ground || {}).type !== 'nimic') ctx.waterLevel = num(P.water.level, -0.8);
  const night = sunL ? sunL.alt < -4 * D2R : false; ctx.night = night || /noapte/.test(pname);
  const G = P.ground || { type: 'teren' };
  if (G.type === 'interior') { interior(ctx, G); }
  else {
    addSkyAndLight(ctx, sk, sunL || { alt: 0.5, az: 2.4 }, P.fog || (sk.type === 'cosmos' ? null : { color: '#c8d8e6', near: 50, far: 600 }), { background: P.background, sunLight: P.sunLight, skyScale: 4000, hemiSky: P.underwater ? '#7fd0ff' : undefined, hemiGround: P.underwater ? '#16384a' : undefined });
    if (G.type === 'teren') genTerrain(ctx, G); else if (G.type === 'plat') flatGround(ctx, G); else if (G.type === 'pestera') cave(ctx, G); else { ctx.heightAt = () => -1000; }
    if (P.water) water(ctx, P.water);
    if (P.platform || G.type === 'apa' || G.type === 'nimic') { ctx.heightAt = G.type === 'teren' || G.type === 'plat' ? ctx.heightAt : () => (G.type === 'apa' ? -0.02 : -1000); platform(ctx); }
  }
  if (!ctx.heightAt) ctx.heightAt = () => 0; let made = [];
  for (const e of (P.elements || []).slice(0, 24)) { const f = ELEM[String(e.kind || '').toLowerCase()]; if (!f) { made.push('necunoscut:' + e.kind); continue; } try { const n = f(ctx, e); made.push(e.kind + ' ' + n); } catch (err) { console.warn('element', e.kind, err); made.push(e.kind + ' esuat'); } }
  if (P.label !== false && (spec.label || P.label)) { const sp = textSprite(spec.label || P.label, 0.2); sp.position.set(1.35, 1.95, -0.6); ctx.root.add(sp); }
  ctx.extent = Math.max(ctx.extent || 600, 600);
  return 'spatiu GENERAT: ' + (spec.label || P.label || pname || 'personalizat') + ' (' + (G.type || 'teren') + (G.type === 'interior' ? ' ' + num(G.width, 12) + 'x' + num(G.depth, 16) + ' m' : (sk.type ? ', cer ' + sk.type : '') + (sk.type === 'fizic' ? ', ora ' + hour : '')) + ')' + (made.length ? ' cu ' + made.join(', ') : '');
}

// ---------------------------------------------------------------- API
export async function createSpace(scene, renderer, spec = {}) {
  const root = new THREE.Group(); root.name = 'spatiu3d';
  const ctx = { scene, renderer, root, anim: [], heightAt: null, waterLevel: null, night: false, extent: 600 };
  const real = String(spec.mode || '').toLowerCase() === 'real' || (spec.mode !== 'generat' && spec.mode !== 'generated' && (spec.place || (isFinite(+spec.lat) && isFinite(+spec.lon) && spec.lat !== undefined && spec.lon !== undefined)) && !spec.preset);
  let info;
  try { info = real ? await realSpace(ctx, spec) : await generatedSpace(ctx, spec); }
  catch (e) { disposeCtx(ctx); throw e; }
  scene.add(root);
  const far = real ? 6400 : 5200; // cerul generat e la 4000 m, stelele la 3000 m
  return { root, heightAt: ctx.heightAt, info, far, real, night: ctx.night,
    update(dt) { for (const f of ctx.anim) f(dt); },
    dispose() { disposeCtx(ctx); } };
}
function disposeCtx(ctx) { const { scene, root } = ctx; scene.remove(root); if (ctx.fogSet) scene.fog = ctx.prevFog || null; if (ctx.bgSet) scene.background = ctx.prevBg || null;
  root.traverse(o => { if (o.geometry) o.geometry.dispose(); if (o.material) (Array.isArray(o.material) ? o.material : [o.material]).forEach(m => { for (const k of ['map', 'emissiveMap', 'normalMap']) if (m[k] && m[k] !== softDot()) m[k].dispose(); m.dispose(); }); }); ctx.anim.length = 0; }
export const SPATII = Object.keys(PRESETS);
export const ELEMENTE = Object.keys(ELEM);
