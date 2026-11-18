// node twin-feeding/tests/gas.test.js
// Code.gs(Apps Script 서버)를 구글 서비스 흉내 환경에서 실행해 단축어 동작·동시 수정 방지를 검증한다.
const fs = require('fs'), path = require('path'), vm = require('vm'), assert = require('assert');
process.env.TZ = 'Asia/Seoul';

function makeEnv() {
  const sheets = {};
  const props = {};
  const mkSheet = name => {
    const sh = { name, rows: [] };
    const range = (r, c, nr, nc) => ({
      getValues: () => Array.from({ length: nr }, (_, i) => Array.from({ length: nc }, (_, j) => ((sh.rows[r - 1 + i] || [])[c - 1 + j] ?? ''))),
      setValues: v => v.forEach((row, i) => { sh.rows[r - 1 + i] = sh.rows[r - 1 + i] || []; row.forEach((x, j) => { sh.rows[r - 1 + i][c - 1 + j] = x; }); }),
      getValue: () => ((sh.rows[r - 1] || [])[c - 1] ?? ''),
      setNumberFormat() { return this; },
      createTextFinder: text => ({ matchEntireCell() { return this; }, findNext: () => { const i = sh.rows.findIndex(row => String(row[0]) === String(text)); return i >= 0 ? { getRow: () => i + 1 } : null; } }),
    });
    Object.assign(sh, {
      getLastRow: () => sh.rows.length,
      getRange: (a, b, c, d) => typeof a === 'string' ? range(1, 1, sh.rows.length, 1) : range(a, b, c || 1, d || 1),
      appendRow: v => { sh.rows.push(v.slice()); },
      setFrozenRows() {},
    });
    return sh;
  };
  const ss = { getSheetByName: n => sheets[n] || null, insertSheet: n => (sheets[n] = mkSheet(n)), getUrl: () => 'https://docs.google.com/spreadsheets/d/TEST' };
  const g = {
    SpreadsheetApp: { openById: () => ss },
    PropertiesService: { getScriptProperties: () => ({ getProperty: k => props[k] ?? null, setProperty: (k, v) => { props[k] = String(v); } }) },
    LockService: { getScriptLock: () => ({ waitLock() {}, releaseLock() {} }) },
    Utilities: { getUuid: () => 'abcd1234-ef56-7890-abcd-1234567890ab', formatDate: (d) => d.toISOString().slice(0, 16).replace('T', ' ') },
    ContentService: { createTextOutput: s => ({ text: s }) },
    HtmlService: { createHtmlOutputFromFile: () => ({ getContent: () => '<p>__TOKEN__</p>' }), createHtmlOutput: h => ({ html: h, setTitle() { return this; }, addMetaTag() { return this; } }) },
    ScriptApp: { getService: () => ({ getUrl: () => 'https://script.google.com/macros/s/TEST/exec' }) },
    Logger: { log() {} },
    console,
  };
  const ctx = vm.createContext(g);
  vm.runInContext(fs.readFileSync(path.join(__dirname, '..', 'stage1', 'gas', 'Code.gs'), 'utf8') + '\n' + fs.readFileSync(path.join(__dirname, '..', 'stage1', 'gas', 'Migrate.gs'), 'utf8') + '\n;this.__x = { migrate, setup, doGet, act_, api_getAll, api_setBag, api_updateBag, api_getBag, api_addEvent, api_patchEvent, readEvents_, cryRank_ };', ctx);
  return { x: ctx.__x, sheets, props };
}

let n = 0;
const test = (name, fn) => { fn(); n++; console.log('ok', name); };
const at = s => new Date(s).getTime();
const T0 = at('2026-11-18T02:30');

const env = makeEnv(); const X = env.x;
X.setup();
const K = env.props.TOKEN;
const act = (q, t) => X.act_(Object.assign({ by: 'mom', src: 'siri' }, q), t);

