/**
 * 쌍둥이 수유 기록 — Google Apps Script 서버 (1단계)
 *
 * 하는 일
 *  1) 아이폰 단축어가 부르는 주소: ...exec?k=토큰&a=동작&by=mom
 *     → 기록하고, 시리가 읽을 짧은 한국어 문장을 돌려준다.
 *  2) 웹 페이지: ...exec?k=토큰  → 엄마·아빠가 Claude 계정 없이 여는 화면 (Index.html)
 *  3) 데이터는 구글 시트(events·bags·config 탭)에 저장된다.
 *
 * 처음 한 번: 편집기에서 setup() 실행 → 권한 허용 → 로그에 나온 토큰 확인 → 배포(웹 앱, 나로 실행, 모든 사용자)
 */

const SHEET_ID = '__SHEET_ID__';
const TZ = 'Asia/Seoul';
const HOUR = 3600e3, DAY = 24 * HOUR;
const EV_HEAD = ['id', 't', '시각', '종류', '내용', '기록자', '경로', '삭제', 'json'];
const BAG_HEAD = ['id', '코드', 'ml', '상태', '용도', '짠 시각', 'version', 'json'];
const SIDE_KO = { L: '왼쪽', R: '오른쪽', B: '양쪽' };
const KIND_KO = { nurse: '직수', 'nurse+pump': '직수 유축', pump: '유축' };

/* ---------- 설정 ---------- */
function setup() {
  const p = PropertiesService.getScriptProperties();
  if (!p.getProperty('TOKEN')) p.setProperty('TOKEN', Utilities.getUuid().replace(/-/g, '').slice(0, 24));
  sheet_('events', EV_HEAD); sheet_('bags', BAG_HEAD); sheet_('config', ['key', 'json']);
  if (!p.getProperty('NTFY')) p.setProperty('NTFY', 'tf-' + Utilities.getUuid().replace(/-/g, '').slice(0, 16));
  if (!ScriptApp.getProjectTriggers().some(t => t.getHandlerFunction() === 'checkAlerts')) ScriptApp.newTrigger('checkAlerts').timeBased().everyMinutes(5).create();
  Logger.log('토큰: ' + p.getProperty('TOKEN'));
  Logger.log('ntfy 알림 채널 — 엄마 폰: ' + p.getProperty('NTFY') + '-mom / 아빠 폰: ' + p.getProperty('NTFY') + '-dad');
  Logger.log('배포한 웹 앱 주소 뒤에 ?k=' + p.getProperty('TOKEN') + ' 를 붙여서 여세요.');
}
function token_() { return PropertiesService.getScriptProperties().getProperty('TOKEN'); }
function auth_(k) { if (!k || k !== token_()) throw new Error('unauthorized'); }
function rev_() { return Number(PropertiesService.getScriptProperties().getProperty('REV') || 0); }
function bump_() { const p = PropertiesService.getScriptProperties(); p.setProperty('REV', String(rev_() + 1)); }
function locked_(fn) {
  const lock = LockService.getScriptLock();
  lock.waitLock(15000);
  try { return fn(); } finally { lock.releaseLock(); }
}

/* ---------- 시트 ---------- */
function ss_() { return SpreadsheetApp.openById(SHEET_ID); }
function sheet_(name, head) {
  const ss = ss_();
  let sh = ss.getSheetByName(name);
  if (!sh) {
    sh = ss.insertSheet(name);
    if (head) { sh.getRange(1, 1, 1, head.length).setValues([head]); sh.setFrozenRows(1); sh.getRange('A:A').setNumberFormat('@'); }
  }
  return sh;
}
function rows_(sh, width) {
  const n = sh.getLastRow() - 1;
  return n > 0 ? sh.getRange(2, 1, n, width).getValues() : [];
}
function findRow_(sh, id) {
  const f = sh.getRange('A:A').createTextFinder(String(id)).matchEntireCell(true).findNext();
  return f ? f.getRow() : 0;
}
function fmt_(t) { return Utilities.formatDate(new Date(Number(t)), TZ, 'yyyy-MM-dd HH:mm'); }
function parse_(s) { try { return JSON.parse(s); } catch (e) { return null; } }

