// node twin-feeding/tests/logic.test.js
// app/index.html 안의 LOGIC 블록만 떼어 내 검증한다 (DOM 없음).
const fs = require('fs');
const path = require('path');
const vm = require('vm');
const assert = require('assert');

process.env.TZ = 'Asia/Seoul';
const html = fs.readFileSync(path.join(__dirname, '..', 'app', 'index.html'), 'utf8');
const src = html.split('/* LOGIC START')[1].split('/* LOGIC END */')[0].replace(/^[^\n]*\n/, '');
const ctx = {};
vm.createContext(ctx);
vm.runInContext(src + '\n;Object.assign(this, {HOUR, DAY, DEFAULT_CONFIG, mergeConfig, sonNow, latestOrder, dayKey, dayOfLife, inWindow, stats24, nightGap, dailySeries, weightSlope, need, bagExpiry, inventory, allocate, tasks, flags});', ctx);
const L = ctx;
const H = L.HOUR, D = L.DAY;

let n = 0;
const test = (name, fn) => { fn(); n++; console.log('ok', name); };
const cfg = L.mergeConfig(null);
const at = (s) => new Date(s).getTime(); // 'YYYY-MM-DDTHH:MM' 로컬(KST)
const NOW = at('2026-11-17T12:00');

// 하루 8회 비우기 (3시간 간격, 밤 공백 4.75h) + 유축량
function day(base, mlEach) {
  const times = ['02:30', '05:30', '08:30', '11:30', '14:30', '17:00', '19:30', '21:45'];
  return times.map((t, i) => ({ id: base + i, type: 'session', kind: 'nurse+pump', baby: 'D', side: i % 2 ? 'R' : 'L', t: at(base + 'T' + t), end: at(base + 'T' + t) + 25 * 60e3, mlL: mlEach / 2, mlR: mlEach / 2, processed: true, by: 'mom' }));
}

test('mergeConfig keeps defaults and nested overrides', () => {
  const c = L.mergeConfig({ th: { wetMin: 5 }, sonOrderMl: 420 });
  assert.strictEqual(c.th.wetMin, 5);
  assert.strictEqual(c.th.feedsMin, 8);
  assert.strictEqual(c.sonOrderMl, 420);
  assert.strictEqual(c.birthG.D, 2630);
});

test('day of life: born 11/6 → 11/17 is day 11', () => {
  assert.strictEqual(L.dayOfLife(NOW, cfg), 11);
});

test('inWindow handles windows crossing midnight', () => {
  assert.ok(L.inWindow(at('2026-11-17T23:00'), { start: '21:45', end: '02:30' }));
  assert.ok(L.inWindow(at('2026-11-17T01:00'), { start: '21:45', end: '02:30' }));
  assert.ok(!L.inWindow(at('2026-11-17T03:00'), { start: '21:45', end: '02:30' }));
});

test('son: full need by weight, current order from latest order event', () => {
  assert.strictEqual(L.need([], cfg, 'S').ml, Math.round(2.64 * 150));
  const ev = [{ type: 'weight', baby: 'S', g: 2730, t: NOW - H }];
  assert.strictEqual(L.need(ev, cfg, 'S').ml, 410);
  assert.strictEqual(L.sonNow(ev, cfg, NOW), null);
  const o = ev.concat([{ type: 'order', baby: 'S', perFeed: 10, times: 1, ml: 10, t: at('2026-11-16T12:00') }, { type: 'order', baby: 'S', perFeed: 10, times: 8, ml: 80, t: at('2026-11-17T09:00') }]);
  assert.strictEqual(L.sonNow(o, cfg, NOW).ml, 80);
  assert.strictEqual(L.sonNow(o, cfg, at('2026-11-16T20:00')).ml, 10);
});

test('pump target follows full need, not the small current order', () => {
  const ev = [{ type: 'weight', baby: 'S', g: 2730, t: NOW - H }, { type: 'order', baby: 'S', ml: 10, perFeed: 10, times: 1, t: NOW - 2 * H }];
  const st = L.stats24(ev, NOW, cfg);
  assert.strictEqual(st.pumpTarget, Math.round(410 * 1.2));
  assert.strictEqual(st.sNow.ml, 10);
});

