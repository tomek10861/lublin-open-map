// Lublin Open Map viewer: loads the exported glTF tiles around the camera target.
// URL: viewer/?data=../dist#preset   or   #x,y,dist,yaw,pitch  (local metres, degrees)
import * as THREE from 'three';
import { GLTFLoader } from 'three/addons/loaders/GLTFLoader.js';
import { MapControls } from 'three/addons/controls/MapControls.js';

const params = new URLSearchParams(location.search);
const DATA = (params.get('data') || '../dist').replace(/\/$/, '');
if (params.has('clean')) document.body.classList.add('clean');
const RADIUS = Number(params.get('radius') || 900);

const renderer = new THREE.WebGLRenderer({ antialias: true, preserveDrawingBuffer: true });
renderer.setPixelRatio(Math.min(devicePixelRatio, 2));
renderer.setSize(innerWidth, innerHeight);
renderer.outputColorSpace = THREE.SRGBColorSpace;
document.body.appendChild(renderer.domElement);

const scene = new THREE.Scene();
const sky = new THREE.Color('#9fb7cc');
scene.background = sky;
scene.fog = new THREE.Fog(sky, 900, 2600);
scene.add(new THREE.HemisphereLight('#dfe9f3', '#6b6255', 1.6));
const sun = new THREE.DirectionalLight('#fff4e0', 1.8);
sun.position.set(-300, 600, 200);
scene.add(sun);

const persp = new THREE.PerspectiveCamera(55, innerWidth / innerHeight, 1, 6000);
let camera = persp;
const controls = new MapControls(persp, renderer.domElement);
controls.maxPolarAngle = Math.PI * 0.49;
controls.addEventListener('change', () => { schedule(); });

// local (x east, y north, z up) <-> glTF/three (x, y up, z south)
const toGL = (x, y, z = 0) => new THREE.Vector3(x, z, -y);

const loader = new GLTFLoader();
const loaded = new Map();   // file -> Promise<Object3D>
let manifest, routes, presets = {};
const status = document.getElementById('status');

function bboxOfCell(c, m) { const s = m.coordinates.cellM; return [c[0] * s, c[1] * s, (c[0] + 1) * s, (c[1] + 1) * s]; }
function dist2(b, x, y) { const dx = Math.max(b[0] - x, 0, x - b[2]), dy = Math.max(b[1] - y, 0, y - b[3]); return dx * dx + dy * dy; }

function load(file, group) {
  if (!loaded.has(file)) {
    loaded.set(file, loader.loadAsync(`${DATA}/${file}`).then(g => {
      g.scene.traverse(o => { if (o.isMesh) { o.matrixAutoUpdate = false; o.updateMatrix(); } });
      g.scene.userData.group = group; scene.add(g.scene); return g.scene;
    }).catch(e => { console.warn('tile failed', file, e); return null; }));
  }
  return loaded.get(file);
}

function wanted(x, y, r) {
  const out = [];
  for (const c of manifest.city) if (dist2(bboxOfCell(c.cell, manifest), x, y) < r * r) out.push([c.file, 'city']);
  if (document.getElementById('photo').checked)
    for (const p of manifest.photo) if (dist2(p.bboxLocal, x, y) < (r * 0.8) ** 2) out.push([p.file, 'photo']);
  return out;
}

function target() { const t = controls.target; return [t.x, -t.z]; }

let timer;
function schedule() { clearTimeout(timer); timer = setTimeout(() => refresh(), 250); }
async function refresh(r = RADIUS) {
  const [x, y] = target(); const list = wanted(x, y, r);
  status.textContent = `Kafle: ${list.length}`;
  await Promise.all(list.map(([f, g]) => load(f, g)));
  for (const [f, p] of loaded) p.then(o => { if (o && o.userData.group === 'photo') o.visible = document.getElementById('photo').checked; });
  status.textContent = `Gotowe · kafle w pamięci: ${loaded.size}`;
}

function groundAt(x, y) {
  const rc = new THREE.Raycaster(toGL(x, y, 400), new THREE.Vector3(0, -1, 0), 0, 1000);
  const hits = rc.intersectObjects(scene.children, true).filter(h => h.object.isMesh);
  return hits.length ? hits[hits.length - 1].point.y : 30;
}