/* ---------- 기록(events) ---------- */
function readEvents_() {
  const out = [];
  for (const r of rows_(sheet_('events', EV_HEAD), EV_HEAD.length)) {
    const ev = parse_(r[8]);
    if (ev && ev.id) out.push(ev);
  }
  return out;
}
function getEvent_(id) {
  const sh = sheet_('events', EV_HEAD), row = findRow_(sh, id);
  return row ? parse_(sh.getRange(row, 9).getValue()) : null;
}
function putEvent_(ev) {
  const sh = sheet_('events', EV_HEAD), row = findRow_(sh, ev.id);
  const vals = [String(ev.id), ev.t, fmt_(ev.t), ev.type, summary_(ev), ev.by || '', ev.src || '', ev.deleted ? 'Y' : '', JSON.stringify(ev)];
  if (row) sh.getRange(row, 1, 1, vals.length).setValues([vals]);
  else sh.appendRow(vals);
}
function summary_(e) {
  switch (e.type) {
    case 'session': return (e.kind === 'pump' ? '양쪽 유축' : splitText_(e, e.end || Date.now()) ? '양쪽 ' + KIND_KO[e.kind] + ' (' + splitText_(e, e.end || Date.now()) + ')' : SIDE_KO[curSide_(e)] + ' ' + KIND_KO[e.kind]) + (e.end ? ' ' + Math.round((e.end - e.t) / 60000) + '분' : ' 진행 중') + (e.processed ? ' · ' + ((+e.mlL || 0) + (+e.mlR || 0)) + 'ml' : '');
    case 'diaper': return '기저귀 ' + (e.wet && e.stool ? '소변+대변' : e.wet ? '소변' : '대변');
    case 'bottle': return '젖병 ' + (e.milk === 'ebm' ? '모유 ' : '분유 ') + e.ml + 'ml';
    case 'weight': return (e.baby === 'S' ? '아들' : '딸') + ' 체중 ' + e.g + 'g';
    case 'order': return '아들 처방 ' + e.ml + 'ml/일';
    case 'nicu': return 'NICU 배송 ' + e.ml + 'ml';
    case 'cry': return '울음' + (e.rank && e.rank[0] ? ' · 1순위 ' + e.rank[0].why : '');
    case 'calm': return '울음 그침 · ' + (CALM_KO[e.how] || e.how);
    case 'sleep': return '잠' + (e.end ? ' ' + Math.round((e.end - e.t) / 60000) + '분' : ' 시작');
    case 'note': return String(e.text || '').slice(0, 60);
    case 'wash': return '유축 부품 세척';
    case 'momcheck': return '엄마 상태' + (e.temp ? ' ' + e.temp + '도' : '') + (e.epds !== undefined && e.epds !== '' ? ' · EPDS ' + e.epds : '');
    case 'break': return '울음 중 잠시 쉬기';
    case 'care': { const it = CARE_.find(x => x[0] === e.item); return (e.baby === 'S' ? '아들 ' : '딸 ') + (it ? it[1] : e.item) + ({ done: ' 완료', ok: ' 정상 확인', nicu: ' NICU에서', undo: ' 되돌림' }[e.status] || ''); }
    default: return e.type;
  }
}
const CALM_KO = { feed: '먹여서', diaper: '기저귀 갈아서', sleep: '재워서', hold: '안아줘서', other: '그 밖', unknown: '모름' };

/* ---------- 모유 팩(bags): version으로 동시 수정 방지 ---------- */
function readBags_() {
  const out = {};
  for (const r of rows_(sheet_('bags', BAG_HEAD), BAG_HEAD.length)) {
    const b = parse_(r[7]);
    if (b && r[0]) { delete b.id; out[String(r[0])] = b; }
  }
  return out;
}
function getBag_(id) {
  const sh = sheet_('bags', BAG_HEAD), row = findRow_(sh, id);
  if (!row) return null;
  const v = sh.getRange(row, 1, 1, BAG_HEAD.length).getValues()[0];
  return { bag: parse_(v[7]), version: Number(v[6]) || 0, row };
}
function putBag_(id, bag, version, row) {
  const sh = sheet_('bags', BAG_HEAD);
  const b = Object.assign({}, bag); delete b.id;
  const vals = [String(id), b.code || '', b.ml || 0, b.state || '', b.for === 'S' ? '아들용' : '딸도 가능', b.pumpedAt ? fmt_(b.pumpedAt) : '', version, JSON.stringify(b)];
  if (row) sh.getRange(row, 1, 1, vals.length).setValues([vals]);
  else sh.appendRow(vals);
}
function merge_(a, b) {
  for (const k in b) {
    if (b[k] && typeof b[k] === 'object' && !Array.isArray(b[k]) && a[k] && typeof a[k] === 'object') merge_(a[k], b[k]);
    else a[k] = b[k];
  }
  return a;
}

