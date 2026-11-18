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
  Logger.log('토큰: ' + p.getProperty('TOKEN'));
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
function api_getAll(k) {
  auth_(k);
  const cfg = ss_().getSheetByName('config');
  const raw = cfg && cfg.getLastRow() > 1 ? parse_(cfg.getRange(2, 2).getValue()) : null;
  return { events: readEvents_(), bags: readBags_(), config: raw, rev: rev_(), sheetUrl: ss_().getUrl(), execUrl: ScriptApp.getService().getUrl() };
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
  let msg;
  try { msg = locked_(() => { const m = act_(p, Date.now()); bump_(); return m; }); }
  catch (err) { msg = '기록하지 못했어요. 다시 말해 주세요.'; }
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
      if (open) return endSession_(open, by, now);
      // 종류를 말하지 않으면 최근 24시간에 가장 많이 한 종류 (없으면 직수+유축)
      const cnt = {}; recent.filter(e => e.type === 'session' && e.t > now - DAY).forEach(e => { cnt[e.kind] = (cnt[e.kind] || 0) + 1; });
      const top = Object.keys(cnt).sort((a, b) => cnt[b] - cnt[a])[0];
      const kind = kindParam_(p.kind) || top || 'nurse+pump';
      return startSession_(add, kind, side);
    }
    case 'start': {
      const kind = kindParam_(p.kind) || 'nurse+pump';
      let pre = '';
      if (open) { endSession_(open, by, now); pre = '앞 기록을 끝내고 '; }
      return pre + startSession_(add, kind, side);
    }
    case 'end': return open ? endSession_(open, by, now) : '진행 중인 수유가 없어요.';
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
      if (!prev) add({ type: 'cry', baby: 'D', rank });
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
      return '잠들었어요.';
    }
    case 'status': return status_(recent, now, side);
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
  return (kind === 'pump' ? '양쪽 유축' : SIDE_KO[s.side] + ' ' + KIND_KO[kind]) + ' 시작했어요.';
}
function endSession_(s, by, now) {
  s.end = now; s.endBy = by; s.endedAt = now; s.updatedAt = now; putEvent_(s);
  const sp = s.kind === 'pump' ? '' : splitText_(s, now);
  return (s.kind === 'pump' ? '유축' : KIND_KO[s.kind]) + ' 끝. ' + mins_(now - s.t) + '이에요.' + (sp ? ' ' + sp.replace(/왼/g, '왼쪽').replace(/오 /g, '오른쪽 ').replace(/ → /g, ', ') + '분.' : '');
}
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
  const open = evs.filter(e => e.type === 'session' && !e.end && e.t > now - 4 * HOUR)[0];
  return (open ? (open.kind === 'pump' ? '유축' : SIDE_KO[curSide_(open)] + ' ' + KIND_KO[open.kind]) + ' ' + mins_(now - open.t) + '째예요. ' : '') +
    '마지막 수유 ' + (lf ? mins_(now - lf) + ' 전' : '기록 없음') + ', 다음은 ' + SIDE_KO[side] + '. ' +
    '기저귀 ' + (ld ? mins_(now - ld) + ' 전' : '기록 없음') + '.';
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