// Camera from a target, distance, yaw (0 = looking north, clockwise) and pitch (degrees above horizon).
async function goto({ x, y, dist = 300, yaw = 0, pitch = 30, top = false, radius }) {
  if (arguments[0].photo !== undefined) document.getElementById('photo').checked = arguments[0].photo;
  controls.target.copy(toGL(x, y, 30)); controls.update();
  await refresh(radius || Math.max(RADIUS, dist * 1.4));
  const gz = groundAt(x, y);
  const tgt = toGL(x, y, gz + 2);
  const yr = THREE.MathUtils.degToRad(yaw), pr = THREE.MathUtils.degToRad(top ? 89.9 : pitch);
  const back = new THREE.Vector3(-Math.sin(yr) * Math.cos(pr), Math.sin(pr), Math.cos(yr) * Math.cos(pr));
  persp.position.copy(tgt).addScaledVector(back, dist);
  persp.far = Math.max(6000, dist * 4); persp.updateProjectionMatrix();
  scene.fog.near = top ? 1e5 : Math.max(900, dist); scene.fog.far = top ? 2e5 : Math.max(2600, dist * 4);
  controls.target.copy(tgt); controls.update();
  if (routes || arguments[0].routes) await showRoutes(!!arguments[0].routes);
  await new Promise(r => requestAnimationFrame(() => requestAnimationFrame(r)));
}

async function showRoutes(on) {
  if (!routes) {
    const fc = await (await fetch(`${DATA}/layers/races.geojson`)).json();
    const [ox, oy] = manifest.coordinates.originEPSG2180; routes = new THREE.Group();
    const colors = ['#ff4d2e', '#ffd21f', '#2ec4ff', '#b05cff'];
    // WebGL draws 1 px lines only: build flat ribbons instead (width in metres).
    const W = Number(params.get('routeWidth') || 14);
    fc.features.forEach((f, i) => {
      const P = f.geometry.coordinates.map(([e, n]) => [e - ox, n - oy]);
      const pos = [], idx = [];
      P.forEach(([x, y], k) => {
        const [ax, ay] = P[Math.max(0, k - 1)], [bx, by] = P[Math.min(P.length - 1, k + 1)];
        let dx = bx - ax, dy = by - ay; const l = Math.hypot(dx, dy) || 1; dx /= l; dy /= l;
        const z = groundAt(x, y) + 4 + i * 0.5;
        for (const s of [-1, 1]) { const v = toGL(x - dy * s * W / 2, y + dx * s * W / 2, z); pos.push(v.x, v.y, v.z); }
        if (k) { const o = 2 * k; idx.push(o - 2, o - 1, o, o - 1, o + 1, o); }
      });
      const geo = new THREE.BufferGeometry(); geo.setAttribute('position', new THREE.Float32BufferAttribute(pos, 3)); geo.setIndex(idx);
      const mesh = new THREE.Mesh(geo, new THREE.MeshBasicMaterial({ color: colors[i % colors.length], side: THREE.DoubleSide, depthTest: false, transparent: true, opacity: .9 }));
      mesh.renderOrder = 10; mesh.name = f.properties.name; routes.add(mesh);
    });
    routes.renderOrder = 10; scene.add(routes);
  }
  routes.visible = on;
}

function fromHash() {
  const h = decodeURIComponent(location.hash.slice(1));
  if (presets[h]) return presets[h];
  const v = h.split(',').map(Number);
  if (v.length >= 2 && v.every(Number.isFinite)) return { x: v[0], y: v[1], dist: v[2] ?? 300, yaw: v[3] ?? 0, pitch: v[4] ?? 30 };
  return presets[Object.keys(presets)[0]];
}

async function init() {
  manifest = await (await fetch(`${DATA}/manifest.json`)).json();
  presets = await (await fetch('presets.json')).json().catch(() => ({}));
  const sel = document.getElementById('preset');
  for (const [k, p] of Object.entries(presets)) sel.add(new Option(p.label || k, k));
  sel.onchange = () => { location.hash = sel.value; };
  document.getElementById('photo').onchange = () => refresh();
  document.getElementById('routes').onchange = e => showRoutes(e.target.checked);
  window.addEventListener('hashchange', () => goto(fromHash()));
  window.addEventListener('resize', () => { persp.aspect = innerWidth / innerHeight; persp.updateProjectionMatrix(); renderer.setSize(innerWidth, innerHeight); });
  renderer.setAnimationLoop(() => { controls.update(); renderer.render(scene, camera); });
  const start = fromHash();
  if (params.has('routes')) { document.getElementById('routes').checked = true; }
  if (start) { sel.value = Object.keys(presets).find(k => presets[k] === start) || ''; await goto(start); }
  if (params.has('routes')) await showRoutes(true);
  window.__viewerReady = true;
}

window.viewer = { goto, showRoutes, refresh };
init();
