// node twin-feeding/tests/gas.test.js
// Code.gs(Apps Script 서버)를 구글 서비스 흉내 환경에서 실행해 단축어 동작·동시 수정 방지를 검증한다.
const fs = require('fs'), path = require('path'), vm = require('vm'), assert = require('assert');
process.env.TZ = 'Asia/Seoul';

function makeEnv() {
  const sheets = {};
  const props = {};
  const sent = [], triggers = [];
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
    Utilities: { getUuid: () => 'abcd1234-ef56-7890-abcd-1234567890ab', formatDate: (d, tz, f) => f === 'H' ? String(d.getHours()) : f === 'HH:mm' ? String(d.getHours()).padStart(2, '0') + ':' + String(d.getMinutes()).padStart(2, '0') : d.toISOString().slice(0, 16).replace('T', ' ') },
    UrlFetchApp: { fetch: (url, o) => { sent.push(Object.assign({ url }, JSON.parse(o.payload))); return { getResponseCode: () => 200 }; } },
    ContentService: { createTextOutput: s => ({ text: s, setMimeType(m) { this.mime = m; return this; } }), MimeType: { JSON: 'json' } },
    HtmlService: { createHtmlOutputFromFile: () => ({ getContent: () => '<p>__TOKEN__</p>' }), createHtmlOutput: h => ({ html: h, setTitle() { return this; }, addMetaTag() { return this; } }) },
    ScriptApp: { getService: () => ({ getUrl: () => 'https://script.google.com/macros/s/TEST/exec' }), getProjectTriggers: () => triggers,
      newTrigger: h => ({ timeBased() { return this; }, everyMinutes(m) { this.m = m; return this; }, create() { triggers.push({ getHandlerFunction: () => h, m: this.m }); } }) },
    Logger: { log() {} },
    console,
  };
  const ctx = vm.createContext(g);
  vm.runInContext(fs.readFileSync(path.join(__dirname, '..', 'stage1', 'gas', 'Code.gs'), 'utf8') + '\n' + fs.readFileSync(path.join(__dirname, '..', 'stage1', 'gas', 'Migrate.gs'), 'utf8') + '\n;this.__x = { migrate, setup, doGet, act_, api_getAll, api_setBag, api_updateBag, api_getBag, api_addEvent, api_patchEvent, readEvents_, cryRank_, checkAlerts, widget_, flush_, outbox: OUTBOX_ };', ctx);
  return { x: ctx.__x, sheets, props, sent, triggers, ctx };
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
  assert.ok(act({ a: 'feed' }, T0 + 22 * 60e3).startsWith('직수 유축 끝. 22분이에요.'), '직수 유축 끝. 22분이에요.');
  assert.strictEqual(act({ a: 'feed' }, T0 + 3 * 3600e3), '오른쪽 직수 유축 시작했어요.');
  assert.ok(act({ a: 'end' }, T0 + 3 * 3600e3 + 15 * 60e3).startsWith('직수 유축 끝. 15분이에요.'), '직수 유축 끝. 15분이에요.');
});
test('start with spoken kind and side; starting while one is open ends it first', () => {
  assert.strictEqual(act({ a: 'start', kind: '직수', side: '오른쪽' }, T0 + 5 * 3600e3), '오른쪽 직수 시작했어요.');
  assert.strictEqual(act({ a: 'start', kind: 'pump' }, T0 + 5 * 3600e3 + 20 * 60e3), '앞 기록을 끝내고 양쪽 유축 시작했어요.');
  assert.ok(act({ a: 'end' }, T0 + 5 * 3600e3 + 40 * 60e3).startsWith('유축 끝. 20분이에요.'), '유축 끝. 20분이에요.');
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
  assert.ok(act({ a: 'end' }, T0 + 8 * 3600e3 + 20 * 60e3).startsWith('직수 유축 끝. 20분이에요.'), '직수 유축 끝. 20분이에요.');
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
  assert.strictEqual(act({ a: 'sleep' }, T0 + 11 * 3600e3), '잠들었어요. 등 대고, 자기 잠자리에 아기만 있는지 봐 주세요.');
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

test('migrate brings the 16 artifact records once; deleted ones stay hidden', () => {
  const e2 = makeEnv(); e2.x.setup(); e2.x.migrate(); e2.x.migrate();
  const all = e2.x.readEvents_();
  assert.strictEqual(all.length, 16);
  assert.strictEqual(all.filter(e => !e.deleted).length, 9);
  const tok = e2.props.TOKEN;
  assert.strictEqual(JSON.parse(JSON.stringify(e2.x.api_getAll(tok).config)).birthG.D, 2630);
});
test('two phones hearing the same cry within 5 minutes make one record', () => {
  const before = X.readEvents_().filter(e => e.type === 'cry').length;
  act({ a: 'cry' }, T0 + 13 * 3600e3); act({ a: 'cry', by: 'dad' }, T0 + 13 * 3600e3 + 60e3);
  assert.strictEqual(X.readEvents_().filter(e => e.type === 'cry').length, before + 1);
});

test('switching sides mid-feed: split is spoken, and next start suggests the less-fed side', () => {
  const B = T0 + 20 * 3600e3;
  assert.strictEqual(act({ a: 'start', kind: 'nurse', side: 'L' }, B), '왼쪽 직수 시작했어요.');
  assert.strictEqual(act({ a: 'switch' }, B + 5 * 60e3), '오른쪽으로 바꿨어요.');
  assert.ok(act({ a: 'end' }, B + 7 * 60e3).startsWith('직수 끝. 7분이에요. 왼쪽 5, 오른쪽 2분.'), '직수 끝. 7분이에요. 왼쪽 5, 오른쪽 2분.');
  // 왼 5, 오 2 → 다음은 덜 먹인 오른쪽
  assert.strictEqual(act({ a: 'start', kind: 'nurse' }, B + 60 * 60e3), '오른쪽 직수 시작했어요.');
  assert.ok(act({ a: 'end' }, B + 68 * 60e3).startsWith('직수 끝. 8분이에요.'), '직수 끝. 8분이에요.');
  // 한쪽만 먹였으면 반대쪽
  assert.strictEqual(act({ a: 'start', kind: 'nurse' }, B + 120 * 60e3), '왼쪽 직수 시작했어요.');
  assert.strictEqual(act({ a: 'switch' }, B + 121 * 60e3) !== '바꿀 직수가 없어요.', true);
  act({ a: 'end' }, B + 130 * 60e3);
  assert.strictEqual(act({ a: 'switch' }, B + 131 * 60e3), '바꿀 직수가 없어요.');
});

test('night safety: ending a night feed adds the safe-sleep line; long feeds get a stronger line; sleep start reminds', () => {
  const N = at('2026-11-21T02:00');
  act({ a: 'start', kind: 'nurse', side: 'L' }, N);
  assert.ok(/등 대고, 아기 침대로\.$/.test(act({ a: 'end' }, N + 10 * 60e3)));
  act({ a: 'start', kind: 'nurse', side: 'R' }, N + 60 * 60e3);
  assert.ok(/오래 안고 있었어요/.test(act({ a: 'end' }, N + 100 * 60e3)));
  const D0 = at('2026-11-21T14:00');
  act({ a: 'start', kind: 'nurse', side: 'L' }, D0);
  assert.ok(!/침대/.test(act({ a: 'end' }, D0 + 10 * 60e3)));     // 낮에는 말하지 않음
  assert.ok(/등 대고/.test(act({ a: 'sleep' }, D0 + 20 * 60e3)));
  act({ a: 'sleep' }, D0 + 80 * 60e3);
});
test('crying 20+ minutes: the reply switches to the check-order and safe-break plan; break is logged', () => {
  const C = at('2026-11-22T03:00');
  act({ a: 'cry' }, C); act({ a: 'cry' }, C + 9 * 60e3);
  const r = act({ a: 'cry' }, C + 22 * 60e3);
  assert.ok(/22분째 울고 있어요/.test(r) && /흔들지는 마세요/.test(r) && /38도/.test(r), r);
  assert.ok(/10분 뒤에 다시 보러 가요/.test(act({ a: 'break' }, C + 23 * 60e3)));
  act({ a: 'calm', how: 'feed' }, C + 30 * 60e3);
  assert.ok(!/분째 울고/.test(act({ a: 'cry' }, C + 40 * 60e3)));  // 그친 뒤 새 울음은 처음부터
});
test('care schedule by voice lists what is due within a week; hospital items are one "check" line, like the app', () => {
  const r = act({ a: 'care' }, at('2026-11-21T10:00'));
  assert.ok(/영유아건강검진 1차 12월 11일까지/.test(r) && /BCG/.test(r), r);
  assert.ok(!/청각선별검사 12월/.test(r) && /출산 병원에서 하는 검사·접종 3개는 퇴원요약지로 확인/.test(r), r);
});
test('undo speaks Korean names for every record type (no raw "break")', () => {
  act({ a: 'break' }, at('2026-11-24T15:00'));
  assert.strictEqual(act({ a: 'undo' }, at('2026-11-24T15:01')), '방금 울음 중 잠시 쉬기 기록을 취소했어요.');
});
test('a cry episode never reaches back more than 3 hours (same rule as the app)', () => {
  const C = at('2026-11-25T10:00');
  for (let i = 0; i <= 8; i++) act({ a: 'cry' }, C + i * 25 * 60e3);   // 25분마다 울음 3시간 20분
  const r = act({ a: 'cry' }, C + 200 * 60e3 + 60e3);
  const m = Number((r.match(/^(\d+)분째/) || [])[1]);
  assert.ok(m > 0 && m <= 180, r);
  act({ a: 'calm', how: 'feed' }, C + 202 * 60e3);
});


/* ---------- 잠금화면 알림(ntfy)·위젯 ---------- */
{
  const E = makeEnv(), Y = E.x; Y.setup(); Y.setup();
  const go = (q, t) => { Y.outbox.length = 0; const r = Y.act_(Object.assign({ by: 'mom', src: 'siri' }, q), t); Y.flush_(t); return r; };
  const last = () => E.sent[E.sent.length - 1];
  const base = E.props.NTFY;
  test('setup makes one alert channel and one 5-minute check, even when run twice', () => {
    assert.ok(/^tf-[0-9a-f]{16}$/.test(base), base);
    assert.strictEqual(E.triggers.length, 1); assert.strictEqual(E.triggers[0].m, 5);
    assert.strictEqual(JSON.stringify(Y.api_getAll(E.props.TOKEN).ntfy), JSON.stringify({ server: 'https://ntfy.sh', mom: base + '-mom', dad: base + '-dad' }));
  });
  test('mom starts a feed in the daytime → only dad\'s phone is told, without names', () => {
    const D = at('2026-11-21T14:00');
    go({ a: 'start', kind: 'nurse', side: 'L' }, D);
    assert.strictEqual(E.sent.length, 1);
    assert.strictEqual(last().topic, base + '-dad'); assert.strictEqual(last().title, '수유 시작');
    assert.ok(/왼쪽 직수 · 14:00/.test(last().message), last().message);
    go({ a: 'end' }, D + 15 * 60e3);
    assert.strictEqual(E.sent.length, 1, 'plain nursing end sends nothing');
  });
  test('while dad sleeps (02:30–09:00) routine alerts are held, but 도와줘요 still goes through', () => {
    const N = at('2026-11-22T04:00'), k = E.sent.length;
    go({ a: 'start', kind: 'pump' }, N); go({ a: 'end' }, N + 20 * 60e3);
    assert.strictEqual(E.sent.length, k);
    assert.strictEqual(go({ a: 'help' }, N + 21 * 60e3), '아빠에게 알렸어요.');
    assert.strictEqual(last().topic, base + '-dad'); assert.strictEqual(last().priority, 5);
  });
  test('dad asks for help → mom\'s phone; pump end in the evening → dad gets the freeze reminder', () => {
    go({ a: 'help', by: 'dad' }, at('2026-11-22T10:00'));
    assert.strictEqual(last().topic, base + '-mom');
    const P = at('2026-11-22T19:00');
    go({ a: 'start', kind: 'pump' }, P); go({ a: 'end' }, P + 20 * 60e3);
    assert.strictEqual(last().title, '유축 끝'); assert.strictEqual(last().topic, base + '-dad');
  });
  test('5-minute check: a night nursing past 30 minutes alerts mom (urgent) and awake dad, once', () => {
    const L = at('2026-11-22T23:00');
    go({ a: 'start', kind: 'nurse', side: 'R' }, L);
    const k = E.sent.length;
    Y.checkAlerts({}, L + 25 * 60e3); assert.strictEqual(E.sent.length, k, 'not yet at 25 min');
    Y.checkAlerts({}, L + 31 * 60e3);
    const got = E.sent.slice(k);
    assert.strictEqual(got.map(m => m.topic).join(), [base + '-mom', base + '-dad'].join());
    assert.strictEqual(got[0].priority, 5);
    Y.checkAlerts({}, L + 36 * 60e3); assert.strictEqual(E.sent.length, k + 2, 'no repeat');
    const w = JSON.parse(Y.doGet({ parameter: { k: E.props.TOKEN, a: 'widget' } }).text);
    assert.ok(w && 'running' in w && 'nextSide' in w);
    const w2 = Y.widget_(L + 32 * 60e3);
    assert.strictEqual(w2.running.label, '오른쪽 직수'); assert.strictEqual(w2.running.t, L); assert.strictEqual(w2.running.long, true);
    go({ a: 'end' }, L + 40 * 60e3);
    const w3 = Y.widget_(L + 41 * 60e3);
    assert.strictEqual(w3.running, null); assert.strictEqual(w3.lastFeed.label, '오른쪽에서 끝'); assert.strictEqual(w3.nextSide, '왼쪽');
    assert.strictEqual(Y.doGet({ parameter: { k: E.props.TOKEN, a: 'widget' } }).mime, 'json');
    assert.strictEqual(Y.doGet({ parameter: { k: 'bad', a: 'widget' } }).text, '주소가 올바르지 않아요.');
  });
  test('crying 20+ minutes tells the other parent once (held if they are asleep)', () => {
    const C = at('2026-11-23T20:00'), k = E.sent.length;
    go({ a: 'cry', by: 'dad' }, C); go({ a: 'cry', by: 'dad' }, C + 10 * 60e3);
    go({ a: 'cry', by: 'dad' }, C + 21 * 60e3); go({ a: 'cry', by: 'dad' }, C + 27 * 60e3);
    const got = E.sent.slice(k).filter(m => /울어요/.test(m.title));
    assert.strictEqual(got.length, 1); assert.strictEqual(got[0].topic, base + '-mom');
    assert.strictEqual(Y.widget_(C + 28 * 60e3).crying.minutes, 28);
  });
  test('dad ending a pump himself gets no "pump done" alert; the 5-minute check skips daytime', () => {
    const P = at('2026-11-24T19:00'), k = E.sent.length;
    go({ a: 'start', kind: 'pump', by: 'dad' }, P); go({ a: 'end', by: 'dad' }, P + 20 * 60e3);
    assert.ok(!E.sent.slice(k).some(m => m.title === '유축 끝'));
    const D = at('2026-11-24T13:00'); go({ a: 'start', kind: 'nurse', side: 'L' }, D);
    const k2 = E.sent.length; Y.checkAlerts({}, D + 45 * 60e3); assert.strictEqual(E.sent.length, k2);
    go({ a: 'end' }, D + 46 * 60e3);
  });
  test('a failing ntfy server never breaks the record', () => {
    const F = makeEnv(); F.x.setup();
    F.ctx.UrlFetchApp.fetch = () => { throw new Error('down'); };
    assert.strictEqual(F.x.doGet({ parameter: { k: F.props.TOKEN, a: 'start', kind: 'nurse', side: 'L', by: 'mom' } }).text, '왼쪽 직수 시작했어요.');
    assert.strictEqual(F.x.readEvents_().filter(e => e.type === 'session').length, 1);
  });
}

console.log('\n' + n + ' tests passed');