/* ---------- 웹 페이지가 부르는 함수 (google.script.run) ---------- */
function rawCfg_() {
  const sh = ss_().getSheetByName('config');
  return sh && sh.getLastRow() > 1 ? parse_(sh.getRange(2, 2).getValue()) : null;
}
function api_getAll(k) {
  auth_(k);
  const raw = rawCfg_();
  const nt = PropertiesService.getScriptProperties().getProperty('NTFY');
  return { events: readEvents_(), bags: readBags_(), config: raw, rev: rev_(), sheetUrl: ss_().getUrl(), execUrl: ScriptApp.getService().getUrl(),
    ntfy: nt ? { server: ntfyServer_(), mom: nt + '-mom', dad: nt + '-dad' } : null };
}
function api_rev(k) { auth_(k); return rev_(); }
function api_addEvent(k, ev) {
  auth_(k);
  return locked_(() => { const old = getEvent_(ev.id); putEvent_(old ? Object.assign(old, ev) : ev); bump_(); return 'ok'; });
}
function api_patchEvent(k, id, patch) {
  auth_(k);
  return locked_(() => { const old = getEvent_(id); if (!old) return 'missing'; putEvent_(Object.assign(old, patch)); bump_(); return 'ok'; });
}
function api_getBag(k, id) { auth_(k); const g = getBag_(id); return g ? { bag: g.bag, version: g.version } : null; }
function api_setBag(k, bag) {
  auth_(k);
  return locked_(() => { const g = getBag_(bag.id); putBag_(bag.id, bag, g ? g.version + 1 : 1, g ? g.row : 0); bump_(); return 'ok'; });
}
function api_updateBag(k, id, patch, expect) {
  auth_(k);
  return locked_(() => {
    const g = getBag_(id);
    if (!g) return 'missing';
    if (g.version !== expect) return 'busy';        // 그사이 다른 폰이 고침 → 다시 읽고 계산
    putBag_(id, merge_(g.bag, patch), g.version + 1, g.row); bump_(); return 'ok';
  });
}
function api_setConfig(k, cfg) {
  auth_(k);
  return locked_(() => {
    const sh = sheet_('config', ['key', 'json']);
    sh.getRange(2, 1, 1, 2).setValues([['main', JSON.stringify(cfg)]]); bump_(); return 'ok';
  });
}

/* ---------- 진입점 ---------- */
function doGet(e) {
  const p = (e && e.parameter) || {};
  if (!p.k || p.k !== token_()) return ContentService.createTextOutput('주소가 올바르지 않아요.');
  if (!p.a) {
    const html = HtmlService.createHtmlOutputFromFile('Index').getContent().replace('__TOKEN__', p.k);
    return HtmlService.createHtmlOutput(html).setTitle('쌍둥이 수유 보드')
      .addMetaTag('viewport', 'width=device-width, initial-scale=1, viewport-fit=cover');
  }
  if (p.a === 'widget') return ContentService.createTextOutput(JSON.stringify(widget_(Date.now()))).setMimeType(ContentService.MimeType.JSON);
  let msg;
  OUTBOX_.length = 0;
  try { msg = locked_(() => { const m = act_(p, Date.now()); bump_(); return m; }); }
  catch (err) { msg = '기록하지 못했어요. 다시 말해 주세요.'; OUTBOX_.length = 0; }
  flush_(Date.now());
  return ContentService.createTextOutput(msg);
}
function doPost(e) { return doGet(e); }