test('stats24: removals, night removal, longest gap, pumped', () => {
  const ev = day('2026-11-16', 60).concat(day('2026-11-17', 60).filter(e => e.t <= NOW));
  const st = L.stats24(ev, NOW, cfg);
  assert.strictEqual(st.removals, 8); // 11/16 14:30 이후 4회 + 11/17 4회
  assert.ok(st.night);
  assert.strictEqual(Math.round(st.longestGap / 60e3), 4 * 60 + 45);
  assert.strictEqual(st.pumped, 480);
  assert.ok(st.full);
});

test('nightGap: gap ending in the morning of a given day', () => {
  const ev = day('2026-11-16', 60).concat(day('2026-11-17', 60));
  assert.strictEqual(Math.round(L.nightGap(ev, '2026-11-17') / 60e3), 285);
});

test('bag expiry: NICU fridge 48h vs home fridge 96h, freezer 180d', () => {
  const t = at('2026-11-17T08:00');
  assert.strictEqual(L.bagExpiry({ state: 'fridge', for: 'S', pumpedAt: t }, cfg), t + 48 * H);
  assert.strictEqual(L.bagExpiry({ state: 'fridge', for: 'any', pumpedAt: t }, cfg), t + 96 * H);
  assert.strictEqual(L.bagExpiry({ state: 'freezer', for: 'S', pumpedAt: t }, cfg), t + 180 * D);
  assert.strictEqual(L.bagExpiry({ state: 'nicu', pumpedAt: t }, cfg), null);
});

test('allocate rule 3: pumped below current NICU order → formula even with stock', () => {
  const ev = day('2026-11-16', 40).concat(day('2026-11-17', 40).filter(e => e.t <= NOW)); // 320ml
  ev.push({ type: 'order', baby: 'S', ml: 360, perFeed: 45, times: 8, t: NOW - 3 * H });
  const bags = { a: { id: 'a', code: 'x', ml: 2000, pumpedAt: NOW - 2 * D, for: 'S', state: 'freezer' } };
  const a = L.allocate(bags, ev, cfg, NOW, 60);
  assert.strictEqual(a.milk, 'formula');
  assert.strictEqual(a.rule, 3);
});

test('no order recorded → rule 3 never fires', () => {
  const ev = day('2026-11-16', 10).concat(day('2026-11-17', 10).filter(e => e.t <= NOW));
  assert.ok(!L.tasks(ev, {}, cfg, NOW).some(t => t.kind === 'deficit'));
});

test('early milk (before day 14) stays with son even when surplus exists', () => {
  const bags = { z: { id: 'z', code: 'early', ml: 2000, pumpedAt: NOW - 3 * D, for: 'S', state: 'freezer' } };
  const a = L.allocate(bags, [], cfg, NOW, 60);
  assert.strictEqual(a.milk, 'formula');
  assert.ok(/초기 모유/.test(a.reason));
});

test('allocate rule 2: surplus beyond reserve → EBM, newest non-early bag first', () => {
  const N2 = at('2026-11-25T12:00');
  const bags = {
    e1: { id: 'e1', code: 'early', ml: 800, pumpedAt: at('2026-11-15T08:00'), for: 'S', state: 'freezer' },
    f1: { id: 'f1', code: 'old', ml: 100, pumpedAt: N2 - 30 * H, for: 'S', state: 'fridge' },
    f2: { id: 'f2', code: 'new', ml: 100, pumpedAt: N2 - 2 * H, for: 'S', state: 'fridge' },
    z1: { id: 'z1', code: 'frz', ml: 300, pumpedAt: N2 - 3 * D, for: 'S', state: 'freezer' },
  };
  const a = L.allocate(bags, [], cfg, N2, 60); // total 1300, reserve 792
  assert.strictEqual(a.milk, 'ebm');
  assert.strictEqual(a.bag.id, 'f2');
  assert.strictEqual(a.inv.reserve, 792);
});