test('setup makes sheets and a token', () => {
  assert.ok(env.sheets.events && env.sheets.bags && env.sheets.config);
  assert.strictEqual(K.length, 24);
});
test('wrong token is refused; page gets the token injected', () => {
  assert.strictEqual(X.doGet({ parameter: { k: 'nope', a: 'diaper' } }).text, '주소가 올바르지 않아요.');
  assert.strictEqual(X.doGet({ parameter: { k: K } }).html, '<p>' + K + '</p>');
});
test('action button toggles: start (default 직수+유축, 왼쪽) → end → next start on the other side', () => {
  assert.strictEqual(act({ a: 'feed' }, T0), '왼쪽 직수 유축 시작했어요.');
  assert.strictEqual(act({ a: 'feed' }, T0 + 22 * 60e3), '직수 유축 끝. 22분이에요.');
  assert.strictEqual(act({ a: 'feed' }, T0 + 3 * 3600e3), '오른쪽 직수 유축 시작했어요.');
  assert.strictEqual(act({ a: 'end' }, T0 + 3 * 3600e3 + 15 * 60e3), '직수 유축 끝. 15분이에요.');
});
test('start with spoken kind and side; starting while one is open ends it first', () => {
  assert.strictEqual(act({ a: 'start', kind: '직수', side: '오른쪽' }, T0 + 5 * 3600e3), '오른쪽 직수 시작했어요.');
  assert.strictEqual(act({ a: 'start', kind: 'pump' }, T0 + 5 * 3600e3 + 20 * 60e3), '앞 기록을 끝내고 양쪽 유축 시작했어요.');
  assert.strictEqual(act({ a: 'end' }, T0 + 5 * 3600e3 + 40 * 60e3), '유축 끝. 20분이에요.');
  assert.strictEqual(act({ a: 'end' }, T0 + 6 * 3600e3), '진행 중인 수유가 없어요.');
});
test('diaper, bottle with spoken amount, status', () => {
  assert.strictEqual(act({ a: 'diaper', wet: '1' }, T0 + 6 * 3600e3), '기저귀 소변 기록했어요.');
  assert.strictEqual(act({ a: 'bottle', ml: '60밀리', milk: '분유', by: 'dad' }, T0 + 6.5 * 3600e3), '젖병 분유 60밀리 기록했어요.');
  assert.strictEqual(act({ a: 'bottle', ml: '많이' }, T0 + 6.5 * 3600e3), '양을 숫자로 말해 주세요.');
  const s = act({ a: 'status' }, T0 + 7 * 3600e3);
  assert.ok(/마지막 수유 30분 전/.test(s) && /다음은 왼쪽/.test(s), s);
});
test('undo removes my last record within 15 minutes, not my partner\'s', () => {
  act({ a: 'diaper', stool: '1' }, T0 + 7 * 3600e3);
  assert.strictEqual(act({ a: 'undo' }, T0 + 7 * 3600e3 + 60e3), '방금 기저귀 대변 기록을 취소했어요.');
  const evs = X.readEvents_();
  assert.ok(evs.find(e => e.type === 'diaper' && e.stool).deleted);
  assert.ok(!evs.find(e => e.type === 'bottle').deleted);
});
test('undo right after ending a feed reopens it', () => {
  act({ a: 'feed' }, T0 + 8 * 3600e3);
  act({ a: 'feed' }, T0 + 8 * 3600e3 + 10 * 60e3);
  assert.ok(/끝낸 걸 되돌렸어요/.test(act({ a: 'undo' }, T0 + 8 * 3600e3 + 11 * 60e3)));
  assert.strictEqual(act({ a: 'end' }, T0 + 8 * 3600e3 + 20 * 60e3), '직수 유축 끝. 20분이에요.');
});
test('cry ranking: long since feed → hunger first; recent feed & old diaper → diaper first', () => {
  const H = 3600e3;
  const base = at('2026-11-19T10:00');
  const evs1 = [{ type: 'session', kind: 'nurse', side: 'L', t: base - 3.2 * H, end: base - 3 * H }, { type: 'diaper', wet: true, t: base - 40 * 60e3 }];
  assert.strictEqual(X.cryRank_(evs1, base)[0].k, 'feed');
  const evs2 = [{ type: 'session', kind: 'nurse', side: 'L', t: base - 50 * 60e3, end: base - 30 * 60e3 }, { type: 'diaper', wet: true, t: base - 4 * H }];
  assert.strictEqual(X.cryRank_(evs2, base)[0].k, 'diaper');
  const r = act({ a: 'cry' }, T0 + 10 * 3600e3);
  assert.ok(/배고플 수 있어요|기저귀일 수 있어요/.test(r), r);
  assert.strictEqual(act({ a: 'calm', how: '먹였어' }, T0 + 10 * 3600e3 + 5 * 60e3), '먹여서 그친 걸 기록했어요.');
});
test('sleep toggle', () => {
  assert.strictEqual(act({ a: 'sleep' }, T0 + 11 * 3600e3), '잠들었어요.');
  assert.strictEqual(act({ a: 'sleep' }, T0 + 12.5 * 3600e3), '깼어요. 1시간 30분 잤어요.');
});
test('bag updates are refused when the version moved (another phone changed it)', () => {
  X.api_setBag(K, { id: 'b1', code: '1118-0230', ml: 100, state: 'freezer', for: 'S', pumpedAt: T0 });
  const g = X.api_getBag(K, 'b1');
  assert.strictEqual(X.api_updateBag(K, 'b1', { ml: 70, used: { e1: 30 } }, g.version), 'ok');
  assert.strictEqual(X.api_updateBag(K, 'b1', { ml: 40, used: { e2: 30 } }, g.version), 'busy');
  const g2 = X.api_getBag(K, 'b1');
  assert.strictEqual(X.api_updateBag(K, 'b1', { ml: 40, used: { e2: 30 } }, g2.version), 'ok');
  const b = X.api_getBag(K, 'b1').bag;
  assert.strictEqual(JSON.stringify([b.ml, b.used]), JSON.stringify([40, { e1: 30, e2: 30 }]));
});
test('page API refuses a wrong token', () => {
  assert.throws(() => X.api_getAll('nope'));
  const all = X.api_getAll(K);
  assert.ok(all.events.length > 5 && all.bags.b1 && all.execUrl);
});

test('migrate brings the 13 artifact records once; deleted ones stay hidden', () => {
  const e2 = makeEnv(); e2.x.setup(); e2.x.migrate(); e2.x.migrate();
  const all = e2.x.readEvents_();
  assert.strictEqual(all.length, 13);
  assert.strictEqual(all.filter(e => !e.deleted).length, 7);
  const tok = e2.props.TOKEN;
  assert.strictEqual(JSON.parse(JSON.stringify(e2.x.api_getAll(tok).config)).birthG.D, 2630);
});
test('two phones hearing the same cry within 5 minutes make one record', () => {
  const before = X.readEvents_().filter(e => e.type === 'cry').length;
  act({ a: 'cry' }, T0 + 13 * 3600e3); act({ a: 'cry', by: 'dad' }, T0 + 13 * 3600e3 + 60e3);
  assert.strictEqual(X.readEvents_().filter(e => e.type === 'cry').length, before + 1);
});

console.log('\n' + n + ' tests passed');