/* ---------- 단축어 동작 ---------- */
function act_(p, now) {
  const by = p.by === 'dad' ? 'dad' : 'mom';
  const src = p.src || 'shortcut';
  const all = readEvents_().filter(e => !e.deleted);
  const recent = all.filter(e => e.t > now - 3 * DAY);
  const add = ev => { ev.id = ev.id || ('s' + now.toString(36) + Math.random().toString(36).slice(2, 6)); ev.t = ev.t || now; ev.updatedAt = now; ev.by = by; ev.src = src; putEvent_(ev); return ev; };
  const open = recent.filter(e => e.type === 'session' && !e.end && e.t > now - 4 * HOUR).sort((a, b) => b.t - a.t)[0];
  const side = sideParam_(p.side) || suggestSide_(recent, now);
  switch (p.a) {
    case 'feed': {                                            // 액션 버튼: 진행 중이면 끝, 아니면 시작
      if (open) { pumpDone_(open, by, now); return endSession_(open, by, now); }
      // 종류를 말하지 않으면 최근 24시간에 가장 많이 한 종류 (없으면 직수+유축)
      const cnt = {}; recent.filter(e => e.type === 'session' && e.t > now - DAY).forEach(e => { cnt[e.kind] = (cnt[e.kind] || 0) + 1; });
      const top = Object.keys(cnt).sort((a, b) => cnt[b] - cnt[a])[0];
      const kind = kindParam_(p.kind) || top || 'nurse+pump';
      return startSession_(add, kind, side);
    }
    case 'start': {
      const kind = kindParam_(p.kind) || 'nurse+pump';
      let pre = '';
      if (open) { pumpDone_(open, by, now); endSession_(open, by, now); pre = '앞 기록을 끝내고 '; }
      return pre + startSession_(add, kind, side);
    }
    case 'end': if (open) pumpDone_(open, by, now); return open ? endSession_(open, by, now) : '진행 중인 수유가 없어요.';
    case 'help': {
      const ep = cryEpisode_(recent, now);
      queue_(other_(by), '도와줘요', (by === 'mom' ? '엄마' : '아빠') + '가 도움을 요청했어요' + (ep ? ' · ' + ep.minutes + '분째 울음' : ''), 5, false);
      return (by === 'mom' ? '아빠' : '엄마') + '에게 알렸어요.';
    }
    case 'switch': {
      if (!open || open.kind === 'pump') return '바꿀 직수가 없어요.';
      const to = curSide_(open) === 'L' ? 'R' : 'L';
      open.segs = segs_(open).concat({ side: to, t: now }); open.updatedAt = now; putEvent_(open);
      return SIDE_KO[to] + '으로 바꿨어요.';
    }
    case 'diaper': {
      const wet = p.wet === '1', stool = p.stool === '1';
      if (!wet && !stool) return '소변인지 대변인지 알려 주세요.';
      add({ type: 'diaper', baby: 'D', wet, stool });
      return '기저귀 ' + (wet && stool ? '소변 대변' : wet ? '소변' : '대변') + ' 기록했어요.';
    }
    case 'bottle': {
      const ml = Math.round(Number(String(p.ml || '').replace(/[^0-9.]/g, '')));
      if (!(ml > 0 && ml < 400)) return '양을 숫자로 말해 주세요.';
      const milk = /분유|formula/.test(p.milk || '') ? 'formula' : 'ebm';
      add({ type: 'bottle', baby: 'D', ml, milk, applied: milk === 'ebm' ? false : undefined });
      return '젖병 ' + (milk === 'ebm' ? '모유 ' : '분유 ') + ml + '밀리 기록했어요.';
    }
    case 'cry': {
      const rank = cryRank_(recent, now);
      // 두 폰이 같은 울음을 동시에 감지하면 5분 안의 울음은 하나로
      const prev = recent.filter(e => e.type === 'cry' && e.t > now - 5 * 60e3)[0];
      const evs = prev ? recent : recent.concat(add({ type: 'cry', baby: 'D', rank }));
      const ep = cryEpisode_(evs, now);
      if (ep && ep.minutes >= 20 && !alerted_('cry' + ep.start)) queue_(other_(by), ep.minutes + '분째 울어요', '혼자 달래는 중이에요. 도와줄 수 있으면 가 주세요.', 4, true);
      if (ep && ep.minutes >= 20) return ep.minutes + '분째 울고 있어요. 먹이기, 기저귀, 체온, 트림을 봤는데도 안 그치면 아기를 등 대고 침대에 눕히고 5분에서 10분 쉬어도 괜찮아요. 흔들지는 마세요. 38도 이상이거나 축 처지면 바로 응급실이에요.';
      return rank.length ? rank.slice(0, 2).map((r, i) => (i ? '다음은 ' : '') + r.say).join('. ') + '.' : '기록했어요.';
    }
    case 'calm': {
      const how = CALM_KO[p.how] ? p.how : calmParam_(p.how);
      add({ type: 'calm', baby: 'D', how });
      return (CALM_KO[how] || '') + ' 그친 걸 기록했어요.';
    }
    case 'sleep': {
      const s = recent.filter(e => e.type === 'sleep' && !e.end && e.t > now - 6 * HOUR).sort((a, b) => b.t - a.t)[0];
      if (s) { s.end = now; s.endBy = by; s.updatedAt = now; putEvent_(s); return '깼어요. ' + mins_(now - s.t) + ' 잤어요.'; }
      add({ type: 'sleep', baby: 'D', end: null });
      return '잠들었어요. 등 대고, 자기 잠자리에 아기만 있는지 봐 주세요.';
    }
    case 'status': return status_(recent, now, side);
    case 'break': {
      add({ type: 'break' });
      return '아기를 등 대고 침대에 눕혔으면 방을 나와 숨을 고르세요. 10분 뒤에 다시 보러 가요. 도움이 필요하면 배우자를 깨우세요.';
    }
    case 'care': return careSay_(all, now);
    case 'undo': {
      const mine = recent.filter(e => e.by === by && (e.updatedAt || e.t) > now - 15 * 60e3).sort((a, b) => (b.updatedAt || b.t) - (a.updatedAt || a.t))[0];
      if (!mine) return '15분 안에 취소할 기록이 없어요.';
      if (mine.type === 'session' && mine.end && mine.endedAt === mine.updatedAt) { mine.end = null; mine.endBy = null; mine.endedAt = null; mine.updatedAt = now; putEvent_(mine); return summary_(mine).replace(' 진행 중', '') + ' 끝낸 걸 되돌렸어요.'; }
      mine.deleted = true; putEvent_(mine);
      return '방금 ' + summary_(mine) + ' 기록을 취소했어요.';
    }
    default: return '모르는 동작이에요.';
  }
}
function startSession_(add, kind, side) {
  const s = add({ type: 'session', kind, baby: kind === 'pump' ? null : 'D', side: kind === 'pump' ? 'B' : side, end: null });
  queue_(other_(s.by), '수유 시작', (kind === 'pump' ? '양쪽 유축' : SIDE_KO[s.side] + ' ' + KIND_KO[kind]) + ' · ' + hm_(s.t), 3, true);
  return (kind === 'pump' ? '양쪽 유축' : SIDE_KO[s.side] + ' ' + KIND_KO[kind]) + ' 시작했어요.';
}
function endSession_(s, by, now) {
  s.end = now; s.endBy = by; s.endedAt = now; s.updatedAt = now; putEvent_(s);
  const sp = s.kind === 'pump' ? '' : splitText_(s, now);
  const safe = s.kind === 'pump' || !isNight_(now) ? '' : (now - s.t > 30 * 60e3 ? ' 오래 안고 있었어요. 아기는 등 대고 자기 침대로.' : ' 등 대고, 아기 침대로.');
  return (s.kind === 'pump' ? '유축' : KIND_KO[s.kind]) + ' 끝. ' + mins_(now - s.t) + '이에요.' + (sp ? ' ' + sp.replace(/왼/g, '왼쪽').replace(/오 /g, '오른쪽 ').replace(/ → /g, ', ') + '분.' : '') + safe;
}
function isNight_(t) { const h = Number(Utilities.formatDate(new Date(t), TZ, 'H')); return h >= 21 || h < 7; }
function sideParam_(v) { v = String(v || ''); return /^(L|왼)/i.test(v) ? 'L' : /^(R|오)/i.test(v) ? 'R' : null; }
function kindParam_(v) { v = String(v || ''); return v === 'nurse' || v === 'nurse+pump' || v === 'pump' ? v : /직수.*유축|both/.test(v) ? 'nurse+pump' : /유축/.test(v) ? 'pump' : /직수/.test(v) ? 'nurse' : null; }
function calmParam_(v) { v = String(v || ''); return /먹|수유|젖/.test(v) ? 'feed' : /기저귀/.test(v) ? 'diaper' : /재|잠/.test(v) ? 'sleep' : /안/.test(v) ? 'hold' : v ? 'other' : 'unknown'; }
// 쪽 구간: segs=[{side,t}] (수유 중 반대쪽으로 바꾸면 늘어남). 예전 기록은 side 하나
function segs_(e) { return e.segs && e.segs.length ? e.segs : [{ side: e.side, t: e.t }]; }
function curSide_(e) { const s = segs_(e); return s[s.length - 1].side; }
function sideTimes_(e, now) {
  const s = segs_(e), end = e.end || now;
  return s.map((x, i) => ({ side: x.side, ms: Math.max(0, (i + 1 < s.length ? s[i + 1].t : end) - x.t) }));
}
function splitText_(e, now) {
  const st = sideTimes_(e, now).filter(x => x.ms >= 30e3);
  return st.length < 2 ? '' : st.map(x => (x.side === 'L' ? '왼' : '오') + ' ' + Math.max(1, Math.round(x.ms / 60000))).join(' → ');
}
// 다음 쪽: 지난 수유에서 덜 먹인 쪽 (한쪽만 먹였으면 반대쪽)
function suggestSide_(evs, now) {
  const last = evs.filter(e => e.type === 'session' && e.kind !== 'pump' && e.side && e.side !== 'B').sort((a, b) => b.t - a.t)[0];
  if (!last) return 'L';
  const tot = { L: 0, R: 0 };
  for (const x of sideTimes_(last, now || Date.now())) if (tot[x.side] !== undefined) tot[x.side] += x.ms;
  if (tot.L === tot.R) return curSide_(last) === 'L' ? 'R' : 'L';
  return tot.L < tot.R ? 'L' : 'R';
}
function mins_(ms) { const m = Math.max(0, Math.round(ms / 60000)); return m < 60 ? m + '분' : Math.floor(m / 60) + '시간' + (m % 60 ? ' ' + (m % 60) + '분' : ''); }
function lastFeedEnd_(evs) {
  let t = 0;
  for (const e of evs) {
    if (e.type === 'session' && e.kind !== 'pump') t = Math.max(t, e.end || e.t);
    if (e.type === 'bottle' && e.baby === 'D') t = Math.max(t, e.t);
  }
  return t;
}
function status_(evs, now, side) {
  const lf = lastFeedEnd_(evs);
  const ld = evs.filter(e => e.type === 'diaper').reduce((m, e) => Math.max(m, e.t), 0);
  const open = evs.filter(e => e.type === 'session' && !e.end && e.t > now - 4 * HOUR).sort((a, b) => b.t - a.t)[0];
  return (open ? (open.kind === 'pump' ? '유축' : SIDE_KO[curSide_(open)] + ' ' + KIND_KO[open.kind]) + ' ' + mins_(now - open.t) + '째예요. ' : '') +
    '마지막 수유 ' + (lf ? mins_(now - lf) + ' 전' : '기록 없음') + ', 다음은 ' + SIDE_KO[side] + '. ' +
    '기저귀 ' + (ld ? mins_(now - ld) + ' 전' : '기록 없음') + '.';
}