test('allocate rule 2: no surplus → formula', () => {
  const bags = { f1: { id: 'f1', code: 'a', ml: 500, pumpedAt: NOW - H, for: 'S', state: 'fridge' } };
  assert.strictEqual(L.allocate(bags, [], cfg, NOW, 60).milk, 'formula');
});

test('expired bags are excluded from inventory and surfaced as tasks', () => {
  const bags = { old: { id: 'old', code: 'o', ml: 80, pumpedAt: NOW - 50 * H, for: 'S', state: 'fridge' } };
  const inv = L.inventory(bags, [], cfg, NOW);
  assert.strictEqual(inv.total, 0);
  assert.ok(L.tasks([], bags, cfg, NOW).some(t => t.kind === 'expired'));
});

test('tasks: unprocessed pump session and parts washing', () => {
  const ev = [{ id: 's1', type: 'session', kind: 'pump', t: NOW - 2 * H, end: NOW - 100 * 60e3, by: 'mom' }];
  const tk = L.tasks(ev, {}, cfg, NOW);
  const p = tk.find(t => t.kind === 'process');
  assert.ok(p && !p.overdue);
  assert.ok(tk.some(t => t.kind === 'wash' && t.n === 1));
  const tk2 = L.tasks(ev.concat([{ type: 'wash', t: NOW - 60e3 }]), {}, cfg, NOW);
  assert.ok(!tk2.some(t => t.kind === 'wash'));
});

test('flags: low wet diapers only after a full day of logging', () => {
  const ev = day('2026-11-16', 70).concat(day('2026-11-17', 70).filter(e => e.t <= NOW));
  const f = L.flags(ev, cfg, NOW);
  assert.ok(f.some(x => x.level === 'today' && /소변/.test(x.text)));
  const f2 = L.flags(day('2026-11-17', 70).filter(e => e.t <= NOW), cfg, NOW);
  assert.ok(!f2.some(x => /소변/.test(x.text)));
});

test('flags: EPDS item 10 is immediate regardless of total', () => {
  const ev = [{ type: 'momcheck', t: NOW - H, epds: 4, epds10: 1 }];
  const f = L.flags(ev, cfg, NOW);
  assert.strictEqual(f[0].level, 'now');
});

test('weightSlope: ~30 g/day over 7 days', () => {
  const ev = [0, 2, 4, 6].map(i => ({ type: 'weight', baby: 'D', g: 2600 + 30 * i, t: NOW - (6 - i) * D }));
  assert.strictEqual(Math.round(L.weightSlope(ev, 'D', NOW, 7)), 30);
  assert.strictEqual(L.weightSlope(ev.slice(0, 1), 'D', NOW, 7), null);
});

test('dailySeries counts per calendar day and taps per role', () => {
  const ev = day('2026-11-16', 60).map(e => Object.assign({}, e, { endBy: 'mom' }));
  const ser = L.dailySeries(ev, cfg, NOW, 3);
  const d16 = ser.find(x => x.key === '2026-11-16');
  assert.strictEqual(d16.removals, 8);
  assert.strictEqual(d16.pumped, 480);
  assert.strictEqual(d16.momTaps, 16);
});

test('nurse-only session: counts as removal and daughter feed, not pumped, no processing task', () => {
  const ev = [{ id: 'n1', type: 'session', kind: 'nurse', baby: 'D', side: 'L', t: NOW - H, end: NOW - 40 * 60e3, by: 'mom' }];
  const st = L.stats24(ev, NOW, cfg);
  assert.strictEqual(st.removals, 1);
  assert.strictEqual(st.dFeeds, 1);
  assert.strictEqual(st.pumped, 0);
  const tk = L.tasks(ev, {}, cfg, NOW);
  assert.ok(!tk.some(t => t.kind === 'process' || t.kind === 'wash'));
});

console.log('\n' + n + ' tests passed');