/* ---------- 잠금화면 알림 (ntfy) ----------
 * 엄마 폰은 '채널-mom', 아빠 폰은 '채널-dad'를 ntfy 앱에서 구독. 내가 한 기록은 상대 폰으로만 간다.
 * 상대가 자는 시간(설정의 엄마 보호 수면·아빠 수면)엔 급하지 않은 알림을 보내지 않는다.
 * 내용은 짧게: 아기 이름·체중 같은 정보는 넣지 않음. */
const OUTBOX_ = [];
function ntfyServer_() { return PropertiesService.getScriptProperties().getProperty('NTFY_SERVER') || 'https://ntfy.sh'; }
function other_(by) { return by === 'dad' ? 'mom' : 'dad'; }
function hm_(t) { return Utilities.formatDate(new Date(t), TZ, 'HH:mm'); }
function cfg_() {
  const c = rawCfg_();
  return Object.assign({ momSleep: { start: '21:45', end: '02:30' }, dadSleep: { start: '02:30', end: '09:00' } }, c || {});
}
function inWin_(t, w) {
  const [h, m] = hm_(t).split(':').map(Number), x = h * 60 + m;
  const a = w.start.split(':').map(Number), b = w.end.split(':').map(Number), A = a[0] * 60 + a[1], B = b[0] * 60 + b[1];
  return A <= B ? x >= A && x < B : x >= A || x < B;
}
function asleep_(who, now, c) { c = c || cfg_(); return inWin_(now, who === 'mom' ? c.momSleep : c.dadSleep); }
function queue_(to, title, msg, prio, quietWhenAsleep) { OUTBOX_.push({ to, title, msg, prio, quiet: quietWhenAsleep }); }
function alerted_(key) {
  const p = PropertiesService.getScriptProperties(), m = parse_(p.getProperty('ALERTED') || '{}') || {}, now = Date.now();
  for (const k in m) if (now - m[k] > 2 * DAY) delete m[k];
  if (m[key]) return true;
  m[key] = now; p.setProperty('ALERTED', JSON.stringify(m)); return false;
}
function flush_(now) {
  const base = PropertiesService.getScriptProperties().getProperty('NTFY');
  now = now || Date.now();
  if (!base) { OUTBOX_.length = 0; return; }
  const c = OUTBOX_.some(n => n.quiet) ? cfg_() : null;
  while (OUTBOX_.length) {
    const n = OUTBOX_.shift();
    if (n.quiet && asleep_(n.to, now, c)) continue;
    try {
      UrlFetchApp.fetch(ntfyServer_(), { method: 'post', contentType: 'application/json', muteHttpExceptions: true,
        payload: JSON.stringify({ topic: base + '-' + n.to, title: n.title, message: n.msg, priority: n.prio }) });
    } catch (e) { /* 알림이 실패해도 기록은 이미 저장됨 */ }
  }
}
function pumpDone_(open, by, now) {
  if (open.kind !== 'nurse' && by !== 'dad') queue_('dad', '유축 끝', '양 적고 4시간 안에 냉동해 주세요 · ' + hm_(now), 3, true);
}
// 5분마다: 밤에 직수가 30분을 넘으면 엄마 폰(졸고 있을 수 있음)과 깨어 있는 아빠 폰에 한 번 알림
function checkAlerts(e, at) {                            // 트리거가 e를 넘김. at은 시험용
  const now = at || Date.now();
  if (!isNight_(now)) return;
  OUTBOX_.length = 0;
  locked_(() => {
    const open = readEvents_().filter(e => !e.deleted && e.type === 'session' && !e.end && e.kind !== 'pump' && e.t > now - 4 * HOUR).sort((a, b) => b.t - a.t)[0];
    if (open && now - open.t > 30 * 60e3 && !alerted_('long' + open.id)) {
      queue_('mom', '아기 안고 잠들지 않았나요?', '수유 ' + mins_(now - open.t) + '째예요. 졸리면 아기를 먼저 아기 침대에.', 5, false);
      queue_('dad', '엄마 수유 30분 넘음', '아기를 안고 잠들지 않았는지 봐 주세요.', 4, true);
    }
  });
  flush_(now);
}
// 잠금화면 위젯이 읽는 현재 상황 (이름·체중 없이)
function widget_(now) {
  const evs = readEvents_().filter(e => !e.deleted && e.t > now - 3 * DAY);
  const open = evs.filter(e => e.type === 'session' && !e.end && e.t > now - 4 * HOUR).sort((a, b) => b.t - a.t)[0];
  const lf = evs.filter(e => (e.type === 'session' && e.kind !== 'pump' && e.end) || (e.type === 'bottle' && e.baby === 'D')).sort((a, b) => b.t - a.t)[0];
  const ld = evs.filter(e => e.type === 'diaper').reduce((m, e) => Math.max(m, e.t), 0);
  const ep = cryEpisode_(evs, now);
  return {
    now,
    running: open ? { t: open.t, label: open.kind === 'pump' ? '유축' : SIDE_KO[curSide_(open)] + ' ' + KIND_KO[open.kind], long: isNight_(now) && open.kind !== 'pump' && now - open.t > 30 * 60e3 } : null,
    lastFeed: lf ? { t: lf.end || lf.t, label: lf.type === 'bottle' ? '젖병' : SIDE_KO[curSide_(lf)] + '에서 끝' } : null,
    nextSide: SIDE_KO[suggestSide_(evs, now)],
    lastDiaper: ld || null,
    crying: ep ? { start: ep.start, minutes: ep.minutes } : null,
  };
}

/* ---------- 울음 묶음 (앱 logic.js의 cryEpisode와 같은 규칙) ---------- */
function cryEpisode_(events, now) {
  const evs = events.filter(e => (e.type === 'cry' || e.type === 'calm') && e.t <= now && e.t > now - 3 * HOUR).sort((a, b) => b.t - a.t);
  if (!evs.length || evs[0].type === 'calm' || now - evs[0].t > 30 * 60e3) return null;
  let start = evs[0].t;
  for (const e of evs) { if (e.type === 'calm') break; if (start - e.t > 30 * 60e3) break; start = e.t; }
  return { start, minutes: Math.round((now - start) / 60000) };
}

/* ---------- 검진·접종 일정 말하기 (앱 logic.js의 CARE_ITEMS와 같은 표) ---------- */
const CARE_ = [   // [id, 말할 이름, 시작, 끝, 출산 병원에서 하는 것]
  ['hepb1', 'B형간염 1차', { d: 0 }, { d: 1 }, true], ['nbs', '선천성대사이상검사 결과', { d: 2 }, { d: 14 }, true], ['hear', '청각선별검사', { d: 0 }, { m: 1 }, true],
  ['chk1', '영유아건강검진 1차', { d: 14 }, { d: 35 }], ['hepb2', 'B형간염 2차', { m: 1 }, { m: 1, d: 14 }], ['bcg', 'BCG 결핵 접종', { d: 0 }, { d: 34 }],
  ['m2', '2개월 접종', { m: 2 }, { m: 2, d: 14 }], ['chk2', '영유아건강검진 2차', { m: 4 }, { m: 6 }],
];
function careSay_(evs, now) {
  const cfg = rawCfg_() || {};
  const bd = String(cfg.birthDate || '2026-11-06').split('-').map(Number);
  const at = a => new Date(bd[0], bd[1] - 1 + (a.m || 0), bd[2] + (a.d || 0)).getTime();
  const md = t => { const d = new Date(t); return (d.getMonth() + 1) + '월 ' + d.getDate() + '일'; };
  const done = (baby, id) => { let b = null; for (const e of evs) if (e.type === 'care' && e.baby === baby && e.item === id && (!b || e.t > b.t)) b = e; return b && b.status !== 'undo'; };
  const due = []; let hosp = 0;
  for (const [id, name, f, t, h] of CARE_) {
    const babies = ['D', 'S'].filter(b => !done(b, id));
    if (!babies.length || at(f) > now + 7 * DAY) continue;
    if (h) hosp++; else due.push({ name, to: at(t), babies });
  }
  const tail = hosp ? '출산 병원에서 하는 검사·접종 ' + hosp + '개는 퇴원요약지로 확인해 주세요.' : '';
  if (!due.length) return tail || '일주일 안에 할 검진이나 접종이 없어요.';
  return due.sort((a, b) => a.to - b.to).slice(0, 3).map(x => x.name + ' ' + md(x.to) + '까지' + (x.babies.length === 1 ? (x.babies[0] === 'D' ? ', 딸' : ', 아들') : '')).join('. ') + '.' + (tail ? ' ' + tail : '');
}

/* ---------- 울음 원인 순위 (분류 모델 아님: 내 기록으로 보는 가능성) ----------
 * 배고픔 = 마지막 수유 후 시간 ÷ 최근 24시간 수유 간격 중앙값(없으면 150분)
 * 졸림   = 깨어 있은 시간 ÷ 깨어 있는 시간 중앙값(잠 기록 5회 미만이면 60분, 가정값)
 * 기저귀 = 마지막 교체 후 시간 ÷ 180분 (+0.3: 그 뒤에 수유가 있었으면)
 */
function cryRank_(evs, now) {
  const feeds = evs.filter(e => (e.type === 'session' && e.kind !== 'pump') || (e.type === 'bottle' && e.baby === 'D')).map(e => e.t).sort((a, b) => a - b);
  const day = feeds.filter(t => t > now - DAY);
  const gaps = []; for (let i = 1; i < day.length; i++) gaps.push(day[i] - day[i - 1]);
  const med = a => { if (!a.length) return null; const s = a.slice().sort((x, y) => x - y); return s[Math.floor(s.length / 2)]; };
  const feedInt = med(gaps.filter(g => g > 20 * 60e3)) || 150 * 60e3;
  const lf = lastFeedEnd_(evs);
  const out = [];
  if (lf) out.push({ k: 'feed', score: (now - lf) / feedInt, why: '배고픔', say: '배고플 수 있어요. 마지막 수유 ' + mins_(now - lf) + ' 전' });
  const sleeps = evs.filter(e => e.type === 'sleep').sort((a, b) => a.t - b.t);
  const lastSleep = sleeps[sleeps.length - 1];
  if (lastSleep && lastSleep.end) {
    const awakeGaps = []; for (let i = 1; i < sleeps.length; i++) if (sleeps[i - 1].end) awakeGaps.push(sleeps[i].t - sleeps[i - 1].end);
    const ww = awakeGaps.length >= 5 ? med(awakeGaps) : 60 * 60e3;
    out.push({ k: 'sleep', score: (now - lastSleep.end) / ww, why: '졸림', say: '졸릴 수 있어요. 깬 지 ' + mins_(now - lastSleep.end) });
  }
  const ld = evs.filter(e => e.type === 'diaper').reduce((m, e) => Math.max(m, e.t), 0);
  if (ld) out.push({ k: 'diaper', score: (now - ld) / (180 * 60e3) + (lf > ld ? 0.3 : 0), why: '기저귀', say: '기저귀일 수 있어요. 마지막 교체 ' + mins_(now - ld) + ' 전' });
  return out.sort((a, b) => b.score - a.score).map(r => ({ k: r.k, why: r.why, score: Math.round(r.score * 100) / 100, say: r.say }));
}
