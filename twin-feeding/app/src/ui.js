(() => {
'use strict';
/* ---------- 도우미 ---------- */
const $ = s => document.querySelector(s);
const esc = s => String(s ?? '').replace(/[&<>"']/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
const ls = {
  get(k, d) { try { const v = localStorage.getItem(k); return v === null ? d : JSON.parse(v); } catch { return d; } },
  set(k, v) { try { localStorage.setItem(k, JSON.stringify(v)); return true; } catch { return false; } },
};
const uid = () => Date.now().toString(36) + Math.random().toString(36).slice(2, 7);
const fmtT = t => { const d = new Date(t); return pad(d.getHours()) + ':' + pad(d.getMinutes()); };
const fmtMD = t => { const d = new Date(t); return (d.getMonth() + 1) + '/' + d.getDate(); };
const fmtDur = ms => { if (ms === null || ms === undefined) return '—'; const m = Math.round(ms / 60000); return m < 60 ? m + '분' : Math.floor(m / 60) + '시간' + (m % 60 ? ' ' + (m % 60) + '분' : ''); };
const fmtAgo = t => { if (!t) return '기록 없음'; const ms = Date.now() - t; return ms < 90e3 ? '방금' : fmtDur(ms) + ' 전'; };
const fmtAgoShort = t => { if (!t) return '—'; const m = Math.round((Date.now() - t) / 60000); return m < 2 ? '방금' : m < 60 ? m + '분 전' : Math.floor(m / 60) + '시간 전'; };
const n0 = v => Number(v || 0).toLocaleString('ko-KR');
const bagCode = t => { const d = new Date(t); return pad(d.getMonth() + 1) + pad(d.getDate()) + '-' + pad(d.getHours()) + pad(d.getMinutes()); };
const NAME = b => b === 'D' ? state.cfg.names.D : b === 'S' ? state.cfg.names.S : '';
const STATE_KO = { fridge: '냉장', freezer: '냉동', thawed: '해동', nicu: 'NICU 보냄', used: '먹임', discard: '버림' };
const SIDE_KO = { L: '왼쪽', R: '오른쪽', B: '양쪽' };
const OTHER = { L: 'R', R: 'L' };
const icon = (id, cls) => '<svg class="ic' + (cls ? ' ' + cls : '') + '" aria-hidden="true"><use href="#i-' + id + '"/></svg>';
const bub = (id, tone) => '<span class="bub ' + (tone || '') + '">' + icon(id) + '</span>';
const face = b => '<svg class="face" viewBox="0 0 48 48" aria-hidden="true"><use href="#face-' + b + '"/></svg>';
const KIND = {
  nurse: { label: '직수만', ic: 'nurse', tone: 'girl' },
  'nurse+pump': { label: '직수 + 유축', ic: 'both', tone: 'blue' },
  pump: { label: '유축만', ic: 'pump', tone: 'violet' },
};
const kindDesc = (kind, side) => kind === 'pump' ? '양쪽 유축' : kind === 'nurse' ? SIDE_KO[side] + ' 직수' : SIDE_KO[side] + ' 직수 · ' + SIDE_KO[OTHER[side]] + ' 유축';

const TABS = {
  mom: [['feed', '수유', 'nurse'], ['kids', '아이들', 'babies'], ['log', '기록', 'clock']],
  dad: [['todo', '할 일', 'todo'], ['kids', '아이들', 'babies'], ['milk', '모유', 'milk'], ['log', '기록', 'clock']],
};

const state = {
  events: [], bags: {}, cfg: mergeConfig(null), cfgRaw: null,
  me: ls.get('tf.me', null), tab: ls.get('tf.tab2', null), night: ls.get('tf.night', false),
  mode: 'loading', standby: false, side: null, seen: new Set(), booted: false, pending: false, logView: 'list',
};
function validTab() {
  const tabs = TABS[state.me] || [];
  if (!tabs.some(t => t[0] === state.tab)) state.tab = tabs.length ? tabs[0][0] : null;
}

/* ---------- 저장소: 공유 DB, 없으면 이 기기 저장 ---------- */
const Store = {
  db: null, local: null,
  async init() {
    let db = null;
    try { db = window.claude && window.claude.use ? await window.claude.use('db') : null; } catch { db = null; }
    if (db) { this.db = db; state.mode = 'db-wait'; this.subscribe(); }
    else { state.mode = 'local'; this.local = ls.get('tf.data', { days: {}, bags: {}, config: null }); this.applyLocal(); }
    render();
  },
  subscribe() {
    const timer = setTimeout(() => { if (state.mode === 'db-wait') { state.mode = 'db-slow'; render(); } }, 10000);
    const ok = snap => { if (!snap.metadata.fromCache) { clearTimeout(timer); state.mode = 'db'; } };
    const fail = e => { clearTimeout(timer); state.mode = 'db-error'; state.err = e && e.code; render(); };
    this.db.collection('days').onSnapshot(snap => {
      const evs = [];
      for (const d of snap.docs) { const m = (d.data() || {}).events || {}; for (const id in m) { const e = m[id]; if (e && !e.deleted) evs.push(Object.assign({ id }, e)); } }
      ok(snap); setEvents(evs);
    }, fail);
    this.db.collection('bags').onSnapshot(snap => {
      const b = {}; for (const d of snap.docs) { const v = d.data(); if (v && !v.deleted) b[d.id] = Object.assign({ id: d.id }, v); }
      ok(snap); state.bags = b; render(); reconcileBottles();
    }, fail);
    this.db.doc('config/main').onSnapshot(snap => { ok(snap); state.cfgRaw = snap.exists ? snap.data() : null; state.cfg = mergeConfig(state.cfgRaw); render(); }, fail);
  },
  applyLocal() {
    const evs = [];
    for (const k in this.local.days) for (const id in this.local.days[k]) { const e = this.local.days[k][id]; if (!e.deleted) evs.push(Object.assign({ id }, e)); }
    state.bags = Object.fromEntries(Object.entries(this.local.bags).filter(([, b]) => !b.deleted).map(([id, b]) => [id, Object.assign({ id }, b)]));
    state.cfgRaw = this.local.config; state.cfg = mergeConfig(this.local.config);
    setEvents(evs);
  },
  saveLocal() {
    if (!ls.set('tf.data', this.local)) {
      // 저장 실패: 화면도 마지막으로 저장된 상태로 되돌림 (저장 안 된 변경이 화면에만 남지 않게)
      this.local = ls.get('tf.data', { days: {}, bags: {}, config: null }); this.applyLocal();
      throw { code: 'local_failed' };
    }
    this.applyLocal();
  },
  async addEvent(ev) {
    const id = ev.id || uid(); const body = Object.assign({}, ev); delete body.id;
    const key = dayKey(ev.t);
    if (!this.db) { (this.local.days[key] = this.local.days[key] || {})[id] = body; this.saveLocal(); return id; }
    const ref = this.db.doc('days/' + key);
    try { await ref.update({ events: { [id]: body } }); }
    catch (e) {
      if (e && e.code === 'invalid_argument') {
        const s = await ref.get();
        if (s.exists) await ref.update({ events: { [id]: body } });
        else await ref.set({ date: key, events: { [id]: body } });
      } else throw e;
    }
    return id;
  },
  async patchEvent(ev, patch) {
    const key = dayKey(ev.t);
    if (!this.db) { const d = this.local.days[key]; if (d && d[ev.id]) Object.assign(d[ev.id], patch); this.saveLocal(); return; }
    await this.db.doc('days/' + key).update({ events: { [ev.id]: patch } });
  },
  async setBag(bag) {
    const body = Object.assign({}, bag); delete body.id;
    if (!this.db) { this.local.bags[bag.id] = body; this.saveLocal(); return; }
    await this.db.doc('bags/' + bag.id).set(body);
  },
  async patchBag(id, patch) {
    if (!this.db) { Object.assign(this.local.bags[id], patch); this.saveLocal(); return; }
    await this.db.doc('bags/' + id).update(patch);
  },
  async setConfig(cfg) {
    if (!this.db) { this.local.config = cfg; this.saveLocal(); return; }
    await this.db.doc('config/main').set(cfg);
  },
};
async function act(fn, okMsg) {
  try { await fn(); if (okMsg) toast(okMsg); return true; }
  catch (e) {
    const code = e && e.code;
    toast(code === 'invalid_argument' ? '저장 권한이 없어요. 공유 메뉴에서 편집 권한을 받아 주세요.' : code === 'quota_exceeded' ? '저장 공간이 다 찼어요.' : code === 'local_failed' ? '이 폰에 저장하지 못했어요. 새로고침하면 사라질 수 있어요.' : '저장하지 못했어요. 잠시 후 다시 눌러 주세요.', true);
    return false;
  }
}
function setEvents(evs) {
  evs.sort((a, b) => a.t - b.t);
  const prevBooted = state.booted;
  for (const e of evs) if (e.type === 'session' && !e.end && !state.seen.has(e.id)) {
    state.seen.add(e.id);
    if (prevBooted && state.me === 'dad' && e.by !== 'dad' && state.standby && !inWindow(Date.now(), state.cfg.dadSleep)) alertDad(e);
  }
  state.events = evs; state.booted = true; render();
  if (Object.keys(state.bags).length) reconcileBottles();
}

/* ---------- 아빠 대기 모드 ---------- */
let wakeLock = null, audio = null;
async function lockScreen() { try { wakeLock = await navigator.wakeLock.request('screen'); } catch { wakeLock = null; } }
document.addEventListener('visibilitychange', () => { if (state.standby && document.visibilityState === 'visible') lockScreen(); });
function chime() {
  if (!audio) return;
  const t0 = audio.currentTime;
  [[660, 0], [880, .28], [660, .56]].forEach(([f, d]) => {
    const o = audio.createOscillator(), g = audio.createGain();
    o.frequency.value = f; o.type = 'sine'; o.connect(g); g.connect(audio.destination);
    g.gain.setValueAtTime(0.0001, t0 + d); g.gain.exponentialRampToValueAtTime(0.35, t0 + d + .03); g.gain.exponentialRampToValueAtTime(0.0001, t0 + d + .25);
    o.start(t0 + d); o.stop(t0 + d + .27);
  });
}
function alertDad(e) {
  chime(); try { navigator.vibrate && navigator.vibrate([200, 100, 200]); } catch {}
  toast('엄마가 ' + KIND[e.kind].label + '을 시작했어요. 물 한 컵 챙겨 주세요.', true, 12000);
}

/* ---------- 토스트·시트 ---------- */
let toastTimer;
function toast(msg, alert, ms, undo) {
  const el = $('#toast'); el.textContent = msg; el.className = alert ? 'alert-t' : ''; el.hidden = false;
  if (undo) { const b = document.createElement('button'); b.className = 'undo'; b.textContent = '되돌리기'; b.addEventListener('click', () => { el.hidden = true; undo(); }); el.appendChild(b); }
  clearTimeout(toastTimer); toastTimer = setTimeout(() => { el.hidden = true; }, ms || 2400);
}
function openSheet(html, bind) {
  $('#toast').hidden = true;
  $('#panel').innerHTML = html; $('#sheet').hidden = false; $('#panel').scrollTop = 0;
  if (bind) bind($('#panel'));
}
function closeSheet() { $('#sheet').hidden = true; $('#panel').innerHTML = ''; render(); }
$('#sheet').addEventListener('click', e => { if (e.target.closest('[data-close]')) closeSheet(); });
document.addEventListener('keydown', e => { if (e.key === 'Escape' && !$('#sheet').hidden) closeSheet(); });
function sheetHead(title, sub) { return '<header><div><h3>' + title + '</h3>' + (sub ? '<p>' + sub + '</p>' : '') + '</div><button class="x" data-close="1" aria-label="닫기">' + icon('x') + '</button></header>'; }
function chips(name, opts, val) {
  return '<div class="chips" data-chips="' + name + '">' + opts.map(([v, l]) => '<button type="button" data-v="' + esc(v) + '" aria-pressed="' + (String(v) === String(val)) + '">' + esc(l) + '</button>').join('') + '</div>';
}
function bindChips(root, name, onPick) {
  root.querySelectorAll('[data-chips="' + name + '"] button').forEach(b => b.addEventListener('click', () => {
    root.querySelectorAll('[data-chips="' + name + '"] button').forEach(x => x.setAttribute('aria-pressed', x === b));
    onPick(b.dataset.v);
  }));
}

/* ---------- 기록 동작 ---------- */
const by = () => state.me || 'dad';
const running = () => state.events.filter(e => e.type === 'session' && !e.end).sort((a, b) => b.t - a.t)[0];
function suggestSide() {
  const last = state.events.filter(isNurse).sort((a, b) => b.t - a.t)[0];
  if (!last || !last.side || last.side === 'B') return 'L';
  return OTHER[last.side];
}
const lastOf = pred => { const e = state.events.filter(pred).sort((a, b) => b.t - a.t)[0]; return e || null; };
const isDFeed = e => (isNurse(e) && e.end) || (e.type === 'bottle' && e.baby === 'D');
const feedDesc = e => e.type === 'bottle' ? '젖병 ' + (e.milk === 'ebm' ? '모유 ' : '분유 ') + e.ml + 'ml' : kindDesc(e.kind, e.side);
function startSession(kind) {
  const side = kind === 'pump' ? 'B' : (state.side || suggestSide());
  state.side = null;
  return act(() => Store.addEvent({ type: 'session', kind, baby: kind === 'pump' ? null : 'D', side, t: Date.now(), end: null, by: state.me || 'mom' }));
}
function endSession(e) {
  const handoff = e.kind === 'nurse' ? '' : state.mode === 'db' ? ' 유축분 처리는 아빠 할 일로 넘겼어요.' : '';
  return act(() => Store.patchEvent(e, { end: Date.now(), endBy: state.me || 'mom' }), kindDesc(e.kind, e.side) + ' 기록했어요.' + handoff);
}
function offerUndo(label, fn) { state.undos = (state.undos || []).concat({ label, fn, until: Date.now() + 30000 }); render(); setTimeout(render, 30100); }
async function cancelSession(e) {
  if (await act(() => Store.patchEvent(e, { deleted: true }))) offerUndo('기록을 취소했어요', () => Store.patchEvent(e, { deleted: false }));
}
function undoBar() {
  state.undos = (state.undos || []).filter(x => Date.now() < x.until);
  const u = state.undos[state.undos.length - 1];
  if (!u) return '';
  const more = state.undos.length - 1;
  return '<div class="alert info">' + icon('swap') + '<div style="flex:1"><b>' + esc(u.label) + '</b>' + (more ? '<span>되돌릴 수 있는 기록이 ' + more + '개 더 있어요</span>' : '') + '</div><button class="sbtn" id="undo">되돌리기</button></div>';
}
function quickDiaper(wet, stool) { return act(() => Store.addEvent({ type: 'diaper', baby: 'D', wet, stool, t: Date.now(), by: by() }), NAME('D') + ' 기저귀(' + (wet && stool ? '소변+대변' : wet ? '소변' : '대변') + ')를 기록했어요'); }
function washDone(n) { return act(() => Store.addEvent({ type: 'wash', sets: n, t: Date.now(), by: by() }), '세척을 기록했어요'); }

/* ---------- 시트: 유축분 처리 ---------- */
function processSheet(e) {
  let L = Number(e.mlL) || 0, R = Number(e.mlR) || 0, dest = state.cfg.defaultDest || 'freezer';
  const ob = e.bagId && state.bags[e.bagId];
  let destTouched = false;
  if (ob) dest = ob.state === 'fridge' && ob.for === 'any' ? 'fridge-any' : (ob.state === 'fridge' || ob.state === 'freezer') ? ob.state : '';  // 해동·보냄·먹임은 아무것도 고르지 않음
  const html = sheetHead('유축한 양을 적어 주세요', fmtT(e.t) + ' ' + KIND[e.kind].label + ' · ' + fmtDur((e.end || Date.now()) - e.t) + ' · 젖병 눈금을 보고 입력해요') +
    '<div class="grid2">' +
    '<div class="plain"><p class="lab">왼쪽 ml</p><div class="stepper"><button data-s="L-" aria-label="왼쪽 10ml 빼기">−</button><output id="oL">' + L + '</output><button data-s="L+" aria-label="왼쪽 10ml 더하기">+</button></div></div>' +
    '<div class="plain"><p class="lab">오른쪽 ml</p><div class="stepper"><button data-s="R-" aria-label="오른쪽 10ml 빼기">−</button><output id="oR">' + R + '</output><button data-s="R+" aria-label="오른쪽 10ml 더하기">+</button></div></div></div>' +
    '<p>합계 <b id="oT">' + (L + R) + 'ml</b> · 봉투에 적을 코드 <span class="code">' + bagCode(e.end || e.t) + '</span></p>' +
    '<p class="lab">어디에 둘까요?</p>' + chips('dest', [['freezer', '냉동 · 아들용'], ['fridge', '냉장 · 아들용'], ['fridge-any', '냉장 · 딸도 가능'], ['nicu', 'NICU 바로 전달']], dest) +
    '<p class="xs muted">봉투에 코드·ml·"아들용"을 적고 납작하게 얼려요. 생후 ' + state.cfg.earlyDays + '일까지 짠 초기 모유는 아들 전용이에요.</p>' +
    '<button class="btn" id="save">저장하기</button>';
  openSheet(html, root => {
    const upd = () => { root.querySelector('#oL').textContent = L; root.querySelector('#oR').textContent = R; root.querySelector('#oT').textContent = (L + R) + 'ml'; };
    root.querySelectorAll('[data-s]').forEach(b => b.addEventListener('click', () => {
      const s = b.dataset.s, d = s[1] === '+' ? 10 : -10;
      if (s[0] === 'L') L = Math.max(0, L + d); else R = Math.max(0, R + d); upd();
    }));
    bindChips(root, 'dest', v => { dest = v; destTouched = true; });
    const old = e.bagId ? state.bags[e.bagId] : null;      // 다시 고치는 경우: 같은 팩을 갱신
    const prevTotal = sessionMl(e);
    const newBagId = uid(), nicuEvId = uid();               // 재시도해도 같은 id → 중복 없음
    root.querySelector('#save').addEventListener('click', async () => {
      const total = L + R, now = Date.now();
      const st = dest === 'fridge-any' ? 'fridge' : dest;
      if (!old && total > 0 && !dest) { toast('어디에 둘지 골라 주세요', true); return; }
      const ok = await act(async () => {
        let bagId = old ? old.id : (total > 0 ? newBagId : null);
        if (old) {
          // 팩의 현재 양에 '고친 만큼'만 더하고 뺌 (일부 쓴 팩의 남은 양을 원래 양으로 덮어쓰지 않음)
          const diff = total - prevTotal;
          const patch = { ml: Math.max(0, (Number(old.ml) || 0) + diff) };
          if (destTouched && ACTIVE.includes(old.state) && dest !== 'nicu') { patch.state = st; patch.for = dest === 'fridge-any' ? 'any' : 'S'; patch.stateAt = now; }
          if (patch.ml === 0 && ACTIVE.includes(old.state)) { patch.state = 'discard'; patch.stateAt = now; }
          await Store.patchBag(old.id, patch);
          if (old.state === 'nicu' && diff) {
            const sent = state.events.filter(x => x.type === 'nicu' && (x.bagIds || []).includes(old.id)).sort((a, b) => b.t - a.t)[0];
            if (sent) await Store.patchEvent(sent, { ml: Math.max(0, (Number(sent.ml) || 0) + diff) });
          }
        } else if (bagId) {
          await Store.setBag({ id: bagId, code: bagCode(e.end || e.t), ml: total, pumpedAt: e.end || e.t, for: dest === 'fridge-any' ? 'any' : 'S', state: st, stateAt: now, sessionId: e.id, by: by() });
          if (dest === 'nicu') await Store.addEvent({ id: nicuEvId, type: 'nicu', bagIds: [bagId], ml: total, t: now, by: by() });
        }
        await Store.patchEvent(e, { mlL: L, mlR: R, processed: true, procBy: by(), bagId });
      }, total + 'ml를 저장했어요');
      if (ok) closeSheet();
    });
  });
}

/* ---------- 시트: 딸 젖병 (미리 고른 값 없음: 양·종류를 직접 골라야 저장) ---------- */
function bottleSheet() {
  let ml = null, milk = null;
  const evId = uid();
  const draw = root => {
    const v = root.querySelector('#verdict');
    const a = allocate(state.bags, state.events, state.cfg, Date.now(), ml || 60);
    v.className = 'verdict ' + a.milk;
    v.innerHTML = bub(a.milk === 'ebm' ? 'milk' : 'bottle', a.milk === 'ebm' ? 'green' : 'amber') + '<div><b>' + (a.milk === 'ebm' ? '모유를 줘도 돼요' : '분유를 권해요') + (ml ? ' (' + ml + 'ml)' : '') + '</b><span>' + (a.milk === 'ebm' ? STATE_KO[a.bag.state] + ' <span class="code">' + esc(a.bag.code) + '</span> ' + a.bag.ml + 'ml부터' : '아들 몫을 먼저 채우는 중이에요') + '</span></div>';
    root.querySelector('#why').textContent = a.reason;
    root.querySelector('#warn').hidden = !(milk === 'ebm' && a.milk !== 'ebm');
    const sh = milk === 'ebm' && ml > 0 ? bottlePlan(a, ml).short : 0;
    root.querySelector('#short').hidden = !sh;
    if (sh) root.querySelector('#short b').textContent = '보관분이 ' + sh + 'ml 모자라요';
    const btn = root.querySelector('#save');
    btn.disabled = !(ml > 0 && milk);
    btn.textContent = ml > 0 && milk ? (milk === 'ebm' ? '모유 ' : '분유 ') + ml + 'ml 기록하기' : !ml ? '준 양을 골라 주세요' : '준 것을 골라 주세요';
    return a;
  };
  const html = sheetHead(NAME('D') + '에게 젖병을 줘요', '세워 안고, 젖병은 수평에 가깝게, 중간중간 쉬어 가며 (페이스드 피딩)') +
    '<div id="verdict" class="verdict"></div><details class="why"><summary>판정 근거</summary><p id="why"></p></details>' +
    '<p class="lab">실제로 준 것</p>' + chips('milk', [['ebm', '모유'], ['formula', '분유']], '') +
    '<p class="lab">실제로 준 양 (ml)</p>' + chips('ml', [30, 40, 50, 60, 70, 80, 90, 100, 120].map(v => [v, v]), '') +
    '<label class="f">목록에 없으면 직접 적기<input id="mlx" inputmode="numeric" pattern="[0-9]*" placeholder="예: 75"></label>' +
    '<div class="alert info" id="warn" hidden>' + icon('alert') + '<div><b>아들 예비분에서 꺼내게 돼요</b><span>정말 모유를 줬을 때만 고르세요.</span></div></div>' +
    '<div class="alert info" id="short" hidden>' + icon('alert') + '<div><b></b><span>막 짠 모유를 바로 줬다면 그대로 기록하세요. 보관분에서는 있는 만큼만 빼요.</span></div></div>' +
    '<button class="btn" id="save" disabled>준 양을 골라 주세요</button>';
  openSheet(html, root => {
    draw(root);
    bindChips(root, 'ml', v => { ml = Number(v); root.querySelector('#mlx').value = ''; draw(root); });
    bindChips(root, 'milk', v => { milk = v; draw(root); });
    root.querySelector('#mlx').addEventListener('input', ev => {
      const x = Number(ev.target.value); ml = x > 0 && x < 400 ? x : null;
      root.querySelectorAll('[data-chips="ml"] button').forEach(c => c.setAttribute('aria-pressed', 'false')); draw(root);
    });
    let plan = null, busy = false;
    root.querySelector('#save').addEventListener('click', async () => {
      if (!(ml > 0 && milk) || busy) return;
      // 첫 클릭에서 '어느 팩에서 얼마나'를 정해 두고, 재시도해도 같은 계획을 씀 (두 번 차감 방지)
      if (!plan || plan.ml !== ml || plan.milk !== milk) plan = { ml, milk, t: Date.now(), patches: milk === 'ebm' ? bottlePlan(draw(root), ml) : [] };
      busy = true; const btn = root.querySelector('#save'); btn.disabled = true;
      const ok = await act(async () => {
        const ev = { id: evId, type: 'bottle', baby: 'D', ml, milk, bagId: plan.patches[0] ? plan.patches[0].id : null, bagIds: plan.patches.map(p => p.id), t: plan.t, by: by() };
        if (plan.patches.length) { ev.plan = plan.patches.map(p => ({ id: p.id, use: p.use })); ev.applied = false; }
        reconciled.add(evId);   // 지금 이 시트가 직접 반영하는 중: 자동 반영과 겹치지 않게
        await Store.addEvent(ev);
        await applyBottlePlan(ev);
      }, NAME('D') + ' ' + (milk === 'ebm' ? '모유' : '분유') + ' ' + ml + 'ml를 기록했어요' + (plan.patches.short ? ' (보관분에서 ' + (ml - plan.patches.short) + 'ml만 뺐어요)' : ''));
      busy = false;
      if (ok) closeSheet(); else { reconciled.delete(evId); draw(root); }
    });
  });
}
// 젖병에 쓸 팩들: 판정이 고른 팩부터, 모자라면 최근에 짠 팩 순서로 이어서. 남은 양은 해동 상태로 재고에 남김
function bottlePlan(a, ml) {
  const now = Date.now();
  const inv = inventory(state.bags, state.events, state.cfg, now);
  const earlyEnd = birthTime(state.cfg) + state.cfg.earlyDays * DAY;   // 초기 모유는 아들 전용: 딸 젖병에서 절대 빼지 않음
  const order = inv.avail.filter(b => b.pumpedAt >= earlyEnd || b.for === 'any').sort((x, y) => y.pumpedAt - x.pumpedAt);
  if (a.bag) order.sort((x, y) => (y.id === a.bag.id) - (x.id === a.bag.id));
  const out = []; let rest = ml;
  for (const b of order) {
    if (rest <= 0) break;
    const have = Number(b.ml) || 0, use = Math.min(have, rest); rest -= use;
    if (use > 0) out.push({ id: b.id, use });
  }
  out.short = Math.max(0, rest);   // 보관분에서 못 뺀 양 (막 짠 모유를 바로 준 경우 등)
  return out;
}
async function applyBottlePlan(ev) {
  if (!ev.plan || ev.applied) return true;
  if (ev.plan.some(p => !state.bags[p.id])) return false;            // 팩 목록이 아직 안 들어왔으면 나중에
  const now = Date.now();
  for (const p of ev.plan) {
    const b = state.bags[p.id];
    if (b.used && b.used[ev.id]) continue;                            // 이미 이 젖병만큼 뺐음
    const used = Object.assign({}, b.used, { [ev.id]: p.use });
    if (!ACTIVE.includes(b.state)) { await Store.patchBag(p.id, { used }); continue; }   // 그사이 보냈거나 다 쓴 팩은 표시만
    const left = (Number(b.ml) || 0) - p.use;                          // 지금 남은 양에서 뺌 (덮어쓰지 않음)
    await Store.patchBag(p.id, left > 0
      ? { used, ml: left, state: b.state === 'freezer' ? 'thawed' : b.state, stateAt: b.state === 'freezer' ? now : (b.stateAt || now) }
      : { used, state: 'used', stateAt: now, usedFor: 'D' });
  }
  await Store.patchEvent(ev, { applied: true });
  return true;
}
const reconciled = new Set();
function reconcileBottles() {
  // 기록은 됐는데 팩 차감이 중간에 실패한 젖병(24시간 이내)을 다시 반영. 값이 절대값이라 여러 번 해도 같음
  for (const e of state.events) if (e.type === 'bottle' && e.plan && e.applied === false && Date.now() - e.t < DAY && !reconciled.has(e.id)) {
    reconciled.add(e.id); applyBottlePlan(e).then(done => { if (!done) reconciled.delete(e.id); }, () => reconciled.delete(e.id));
  }
}
function allocBagAny() {
  const inv = inventory(state.bags, state.events, state.cfg, Date.now());
  return inv.avail.slice().sort((a, b) => b.pumpedAt - a.pumpedAt)[0] || null;
}

/* ---------- 시트: 체중·처방·엄마 상태·메모 ---------- */
function weightSheet(baby) {
  let src = baby === 'S' ? 'nicu' : 'home';
  const wid = uid();
  openSheet(sheetHead(NAME(baby) + ' 체중을 적어 주세요', '같은 체중계로, 수유 전·기저귀 벗고 재면 추세가 정확해요') +
    '<label class="f">체중 (g)<input id="g" inputmode="numeric" pattern="[0-9]*" placeholder="예: 2850"></label>' +
    '<p class="lab">어디서 쟀나요?</p>' + chips('src', [['home', '집'], ['nicu', 'NICU'], ['clinic', '소아과']], src) +
    '<button class="btn" id="save">기록하기</button>', root => {
    bindChips(root, 'src', v => { src = v; });
    root.querySelector('#g').focus();
    root.querySelector('#save').addEventListener('click', async () => {
      const g = Number(root.querySelector('#g').value);
      if (!(g > 1000 && g < 10000)) { toast('그램 단위로 적어 주세요 (예: 2850)', true); return; }
      if (await act(() => Store.addEvent({ id: wid, type: 'weight', baby, g, src, t: Date.now(), by: by() }), NAME(baby) + ' ' + n0(g) + 'g을 기록했어요')) closeSheet();
    });
  });
}
function orderSheet() {
  const lo = latestOrder(state.events, Date.now());
  let per = lo && lo.perFeed ? Number(lo.perFeed) : 10, times = lo && lo.times ? Number(lo.times) : 8;
  const g = need(state.events, state.cfg, 'S').g, oid = uid();
  openSheet(sheetHead(NAME('S') + ' 오늘 처방을 적어 주세요', '바뀔 때마다 적으면 늘어나는 모습이 그래프로 남아요') +
    '<p class="lab">한 번에 몇 ml?</p><div class="stepper"><button data-s="-" aria-label="5ml 빼기">−</button><output id="oP">' + per + '</output><button data-s="+" aria-label="5ml 더하기">+</button></div>' +
    '<p class="lab">하루 몇 번?</p>' + chips('times', [1, 2, 3, 4, 6, 8, 12].map(v => [v, v + '번']), times) +
    '<div class="verdict ebm" id="oSum"></div>' +
    '<label class="f">메모 (수액 변화, 의사 말)<input id="onote" placeholder="예: 수액 줄이기 시작"></label>' +
    '<button class="btn" id="save">기록하기</button>', root => {
    const upd = () => {
      root.querySelector('#oP').textContent = per;
      const day = per * times, perKg = Math.round(day / (g / 1000));
      root.querySelector('#oSum').innerHTML = bub('clip', 'boy') + '<div><b>하루 ' + day + 'ml</b><span>' + perKg + 'ml/kg · 완전수유의 ' + Math.round(perKg / state.cfg.mlPerKg * 100) + '% (체중 ' + n0(g) + 'g)</span></div>';
    };
    upd();
    root.querySelectorAll('[data-s]').forEach(b => b.addEventListener('click', () => { per = Math.max(0, per + (b.dataset.s === '+' ? 5 : -5)); upd(); }));
    bindChips(root, 'times', v => { times = Number(v); upd(); });
    root.querySelector('#save').addEventListener('click', async () => {
      const note = root.querySelector('#onote').value.trim();
      const ev = { id: oid, type: 'order', baby: 'S', perFeed: per, times, ml: per * times, t: Date.now(), by: by() };
      if (note) ev.note = note;
      if (await act(() => Store.addEvent(ev), NAME('S') + ' 처방 ' + per + 'ml×' + times + '번을 기록했어요')) closeSheet();
    });
  });
}
function momSheet() {
  let pain = '', breast = 'ok', e10 = '';
  const mid = uid();
  openSheet(sheetHead('엄마 몸 상태를 적어요', '아는 칸만 채워도 돼요. K-EPDS는 보건소·국가정신건강정보포털의 공식 문항으로 하고 점수만 적어요') +
    '<p class="lab">수유할 때 통증 (0–10)</p>' + chips('pain', [0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10].map(v => [v, v]), pain) +
    '<div class="grid2"><label class="f">체온 °C<input id="temp" inputmode="decimal" placeholder="36.8"></label><label class="f">K-EPDS 총점<input id="epds" inputmode="numeric" placeholder="0–30"></label></div>' +
    '<p class="lab">가슴 상태</p>' + chips('breast', [['ok', '괜찮아요'], ['firm', '뭉쳤어요'], ['red', '붉고 아파요']], breast) +
    '<p class="lab">K-EPDS 10번 문항(자해 생각) 점수</p>' + chips('e10', [[0, '0'], [1, '1'], [2, '2'], [3, '3']], e10) +
    '<div class="alert now" id="e10w" hidden>' + icon('alert') + '<div><b>오늘 바로 연락하세요: 109 (24시간)</b><span>위급하면 119. 10번 문항이 1점 이상이면 총점과 상관없이 바로 도움을 받아요.</span></div></div>' +
    '<button class="btn" id="save">기록하기</button>', root => {
    bindChips(root, 'pain', v => { pain = Number(v); });
    bindChips(root, 'breast', v => { breast = v; });
    bindChips(root, 'e10', v => { e10 = Number(v); root.querySelector('#e10w').hidden = !(e10 >= 1); });
    root.querySelector('#save').addEventListener('click', async () => {
      const temp = root.querySelector('#temp').value.trim(), epds = root.querySelector('#epds').value.trim();
      const ev = { id: mid, type: 'momcheck', t: Date.now(), by: by(), breast };
      if (pain !== '') ev.pain = pain;
      if (temp) ev.temp = Number(temp);
      if (epds) ev.epds = Number(epds);
      if (e10 !== '') ev.epds10 = e10;
      if (await act(() => Store.addEvent(ev), '엄마 상태를 기록했어요')) closeSheet();
    });
  });
}
function noteSheet() {
  const nid = uid();
  openSheet(sheetHead('메모를 남겨요', 'NICU 처방 변경, 의사 말, 아내가 한 말 등') + '<textarea id="txt" rows="4"></textarea><button class="btn" id="save">저장하기</button>', root => {
    root.querySelector('#txt').focus();
    root.querySelector('#save').addEventListener('click', async () => {
      const text = root.querySelector('#txt').value.trim(); if (!text) return closeSheet();
      if (await act(() => Store.addEvent({ id: nid, type: 'note', text, t: Date.now(), by: by() }), '메모를 저장했어요')) closeSheet();
    });
  });
}
function addSheet() {
  const item = (q, ic, tone, t, d) => '<button class="li" data-add="' + q + '">' + bub(ic, tone) + '<span class="tx"><span class="t">' + t + '</span><span class="d">' + d + '</span></span>' + icon('chev', 'chev') + '</button>';
  openSheet(sheetHead('무엇을 기록할까요?') + '<div>' +
    item('weightD', 'scale', 'girl', NAME('D') + ' 체중', '집·소아과에서 잰 체중') +
    item('weightS', 'scale', 'boy', NAME('S') + ' 체중', 'NICU에서 들은 체중') +
    item('order', 'clip', 'boy', NAME('S') + ' NICU 처방', '한 번에 몇 ml × 하루 몇 번') +
    item('mom', 'heart', 'red', '엄마 몸 상태', '통증·체온·가슴·K-EPDS') +
    item('note', 'note', '', '메모', '의사 말, 처방 변경 이유') +
    item('startNP', 'both', 'blue', '엄마 대신 시작: 직수 + 유축', '엄마가 부탁할 때') +
    item('startN', 'nurse', 'girl', '엄마 대신 시작: 직수만', '') +
    item('startP', 'pump', 'violet', '엄마 대신 시작: 유축만', '') +
    '</div>', root => {
    root.querySelectorAll('[data-add]').forEach(b => b.addEventListener('click', () => {
      const a = b.dataset.add;
      if (a === 'weightD') weightSheet('D'); else if (a === 'weightS') weightSheet('S'); else if (a === 'order') orderSheet();
      else if (a === 'mom') momSheet(); else if (a === 'note') noteSheet();
      else { closeSheet(); startSession(a === 'startNP' ? 'nurse+pump' : a === 'startN' ? 'nurse' : 'pump'); }
    }));
  });
}
function bagSheet(b) {
  const x = bagExpiry(b, state.cfg);
  const opts = [];
  if (b.state === 'fridge') opts.push(['freezer', '냉동하기', 'snow', 'blue'], ['nicu', 'NICU에 보냈어요', 'cooler', 'boy']);
  if (b.state === 'freezer') opts.push(['thawed', '냉장 해동 시작', 'fridge', 'blue'], ['nicu', 'NICU에 보냈어요', 'cooler', 'boy']);
  if (b.state === 'thawed') opts.push(['nicu', 'NICU에 보냈어요', 'cooler', 'boy']);
  opts.push(['used', NAME('D') + '에게 먹였어요', 'bottle', 'girl'], ['discard', '버렸어요', 'alert', 'red']);
  openSheet(sheetHead('<span class="code">' + esc(b.code) + '</span> ' + b.ml + 'ml', STATE_KO[b.state] + ' · ' + (b.for === 'S' ? '아들용' : '딸도 가능') + (x ? ' · ' + fmtMD(x) + ' ' + fmtT(x) + '까지' : '')) +
    '<div>' + opts.map(([v, l, ic, tone]) => '<button class="li" data-to="' + v + '">' + bub(ic, tone) + '<span class="tx"><span class="t">' + l + '</span></span>' + icon('chev', 'chev') + '</button>').join('') +
    '<button class="li" data-for="' + (b.for === 'S' ? 'any' : 'S') + '">' + bub('swap', '') + '<span class="tx"><span class="t">' + (b.for === 'S' ? '딸도 먹을 수 있게 바꾸기' : '아들용으로 바꾸기') + '</span></span>' + icon('chev', 'chev') + '</button></div>', root => {
    root.querySelectorAll('[data-to]').forEach(btn => btn.addEventListener('click', async () => {
      const to = btn.dataset.to, now = Date.now();
      if (await act(async () => {
        await Store.patchBag(b.id, { state: to, stateAt: now });
        if (to === 'nicu') await Store.addEvent({ type: 'nicu', bagIds: [b.id], ml: b.ml, t: now, by: by() });
        if (to === 'used') await Store.addEvent({ type: 'bottle', baby: 'D', ml: b.ml, milk: 'ebm', bagId: b.id, t: now, by: by() });
      }, STATE_KO[to] + '(으)로 바꿨어요')) closeSheet();
    }));
    root.querySelectorAll('[data-for]').forEach(btn => btn.addEventListener('click', async () => { await act(() => Store.patchBag(b.id, { for: btn.dataset.for }), '바꿨어요'); closeSheet(); }));
  });
}
function sendSheet() {
  const now = Date.now(), cfg = state.cfg;
  const inv = inventory(state.bags, state.events, cfg, now);
  const list = inv.avail.filter(b => b.state !== 'thawed').sort((a, b) => ((a.for === 'S' ? 0 : 1) - (b.for === 'S' ? 0 : 1)) || ((a.state === 'freezer' ? 0 : 1) - (b.state === 'freezer' ? 0 : 1)) || (a.pumpedAt - b.pumpedAt));
  const picked = new Set(), sendId = uid();
  const draw = root => {
    const sel = list.filter(b => picked.has(b.id));
    const btn = root.querySelector('#send');
    btn.disabled = !sel.length;
    btn.textContent = sel.length ? sel.length + '팩 · ' + sel.reduce((s, b) => s + b.ml, 0) + 'ml 보냈어요' : '보낼 모유를 골라 주세요';
  };
  openSheet(sheetHead('NICU에 보낼 모유를 골라요', '아들용 냉동부터, 먼저 짠 순서로 보여요. 병원 규정(용기·라벨·반입 시간)이 우선이에요') +
    (list.length ? '<div>' + list.map(b => '<button class="li pick" data-pick="' + b.id + '" aria-pressed="false"><span class="ck">' + icon('check') + '</span><span class="tx"><span class="t"><span class="code">' + esc(b.code) + '</span> ' + b.ml + 'ml</span><span class="d">' + STATE_KO[b.state] + ' · ' + (b.for === 'S' ? '아들용' : '딸도 가능') + '</span></span></button>').join('') + '</div>'
      : '<div class="empty">' + bub('milk', '') + '<b>보낼 모유가 없어요</b></div>') +
    '<div class="sheet-foot"><button class="btn" id="send" disabled>보낼 모유를 골라 주세요</button></div>', root => {
    root.querySelectorAll('[data-pick]').forEach(b => b.addEventListener('click', () => {
      const id = b.dataset.pick; if (picked.has(id)) picked.delete(id); else picked.add(id);
      b.setAttribute('aria-pressed', picked.has(id)); draw(root);
    }));
    root.querySelector('#send').addEventListener('click', async () => {
      const sel = list.filter(b => picked.has(b.id)); if (!sel.length) return;
      const t = Date.now(), ml = sel.reduce((s, x) => s + x.ml, 0);
      if (await act(async () => { for (const x of sel) await Store.patchBag(x.id, { state: 'nicu', stateAt: t }); await Store.addEvent({ id: sendId, type: 'nicu', bagIds: sel.map(x => x.id), ml, t, by: by() }); }, 'NICU에 ' + ml + 'ml 보낸 걸 기록했어요')) closeSheet();
    });
    draw(root);
  });
}
function eventSheet(e) {
  const vol = e.type === 'session' && e.end && e.kind !== 'nurse';
  openSheet(sheetHead(esc(describe(e)), fmtMD(e.t) + ' ' + fmtT(e.t) + ' · ' + (e.by === 'mom' ? '엄마' : e.by === 'dad' ? '아빠' : esc(e.by)) + '가 기록') +
    '<div>' + (vol ? '<button class="li" id="vol">' + bub('pump', 'violet') + '<span class="tx"><span class="t">유축한 양 ' + (e.processed ? '고치기' : '적기') + '</span></span>' + icon('chev', 'chev') + '</button>' : '') +
    '<button class="li" id="del">' + bub('alert', 'red') + '<span class="tx"><span class="t">이 기록 지우기</span></span>' + icon('chev', 'chev') + '</button></div>', root => {
    const v = root.querySelector('#vol'); if (v) v.addEventListener('click', () => processSheet(e));
    root.querySelector('#del').addEventListener('click', async () => { if (await act(() => Store.patchEvent(e, { deleted: true }))) { closeSheet(); offerUndo('기록을 지웠어요', () => Store.patchEvent(e, { deleted: false })); } });
  });
}
function describe(e) {
  switch (e.type) {
    case 'session': return NAME('D') && e.kind !== 'pump' ? NAME('D') + ' ' + kindDesc(e.kind, e.side) + (e.end ? ' ' + fmtDur(e.end - e.t) : ' 중') + (e.processed ? ' · ' + sessionMl(e) + 'ml' : '') : '양쪽 유축' + (e.end ? ' ' + fmtDur(e.end - e.t) : ' 중') + (e.processed ? ' · ' + sessionMl(e) + 'ml' : '');
    case 'bottle': return NAME(e.baby) + ' 젖병 ' + (e.milk === 'ebm' ? '모유 ' : '분유 ') + e.ml + 'ml';
    case 'diaper': return NAME(e.baby) + ' 기저귀 ' + (e.wet && e.stool ? '소변+대변' : e.wet ? '소변' : '대변');
    case 'weight': return NAME(e.baby) + ' 체중 ' + n0(e.g) + 'g';
    case 'nicu': return 'NICU에 모유 ' + e.ml + 'ml 보냄';
    case 'wash': return '유축 부품 세척';
    case 'momcheck': return '엄마 상태' + (e.temp ? ' ' + e.temp + '°C' : '') + (e.pain !== undefined ? ' · 통증 ' + e.pain : '') + (e.epds !== undefined ? ' · EPDS ' + e.epds : '');
    case 'note': return e.text;
    case 'order': return NAME('S') + ' 처방 ' + (e.perFeed ? e.perFeed + 'ml×' + e.times + '번 = ' : '') + e.ml + 'ml/일' + (e.note ? ' · ' + e.note : '');
    default: return e.type;
  }
}
function eventIcon(e) {
  switch (e.type) {
    case 'session': return KIND[e.kind] ? [KIND[e.kind].ic, KIND[e.kind].tone] : ['clock', ''];
    case 'bottle': return ['bottle', 'girl'];
    case 'diaper': return e.stool ? ['poop', 'amber'] : ['pee', 'blue'];
    case 'weight': return ['scale', e.baby === 'S' ? 'boy' : 'girl'];
    case 'nicu': return ['cooler', 'boy'];
    case 'wash': return ['wash', 'blue'];
    case 'momcheck': return ['heart', 'red'];
    case 'order': return ['clip', 'boy'];
    default: return ['note', ''];
  }
}

/* ---------- 설정 ---------- */
function settingsSheet() {
  const c = state.cfg;
  const f = (id, label, val, mode, hint) => '<label class="f">' + label + '<input id="' + id + '" value="' + esc(val) + '"' + (mode ? ' inputmode="' + mode + '"' : '') + '>' + (hint ? '<span class="xs muted">' + hint + '</span>' : '') + '</label>';
  const grp = (ic, tone, title, body, open) => '<details class="grp"' + (open ? ' open' : '') + '><summary>' + bub(ic, tone) + title + icon('chev', 'chev') + '</summary><div class="body">' + body + '<button class="btn weak" data-savecfg="1">저장하기</button></div></details>';
  const modeTxt = { db: '공유 중이에요. 이 링크를 연 가족 모두 같은 기록을 봐요.', 'db-wait': '공유 저장소에 연결하는 중이에요.', 'db-slow': '공유 저장소 응답이 늦어요. 연결되면 반영돼요.', 'db-error': '공유 저장소에 문제가 있어요 (' + esc(state.err || '') + ').', local: '이 폰에만 저장 중이에요. 상대 폰에는 보이지 않아요.', loading: '불러오는 중이에요.' }[state.mode];
  openSheet(sheetHead('설정') +
    '<div class="li">' + bub('phone', 'blue') + '<span class="tx"><span class="t">이 폰은 누가 쓰나요?</span><span class="d">폰마다 따로 기억해요</span></span></div>' +
    '<div class="row2"><button class="btn ' + (state.me === 'mom' ? '' : 'gray') + '" data-role="mom">엄마</button><button class="btn ' + (state.me === 'dad' ? '' : 'gray') + '" data-role="dad">아빠</button></div>' +
    '<div>' +
    grp('clip', 'boy', NAME('S') + ' 모유 계획',
      '<div class="grid2">' + f('reserveDays', '예비분 (완전수유 며칠치)', c.reserveDays, 'decimal') + f('pumpBuffer', '유축 목표 배수', c.pumpBuffer, 'decimal', '완전수유 필요량 × 이 값') +
      f('earlyDays', '아들 전용 초기 모유 (생후 며칠까지)', c.earlyDays, 'numeric') + f('mlPerKg', '완전수유 ml/kg/일', c.mlPerKg, 'numeric') + '</div>' +
      '<label class="f">유축분 기본 보관<select id="defaultDest"><option value="freezer"' + (c.defaultDest === 'freezer' ? ' selected' : '') + '>냉동 (NICU 냉동 전달)</option><option value="fridge"' + (c.defaultDest === 'fridge' ? ' selected' : '') + '>냉장</option></select></label>') +
    grp('snow', 'blue', '보관 기한',
      '<div class="grid2">' + f('nicuFridgeH', 'NICU용 냉장 (시간)', c.nicuFridgeH, 'numeric', '병원 규정으로') + f('homeFridgeH', '집용 냉장 (시간)', c.homeFridgeH, 'numeric', 'CDC·ABM 96시간') +
      f('freezerD', '냉동 (일)', c.freezerD, 'numeric', '권장 180일') + f('thawedH', '해동 후 (시간)', c.thawedH, 'numeric') +
      f('roomH', '실온 처리 기한 (시간)', c.roomH, 'numeric') + f('spareSets', '유축 부품 세트 수', c.spareSets, 'numeric') + '</div>') +
    grp('moon', 'violet', '밤 교대 시간',
      '<div class="grid2">' + f('momStart', '엄마 푹 자는 시작', c.momSleep.start) + f('momEnd', '엄마 푹 자는 끝', c.momSleep.end) +
      f('dadStart', '아빠 자는 시작 (알림 무음)', c.dadSleep.start) + f('dadEnd', '아빠 자는 끝', c.dadSleep.end) + '</div>') +
    grp('alert', 'amber', '연락 기준값',
      '<p class="xs muted">소아과·산과에서 숫자를 확인받은 뒤 고치고 아래 스위치를 켜 주세요.</p><div class="grid2">' +
      f('wetMin', NAME('D') + ' 소변 최소 (24시간)', c.th.wetMin, 'numeric') + f('stoolMin', NAME('D') + ' 대변 최소', c.th.stoolMin, 'numeric') +
      f('feedsMin', NAME('D') + ' 수유 최소 횟수', c.th.feedsMin, 'numeric') + f('feedGapH', NAME('D') + ' 최대 수유 간격 (시간)', c.th.feedGapH, 'decimal') +
      f('gainMin', NAME('D') + ' 최소 증가 (g/일, 0=끔)', c.th.gainMin, 'numeric') + f('momTemp', '엄마 체온 기준 °C', c.th.momTemp, 'decimal') +
      f('removalsMin', '젖 비우기 목표 (회)', c.th.removalsMin, 'numeric') + f('maxGapH', '가장 긴 공백 목표 (시간)', c.th.maxGapH, 'decimal') +
      f('epdsTh', 'K-EPDS 기준 점수', c.th.epds, 'numeric') + '</div>' +
      '<div class="li"><span class="tx"><span class="t">소아과 확인 완료</span></span><button class="switch" id="confirmed" role="switch" aria-checked="' + !!c.th.confirmed + '" aria-label="소아과 확인 완료"></button></div>') +
    grp('babies', 'girl', '아기 정보',
      '<div class="grid2">' + f('nameD', '첫째 이름', c.names.D) + f('nameS', '둘째 이름', c.names.S) + f('birthD', '첫째 출생체중 g', c.birthG.D, 'numeric') + f('birthS', '둘째 출생체중 g', c.birthG.S, 'numeric') + '</div>') +
    '</div>' +
    '<div class="li">' + bub(state.mode === 'db' ? 'check' : 'alert', state.mode === 'db' ? 'green' : 'amber') + '<span class="tx"><span class="t">저장 상태</span><span class="d">' + modeTxt + '</span></span></div>' +
    '<p class="xs muted">아내도 같은 기록을 쓰려면 이 페이지를 공유하고 편집 권한을 주세요.</p>', root => {
    root.querySelectorAll('[data-role]').forEach(b => b.addEventListener('click', () => { state.me = b.dataset.role; ls.set('tf.me', state.me); state.tab = null; validTab(); closeSheet(); }));
    const sw = root.querySelector('#confirmed'); sw.addEventListener('click', () => sw.setAttribute('aria-checked', sw.getAttribute('aria-checked') !== 'true'));
    root.querySelectorAll('[data-savecfg]').forEach(b => b.addEventListener('click', () => saveSettings(root)));
  });
}
function saveSettings(root) {
  const v = id => { const el = root.querySelector('#' + id); return el ? el.value.trim() : ''; };
  const n = (id, d) => { const x = Number(v(id)); return v(id) !== '' && Number.isFinite(x) ? x : d; };
  const hm = (id, d) => /^\d{1,2}:\d{2}$/.test(v(id)) ? v(id).padStart(5, '0') : d;
  const c = state.cfg;
  const cfg = {
    birthDate: c.birthDate, names: { D: v('nameD') || c.names.D, S: v('nameS') || c.names.S },
    birthG: { D: n('birthD', c.birthG.D), S: n('birthS', c.birthG.S) },
    sonOrderMl: c.sonOrderMl || 0, mlPerKg: n('mlPerKg', c.mlPerKg), reserveDays: n('reserveDays', c.reserveDays), pumpBuffer: n('pumpBuffer', c.pumpBuffer),
    earlyDays: n('earlyDays', c.earlyDays), defaultDest: v('defaultDest') || c.defaultDest,
    roomH: n('roomH', c.roomH), homeFridgeH: n('homeFridgeH', c.homeFridgeH), nicuFridgeH: n('nicuFridgeH', c.nicuFridgeH), freezerD: n('freezerD', c.freezerD), thawedH: n('thawedH', c.thawedH),
    momSleep: { start: hm('momStart', c.momSleep.start), end: hm('momEnd', c.momSleep.end) }, dadSleep: { start: hm('dadStart', c.dadSleep.start), end: hm('dadEnd', c.dadSleep.end) },
    spareSets: n('spareSets', c.spareSets),
    th: { confirmed: root.querySelector('#confirmed').getAttribute('aria-checked') === 'true', removalsMin: n('removalsMin', c.th.removalsMin), maxGapH: n('maxGapH', c.th.maxGapH), wetMin: n('wetMin', c.th.wetMin), stoolMin: n('stoolMin', c.th.stoolMin), feedsMin: n('feedsMin', c.th.feedsMin), feedGapH: n('feedGapH', c.th.feedGapH), momTemp: n('momTemp', c.th.momTemp), epds: n('epdsTh', c.th.epds), gainMin: n('gainMin', c.th.gainMin) },
  };
  act(() => Store.setConfig(cfg), '설정을 저장했어요');
}

/* ---------- 공통 조각 ---------- */
function syncBanner() {
  if (state.mode === 'db' || state.mode === 'db-wait' || state.mode === 'loading') return '';
  const msg = state.mode === 'local' ? '이 폰에만 저장돼요. 상대 폰에는 보이지 않아요.' : state.mode === 'db-slow' ? '공유 저장소 응답이 늦어요. 연결되면 반영돼요.' : '공유 저장소에 문제가 있어요. 설정에서 상태를 확인해 주세요.';
  return '<div class="alert info">' + icon('phone') + '<div><b>' + msg + '</b></div></div>';
}
function flagsBlock(list) {
  if (!list.length) return '';
  const now = list.filter(f => f.level === 'now' || f.level === 'today');
  const rest = list.filter(f => f.level !== 'now' && f.level !== 'today');
  const lv = { now: '지금 연락', today: '오늘 연락', visit: '진료 때 상의', plan: '공급 관리' };
  let h = now.map(f => '<div class="alert ' + (f.level === 'now' ? 'now' : 'info') + '">' + icon('alert') + '<div><b>' + lv[f.level] + ' · ' + esc(f.text) + '</b><span>' + esc(f.act) + '</span></div></div>').join('');
  if (now.length && !state.cfg.th.confirmed && !rest.length) h += '<p class="foot">기준값은 소아과 확인 전 기본값이에요.</p>';
  if (rest.length) h += '<details class="fold"><summary>' + icon('alert') + '확인할 것 ' + rest.length + '개' + icon('chev', 'chev') + '</summary><div class="items">' +
    rest.map(f => '<div><b>' + lv[f.level] + ' · ' + esc(f.text) + '</b>' + esc(f.act) + '</div>').join('') +
    (state.cfg.th.confirmed ? '' : '<div class="xs muted">기준값은 소아과 확인 전 기본값이에요.</div>') + '</div></details>';
  return h;
}
function title(h1, p) { return '<div class="title"><h1>' + h1 + '</h1>' + (p ? '<p>' + p + '</p>' : '') + '</div>'; }

/* ---------- 화면: 역할 고르기 ---------- */
function viewRole() {
  return title('이 폰은 누가 쓰나요?', '엄마 폰은 수유와 기저귀를 빠르게 기록하고, 아빠 폰은 할 일이 먼저 보여요. 설정에서 언제든 바꿀 수 있어요.') +
    '<div class="role"><button class="act" data-role="mom">' + bub('nurse', 'girl') + '<span class="tx"><b>엄마예요</b><span class="d">수유 시작·끝과 기저귀만 누르면 돼요</span></span></button>' +
    '<button class="act" data-role="dad">' + bub('todo', 'blue') + '<span class="tx"><b>아빠예요</b><span class="d">유축분 처리·NICU 배송·기저귀를 맡아요</span></span></button></div>';
}

/* ---------- 화면: 엄마 수유 ---------- */
function viewFeed() {
  const now = Date.now(), r = running(), st = stats24(state.events, now, state.cfg);
  const lastFeed = lastOf(isDFeed);
  let h = '<div class="feed">';
  if (r) {
    h += title(kindDesc(r.kind, r.side) + ' 중이에요', fmtT(r.t) + '에 시작했어요');
    h += syncBanner() + '<div class="spacer"></div>';
    h += '<div class="card">' + '<div class="li" style="min-height:auto">' + bub(KIND[r.kind].ic, KIND[r.kind].tone) + '<span class="tx"><span class="t">' + KIND[r.kind].label + '</span><span class="d">' + kindDesc(r.kind, r.side) + '</span></span></div>' +
      '<div class="timer" id="clock">00:00</div>' +
      '<button class="btn" data-end="' + r.id + '">끝내기</button>' +
      '<button class="btn gray" data-cancel="' + r.id + '">잘못 눌렀어요 · 기록 취소</button></div>';
  } else {
    const sug = state.side || suggestSide();
    h += title(SIDE_KO[sug] + '부터 먹일 차례예요');
    h += syncBanner();
    h += '<div class="card tight"><div class="li">' + bub('clock', st.removals >= state.cfg.th.removalsMin ? 'green' : 'blue') + '<span class="tx"><span class="t">' + NAME('D') + ' 마지막 수유 ' + (lastFeed ? fmtAgo(lastFeed.end || lastFeed.t) : '기록 없음') + '</span><span class="d">24시간 젖 비우기 ' + st.removals + ' / ' + state.cfg.th.removalsMin + '회</span></span></div></div>';
    h += '<div class="spacer"></div>';
    h += '<div class="card"><p class="lab">직수할 쪽</p><div class="sides">' +
      ['L', 'R'].map(s => '<button class="side" data-side="' + s + '" aria-pressed="' + (sug === s) + '">' + (sug === s ? icon('check') : '') + SIDE_KO[s] + '</button>').join('') + '</div>' +
      '<button class="act" data-start="nurse">' + bub('nurse', 'girl') + '<span class="tx"><b>직수만</b><span class="d">' + kindDesc('nurse', sug) + '</span></span></button>' +
      '<button class="act" data-start="nurse+pump">' + bub('both', 'blue') + '<span class="tx"><b>직수 + 유축</b><span class="d">' + kindDesc('nurse+pump', sug) + '</span></span></button>' +
      '<button class="act" data-start="pump">' + bub('pump', 'violet') + '<span class="tx"><b>유축만</b><span class="d">양쪽 유축</span></span></button></div>';
  }
  h += '<div class="quick">' + qk('wet', 'pee', 'pee', '소변') + qk('stool', 'poop', 'poop', '대변') + qk('both', 'both', 'diaper', '둘 다') + '</div>';
  return h + '</div>';
}
function qk(q, cls, ic, label) { return '<button class="qk ' + cls + '" data-q="' + q + '">' + icon(ic) + label + '</button>'; }

/* ---------- 화면: 아빠 할 일 ---------- */
function viewTodo() {
  const now = Date.now(), r = running();
  const tk = tasks(state.events, state.bags, state.cfg, now).filter(t => t.kind !== 'running');
  const fl = flags(state.events, state.cfg, now);
  let h = title(tk.length ? '할 일이 ' + tk.length + '개 있어요' : '지금은 할 일이 없어요', tk.length ? '위에서부터 처리하면 돼요' : '엄마가 유축을 끝내면 여기에 처리할 일이 생겨요');
  h += syncBanner();
  h += flagsBlock(fl);
  if (r) h += '<div class="alert info">' + icon(KIND[r.kind].ic) + '<div><b>엄마가 ' + kindDesc(r.kind, r.side) + ' 중이에요 · <span id="clock">00:00</span></b><span>물 한 컵 챙겨 주세요.</span></div></div>';
  if (tk.length) h += '<div class="card tight">' + tk.map(taskRow).join('') + '</div>';
  const lf = lastOf(isDFeed);
  const ld = lastOf(e => e.type === 'diaper');
  const lb = lastOf(e => e.type === 'bottle');
  h += '<div class="card tight"><div class="li">' + bub('clock', '') + '<span class="tx"><span class="t">마지막 기록</span><span class="d">' + NAME('D') + ' 기준</span></span></div>' +
    '<div class="stats3" style="padding-bottom:16px">' +
    '<div class="stat"><span class="k">수유</span><span class="vv">' + (lf ? fmtAgoShort(lf.end || lf.t) : '—') + '</span></div>' +
    '<div class="stat"><span class="k">기저귀</span><span class="vv">' + (ld ? fmtAgoShort(ld.t) : '—') + '</span></div>' +
    '<div class="stat"><span class="k">젖병</span><span class="vv">' + (lb ? fmtAgoShort(lb.t) : '—') + '</span></div></div></div>';
  h += '<div class="card tight"><div class="li">' + bub('phone', 'blue') + '<span class="tx"><span class="t">대기 모드</span><span class="d">' + (state.standby ? '화면을 켜 두면 엄마가 시작할 때 소리로 알려요. ' + state.cfg.dadSleep.start + '–' + state.cfg.dadSleep.end + '엔 무음' : '엄마가 수유를 시작하면 소리로 알려요') + '</span></span><button class="switch" id="standby" role="switch" aria-checked="' + state.standby + '" aria-label="대기 모드"></button></div></div>';
  return h;
}
function taskRow(t) {
  const now = Date.now();
  const row = (ic, tone, tt, d, btn) => '<div class="li">' + bub(ic, tone) + '<span class="tx"><span class="t">' + tt + '</span><span class="d">' + d + '</span></span>' + (btn || '') + '</div>';
  switch (t.kind) {
    case 'process': return row('pump', t.overdue ? 'red' : 'violet', '유축한 양 적고 냉동하기', t.overdue ? '실온 ' + state.cfg.roomH + '시간이 지났어요. 상태를 확인해 주세요' : fmtT(t.due) + '까지 · ' + fmtT(t.e.t) + ' 유축분', '<button class="sbtn" data-proc="' + t.e.id + '">유축량 적기</button>');
    case 'wash': return row('wash', t.urgent ? 'amber' : 'blue', '유축 부품 씻기', '안 씻은 세트 ' + Math.min(t.n, 99) + '개 · 보유 ' + state.cfg.spareSets + '세트', '<button class="sbtn gray" data-wash="' + t.n + '">다 씻었어요</button>');
    case 'expired': return row('alert', 'red', '기한 지난 모유 <span class="code">' + esc(t.bag.code) + '</span>', STATE_KO[t.bag.state] + ' ' + t.bag.ml + 'ml', '<button class="sbtn" data-bag="' + t.bag.id + '">처리</button>');
    case 'expiring': return row('fridge', 'amber', '곧 기한이 끝나요 <span class="code">' + esc(t.bag.code) + '</span>', STATE_KO[t.bag.state] + ' ' + t.bag.ml + 'ml · ' + fmtDur(t.at - now) + ' 남음', '<button class="sbtn" data-bag="' + t.bag.id + '">처리</button>');
    case 'nicu': return row('cooler', 'boy', 'NICU에 모유 보내기', '아들용 ' + t.n + '팩 · ' + t.ml + 'ml', '<button class="sbtn" data-send="1">보낼 팩 고르기</button>');
    case 'deficit': return row('alert', 'red', NAME('S') + ' 몫이 모자라요', '24시간 유축 ' + t.pumped + 'ml < 오늘 처방 ' + t.need + 'ml · IBCLC·NICU와 상의', '');
    case 'order': return row('clip', 'boy', NAME('S') + ' 오늘 처방 적기', t.last ? '마지막 ' + fmtMD(t.last.t) + ' ' + (t.last.perFeed ? t.last.perFeed + 'ml×' + t.last.times : t.last.ml + 'ml') : 'NICU에서 들은 양을 적어요', '<button class="sbtn" data-q="order">처방 적기</button>');
    case 'weigh': return row('scale', 'girl', NAME('D') + ' 체중 재기', t.last ? '마지막 ' + fmtMD(t.last.t) + ' ' + n0(t.last.g) + 'g' : '집에서 잰 기록이 없어요', '<button class="sbtn" data-q="weightD">체중 적기</button>');
    case 'epds': return row('heart', 'red', '엄마 주간 마음 체크', 'K-EPDS 점수만 적으면 돼요', '<button class="sbtn" data-q="mom">점수 적기</button>');
    default: return '';
  }
}

/* ---------- 화면: 아이들 ---------- */
function viewKids() {
  const now = Date.now(), cfg = state.cfg, st = stats24(state.events, now, cfg);
  const wD = latestWeight(state.events, 'D'), wS = latestWeight(state.events, 'S');
  const sD = weightSlope(state.events, 'D', now, 7);
  const gD = wD ? wD.g : cfg.birthG.D, gS = wS ? wS.g : cfg.birthG.S;
  const delta = (g, b) => { const d = g - cfg.birthG[b]; return '<span class="pill ' + (d > 0 ? 'up' : d < 0 ? 'down' : 'flat') + '">출생보다 ' + (d >= 0 ? '+' : '') + n0(d) + 'g</span>'; };
  const fD = flags(state.events, cfg, now).filter(f => f.who === 'D');
  let h = title('두 아이의 오늘이에요', '생후 ' + dayOfLife(now, cfg) + '일 · ' + fmtMD(now));
  h += syncBanner();
  // 딸
  h += '<div class="card"><div class="kid-head">' + face('D') + '<div><div class="nm">' + NAME('D') + '</div><div class="where">집 · 직수</div></div><button class="sbtn gray" data-q="weightD">체중 적기</button></div>' +
    '<div><div class="big">' + n0(gD) + '<small>g</small></div><div style="display:flex;gap:6px;flex-wrap:wrap;margin-top:6px">' + delta(gD, 'D') + (sD !== null ? '<span class="pill flat">7일 ' + (sD >= 0 ? '+' : '') + Math.round(sD) + 'g/일</span>' : '') + '</div></div>' +
    '<div class="stats3">' +
    '<div class="stat"><span class="k">24시간 수유</span><span class="vv">' + st.dFeeds + '<small>회</small></span></div>' +
    '<div class="stat"><span class="k">기저귀</span><span class="vv">' + st.wet + '<small>소</small> ' + st.stool + '<small>대</small></span></div>' +
    '<div class="stat"><span class="k">젖병</span><span class="vv">' + (st.ebmD + st.formula) + '<small>ml</small></span></div></div>' +
    (fD.length ? fD.map(f => '<div class="alert ' + (f.level === 'now' ? 'now' : 'info') + '">' + icon('alert') + '<div><b>' + esc(f.text) + '</b><span>' + esc(f.act) + '</span></div></div>').join('') : '') +
    '</div>';
  // 아들
  const sNow = st.sNow, full = st.sFull;
  const pct = sNow ? Math.round(sNow.ml / full.ml * 100) : 0;
  h += '<div class="card"><div class="kid-head">' + face('S') + '<div><div class="nm">' + NAME('S') + '</div><div class="where">NICU · 수액과 모유</div></div><button class="sbtn" data-q="order">처방 적기</button></div>' +
    '<div><p class="small sub">오늘 처방</p><div class="big">' + (sNow ? sNow.ml + '<small>ml/일</small>' : '—') + '</div>' +
    '<p class="xs muted" style="margin-top:4px">' + (sNow ? (sNow.perFeed ? sNow.perFeed + 'ml × ' + sNow.times + '번 · ' : '') + '완전수유(' + full.ml + 'ml)의 ' + pct + '%' : 'NICU에서 들은 처방을 적어 주세요') + '</p>' +
    '<div class="bar" style="margin-top:10px"><i style="width:' + Math.min(100, pct) + '%;background:var(--boy)"></i></div></div>' +
    orderChart(now) +
    '<div class="li" style="border-top:1px solid var(--line)">' + bub('scale', 'boy') + '<span class="tx"><span class="t">체중</span><span class="d">' + (wS ? fmtMD(wS.t) + ' · ' + (wS.src === 'nicu' ? 'NICU' : wS.src === 'clinic' ? '소아과' : '집') : '출생') + '</span></span><span class="v">' + n0(gS) + 'g<small>' + (gS - cfg.birthG.S >= 0 ? '+' : '') + n0(gS - cfg.birthG.S) + 'g</small></span><button class="sbtn gray" data-q="weightS">적기</button></div>' +
    '</div>';
  h += '<div class="card"><h2>' + bub('scale', '') + '체중 변화</h2>' + weightChart(now) +
    '<div class="legend"><span><i style="background:var(--girl)"></i>' + NAME('D') + '</span><span><i style="background:var(--boy)"></i>' + NAME('S') + '</span><span>점선은 출생체중</span></div></div>';
  return h;
}
function orderChart(now) {
  const os = state.events.filter(e => e.type === 'order').sort((a, b) => a.t - b.t);
  if (!os.length) return '';
  const full = need(state.events, state.cfg, 'S').ml;
  const t0 = startOfDay(os[0].t), days = Math.max(7, Math.ceil((now - t0) / DAY) + 1);
  const W = 320, Hh = 90, L = 4, R = 4, T = 14, B = 18;
  const x = t => L + (W - L - R) * Math.min(1, (t - t0) / (days * DAY));
  const y = v => T + (Hh - T - B) * (1 - Math.min(v, full) / full);
  let pts = [[x(os[0].t), y(0)]];
  os.forEach((o, i) => { const xx = x(o.t); pts.push([xx, y(i ? os[i - 1].ml : 0)], [xx, y(o.ml)]); });
  pts.push([x(now), y(os[os.length - 1].ml)]);
  const line = pts.map(p => p[0].toFixed(1) + ',' + p[1].toFixed(1)).join(' ');
  const area = line + ' ' + x(now).toFixed(1) + ',' + y(0).toFixed(1) + ' ' + x(os[0].t).toFixed(1) + ',' + y(0).toFixed(1);
  return '<svg class="chart" viewBox="0 0 ' + W + ' ' + Hh + '" role="img" aria-label="아들 처방량 변화">' +
    '<line class="tgt" x1="' + L + '" x2="' + (W - R) + '" y1="' + y(full) + '" y2="' + y(full) + '"/><text x="' + (W - R) + '" y="' + (y(full) - 4) + '" text-anchor="end">완전수유 ' + full + 'ml</text>' +
    '<polygon class="stepfill" points="' + area + '"/><polyline class="step" points="' + line + '"/>' +
    '<text x="' + L + '" y="' + (Hh - 4) + '">' + fmtMD(os[0].t) + '</text><text x="' + x(now) + '" y="' + (Hh - 4) + '" text-anchor="end">오늘</text></svg>';
}
function weightChart(now) {
  const cfg = state.cfg, pD = weightPoints(state.events, 'D', cfg), pS = weightPoints(state.events, 'S', cfg);
  const W = 340, Hh = 170, L = 40, B = 22, T = 10, R = 8;
  const dolNow = dayOfLife(now, cfg), xmax = Math.max(28, dolNow + 3);
  const all = pD.concat(pS).map(p => p.g);
  const lo = Math.floor((Math.min(...all) - 100) / 100) * 100, hi = Math.ceil((Math.max(...all) + 150) / 100) * 100;
  const x = t => L + (W - L - R) * ((t - birthTime(cfg)) / DAY) / xmax;
  const y = g => T + (Hh - T - B) * (1 - (g - lo) / (hi - lo));
  let s = '<svg class="chart" viewBox="0 0 ' + W + ' ' + Hh + '" role="img" aria-label="생후 일수별 체중">';
  const step = hi - lo <= 600 ? 100 : hi - lo <= 1500 ? 250 : 500;
  for (let g = Math.ceil(lo / step) * step; g <= hi; g += step) s += '<line class="grid" x1="' + L + '" x2="' + (W - R) + '" y1="' + y(g) + '" y2="' + y(g) + '"/><text x="' + (L - 4) + '" y="' + (y(g) + 3) + '" text-anchor="end">' + n0(g) + '</text>';
  for (let d = 0; d <= xmax; d += 7) s += '<text x="' + x(birthTime(cfg) + d * DAY) + '" y="' + (Hh - 6) + '" text-anchor="middle">' + d + '일</text>';
  s += '<line class="birthD" x1="' + L + '" x2="' + (W - R) + '" y1="' + y(cfg.birthG.D) + '" y2="' + y(cfg.birthG.D) + '"/><line class="birthS" x1="' + L + '" x2="' + (W - R) + '" y1="' + y(cfg.birthG.S) + '" y2="' + y(cfg.birthG.S) + '"/>';
  for (const [pts, c] of [[pS, 'S'], [pD, 'D']]) {
    s += '<polyline class="l' + c + '" points="' + pts.map(p => x(p.t).toFixed(1) + ',' + y(p.g).toFixed(1)).join(' ') + '"/>';
    pts.forEach((p, i) => { s += '<circle class="p' + c + '" cx="' + x(p.t).toFixed(1) + '" cy="' + y(p.g).toFixed(1) + '" r="' + (i === pts.length - 1 ? 4.5 : 3) + '"/>'; });
  }
  return s + '</svg>';
}

/* ---------- 화면: 모유 ---------- */
function viewMilk() {
  const now = Date.now(), cfg = state.cfg, st = stats24(state.events, now, cfg);
  const inv = inventory(state.bags, state.events, cfg, now);
  const a = allocate(state.bags, state.events, cfg, now, 60);
  const pPct = Math.min(100, Math.round(st.pumped / st.pumpTarget * 100));
  const resPct = inv.reserve ? Math.min(100, Math.round(Math.min(inv.total, inv.reserve) / inv.reserve * 100)) : 0;
  let h = title('모유 ' + n0(inv.total) + 'ml를 보관 중이에요', inv.total ? '냉동 ' + n0(inv.byState('freezer')) + 'ml · 냉장 ' + n0(inv.byState('fridge')) + 'ml' : '유축한 양을 적으면 여기에 쌓여요');
  h += syncBanner();
  const groups = [['freezer', '냉동', 'snow', 'blue'], ['fridge', '냉장', 'fridge', 'blue'], ['thawed', '해동 중', 'fridge', 'amber']];
  const list = inv.avail.concat(inv.expired);
  h += '<div class="card tight">' + groups.map(([s, label, ic, tone]) => {
    const bs = list.filter(b => b.state === s).sort((x, y) => x.pumpedAt - y.pumpedAt);
    if (!bs.length && s === 'thawed') return '';
    return '<details class="grp" style="border-top:0"><summary>' + bub(ic, tone) + '<span class="tx" style="flex:1"><span class="t" style="font-weight:500">' + label + '</span></span><span class="v">' + bs.length + '팩 · ' + n0(bs.reduce((x, b) => x + (Number(b.ml) || 0), 0)) + 'ml</span>' + icon('chev', 'chev') + '</summary><div>' +
      (bs.length ? bs.map(b => { const x = bagExpiry(b, cfg), left = x - now; return '<button class="li" data-bag="' + b.id + '"><span class="tx"><span class="t"><span class="code">' + esc(b.code) + '</span> ' + b.ml + 'ml</span><span class="d">' + (b.for === 'S' ? '아들용' : '딸도 가능') + ' · ' + (left <= 0 ? '기한 지남' : fmtMD(x) + '까지') + '</span></span>' + icon('chev', 'chev') + '</button>'; }).join('') : '<p class="xs muted" style="padding-bottom:12px">없어요</p>') +
      '</div></details>';
  }).join('') + '</div>';
  h += '<button class="btn" data-send="1">' + icon('cooler') + 'NICU에 보낼 모유 고르기</button>';
  h += '<div class="card"><div class="card-head"><h2>' + bub('pump', 'violet') + '24시간 유축</h2></div>' +
    '<div class="big">' + n0(st.pumped) + '<small>/ ' + n0(st.pumpTarget) + 'ml</small></div><div class="bar"><i style="width:' + pPct + '%"></i></div>' +
    '<p class="xs muted">목표는 아들 완전수유(' + st.sFull.ml + 'ml) × ' + cfg.pumpBuffer + '예요. 오늘 처방이 적어도 공급은 지금 맞춰 둬요.' + (st.unmeasured ? ' 아직 안 적은 유축 ' + st.unmeasured + '회.' : '') + '</p></div>';
  h += '<div class="card tight">' +
    '<div class="li">' + bub('milk', 'boy') + '<span class="tx"><span class="t">' + NAME('S') + ' 예비분</span><div class="bar" style="margin-top:6px"><i style="width:' + resPct + '%;background:var(--boy)"></i></div></span><span class="v">' + resPct + '%<small>' + n0(Math.min(inv.total, inv.reserve)) + '/' + n0(inv.reserve) + 'ml</small></span></div>' +
    '<button class="li" data-q="bottle">' + bub(a.milk === 'ebm' ? 'milk' : 'bottle', a.milk === 'ebm' ? 'green' : 'amber') + '<span class="tx"><span class="t">' + NAME('D') + ' 다음 젖병</span><span class="d">' + esc(a.milk === 'ebm' ? '여유분 ' + n0(inv.surplus) + 'ml' : a.reason.split('.')[0]) + '</span></span><span class="v">' + (a.milk === 'ebm' ? '모유' : '분유') + '</span>' + icon('chev', 'chev') + '</button>' +
    '</div>';
  const ser = dailySeries(state.events, cfg, now, 14);
  h += '<div class="card"><h2>' + bub('report', '') + '하루 유축량 · 14일</h2>' + pumpChart(ser, st.pumpTarget, st.sFull.ml) +
    '<div class="legend"><span><i style="background:var(--primary)"></i>유축량</span><span><i style="background:var(--ink)"></i>목표</span><span><i style="background:var(--boy)"></i>아들 완전수유</span><span><i style="background:var(--boy);opacity:.45"></i>아들 처방</span></div></div>';
  return h;
}
function pumpChart(ser, target, needMl) {
  const W = 340, Hh = 170, L = 36, B = 22, T = 10, R = 6;
  const max = Math.max(100, target, needMl, ...ser.map(d => d.pumped));
  const top = Math.ceil(max * 1.1 / 100) * 100;
  const y = v => T + (Hh - T - B) * (1 - v / top);
  const bw = (W - L - R) / ser.length;
  let s = '<svg class="chart" viewBox="0 0 ' + W + ' ' + Hh + '" role="img" aria-label="최근 14일 하루 유축량">';
  const step = top <= 400 ? 100 : top <= 1000 ? 200 : 400;
  for (let v = 0; v <= top; v += step) s += '<line class="grid" x1="' + L + '" x2="' + (W - R) + '" y1="' + y(v) + '" y2="' + y(v) + '"/><text x="' + (L - 4) + '" y="' + (y(v) + 3) + '" text-anchor="end">' + v + '</text>';
  ser.forEach((d, i) => {
    const x = L + i * bw + 3, h = (Hh - T - B) * d.pumped / top;
    s += '<rect class="bar-p' + (d.pumped && d.pumped < needMl && !d.partial ? ' low' : '') + '" x="' + x + '" y="' + (y(0) - h) + '" width="' + (bw - 6) + '" height="' + Math.max(0, h) + '" rx="3" opacity="' + (d.partial ? .55 : 1) + '"/>';
    if (i % 2 === (ser.length - 1) % 2) s += '<text x="' + (x + (bw - 6) / 2) + '" y="' + (Hh - 6) + '" text-anchor="middle">' + Number(d.key.slice(8)) + '</text>';
  });
  if (ser.some(d => d.order > 0)) {
    let pts = '';
    ser.forEach((d, i) => { const x0 = L + i * bw, x1 = x0 + bw; pts += x0.toFixed(1) + ',' + y(d.order).toFixed(1) + ' ' + x1.toFixed(1) + ',' + y(d.order).toFixed(1) + ' '; });
    s += '<polyline class="ord" points="' + pts.trim() + '"/>';
  }
  s += '<line class="need" x1="' + L + '" x2="' + (W - R) + '" y1="' + y(needMl) + '" y2="' + y(needMl) + '"/>';
  s += '<line class="tgt" x1="' + L + '" x2="' + (W - R) + '" y1="' + y(target) + '" y2="' + y(target) + '"/>';
  return s + '</svg>';
}

/* ---------- 화면: 기록 ---------- */
function viewLog() {
  const now = Date.now(), lastFeed = lastOf(isDFeed);
  let h = lastFeed ? '<div class="title"><p>' + NAME('D') + ' 마지막 수유</p><h1>' + fmtAgo(lastFeed.end || lastFeed.t) + '</h1><p>' + fmtT(lastFeed.t) + ' · ' + feedDesc(lastFeed) + '</p></div>' : title('아직 기록이 없어요');
  h += syncBanner();
  h += '<div class="seg" role="group" aria-label="보기"><button data-logview="list" aria-pressed="' + (state.logView === 'list') + '">시간순 기록</button><button data-logview="report" aria-pressed="' + (state.logView === 'report') + '">진료용 7일</button></div>';
  if (state.logView === 'report') return h + viewReport();
  h += '<button class="btn weak" data-add="1">' + icon('note') + '다른 기록 추가하기</button>';
  const st = stats24(state.events, now, state.cfg);
  h += '<div class="card"><h2>' + bub('clock', 'blue') + '최근 24시간</h2><div class="stats3">' +
    '<div class="stat"><span class="k">젖 비우기</span><span class="vv">' + st.removals + '<small>/' + state.cfg.th.removalsMin + '</small></span></div>' +
    '<div class="stat"><span class="k">가장 긴 공백</span><span class="vv">' + (st.longestGap / HOUR).toFixed(1) + '<small>시간</small></span></div>' +
    '<div class="stat"><span class="k">유축</span><span class="vv">' + n0(st.pumped) + '<small>ml</small></span></div>' +
    '<div class="stat"><span class="k">' + NAME('D') + ' 수유</span><span class="vv">' + st.dFeeds + '<small>회</small></span></div>' +
    '<div class="stat"><span class="k">기저귀</span><span class="vv">' + st.wet + '<small>소</small> ' + st.stool + '<small>대</small></span></div>' +
    '<div class="stat"><span class="k">분유</span><span class="vv">' + st.formula + '<small>ml</small></span></div></div></div>';
  const evs = state.events.filter(e => e.t > now - 3 * DAY).slice().reverse();
  if (!evs.length) return h + '<div class="card"><div class="empty">' + bub('clock', '') + '<b>기록이 아직 없어요</b><span class="xs">엄마 폰에서 수유를 시작하면 여기에 쌓여요</span></div></div>';
  let cur = '';
  for (const e of evs) {
    const k = dayKey(e.t);
    if (k !== cur) { if (cur) h += '</div>'; cur = k; h += '<p class="day">' + (k === dayKey(now) ? '오늘' : k === dayKey(now - DAY) ? '어제' : fmtMD(e.t)) + '</p><div class="card tight tl">'; }
    const [ic, tone] = eventIcon(e);
    h += '<button class="li" data-ev="' + e.id + '"><span class="time">' + fmtT(e.t) + '</span>' + bub(ic, tone) + '<span class="tx"><span class="t">' + esc(describe(e)) + '</span><span class="d">' + (e.by === 'mom' ? '엄마' : e.by === 'dad' ? '아빠' : esc(e.by || '')) + '</span></span>' + icon('chev', 'chev') + '</button>';
  }
  return h + '</div><p class="foot">3일 전까지 보여요. 전체 기록은 진료용 7일에서 파일로 받을 수 있어요.</p>';
}
function reportData() {
  const now = Date.now(), cfg = state.cfg;
  return { now, cfg, ser: dailySeries(state.events, cfg, now, 7), st: stats24(state.events, now, cfg), fl: flags(state.events, cfg, now),
    sD: weightSlope(state.events, 'D', now, 7), sS: weightSlope(state.events, 'S', now, 7), wD: latestWeight(state.events, 'D'), wS: latestWeight(state.events, 'S'),
    mc: state.events.filter(e => e.type === 'momcheck').slice(-3).reverse(), notes: state.events.filter(e => e.type === 'note' && e.t > now - 7 * DAY).reverse() };
}
function orderHistory() {
  const os = state.events.filter(e => e.type === 'order').slice(-5);
  if (!os.length) return '기록 없음';
  return os.map(o => fmtMD(o.t) + ' ' + (o.perFeed ? o.perFeed + 'ml×' + o.times : o.ml + 'ml')).join(' → ') + ' (= ' + os[os.length - 1].ml + 'ml/일)';
}
function viewReport() {
  const d = reportData(), cfg = d.cfg, th = cfg.th, sN = d.st.sFull.ml;
  const gap = ms => ms ? (ms / HOUR).toFixed(1) : '—';
  const w = (lw, b, sl) => (lw ? n0(lw.g) + 'g (' + fmtMD(lw.t) + ')' : '측정 없음') + ' · 출생 ' + n0(cfg.birthG[b]) + 'g' + (lw ? ' (' + (lw.g - cfg.birthG[b] >= 0 ? '+' : '') + (lw.g - cfg.birthG[b]) + 'g)' : '') + ' · 7일 ' + (sl === null ? '—' : (sl >= 0 ? '+' : '') + Math.round(sl) + 'g/일');
  const rows = d.ser.map(x => '<tr><td>' + fmtMD(x.start) + (x.partial ? '*' : '') + '</td>' +
    '<td' + (!x.partial && x.removals < th.removalsMin ? ' class="bad"' : '') + '>' + x.removals + '</td><td>' + gap(x.nightGap) + '</td>' +
    '<td' + (!x.partial && x.pumped < sN ? ' class="bad"' : '') + '>' + x.pumped + '</td><td>' + (x.order || '—') + '</td><td>' + x.toNicu + '</td>' +
    '<td' + (!x.partial && x.dFeeds < th.feedsMin ? ' class="bad"' : '') + '>' + x.dFeeds + '</td><td>' + x.ebmD + '/' + x.formula + '</td>' +
    '<td' + (!x.partial && x.wet < th.wetMin ? ' class="bad"' : '') + '>' + x.wet + '</td><td' + (!x.partial && x.stool < th.stoolMin ? ' class="bad"' : '') + '>' + x.stool + '</td></tr>').join('');
  let h = '<div class="card" id="report"><h2>' + bub('report', 'blue') + '진료용 요약</h2>' +
    '<p class="small">쌍둥이 2026-11-06 출생, 재태 37+0주 · 생후 ' + dayOfLife(d.now, cfg) + '일</p>' +
    '<p class="small"><b class="girl-c">' + NAME('D') + '</b> 집, 직수 중심 · ' + w(d.wD, 'D', d.sD) + '</p>' +
    '<p class="small"><b class="boy-c">' + NAME('S') + '</b> NICU (장회전이상 수술 후) · ' + w(d.wS, 'S', d.sS) + '</p>' +
    '<p class="small">' + NAME('S') + ' 경장영양: ' + orderHistory() + ' (수액 병행) · 완전수유 시 약 ' + sN + 'ml/일</p>' +
    '<p class="small">엄마 유축: 24시간 ' + d.st.pumped + 'ml · 7일 평균 ' + avg(d.ser.filter(x => !x.partial).map(x => x.pumped)) + 'ml · 목표 ' + d.st.pumpTarget + 'ml</p>' +
    '<div class="tablewrap"><table><thead><tr><th>날짜</th><th>비우기</th><th>밤공백h</th><th>유축ml</th><th>아들처방</th><th>NICU ml</th><th>딸수유</th><th>모유/분유</th><th>소변</th><th>대변</th></tr></thead><tbody>' + rows + '</tbody></table></div>' +
    '<p class="xs muted">* 오늘(진행 중). 빨간 숫자는 기준 미달' + (th.confirmed ? ' (소아과 확인 기준)' : ' (소아과 확인 전 기본값)') + '. 밤공백은 엄마가 가장 길게 잔 시간 추정.</p>';
  if (d.fl.length) h += d.fl.map(f => '<p class="small"><b>' + { now: '즉시', today: '당일 연락', visit: '진료 때 상의', plan: '공급 관리' }[f.level] + '</b> · ' + esc(f.text) + '</p>').join('');
  if (d.mc.length) h += '<p class="small"><b>엄마</b> ' + d.mc.map(m => fmtMD(m.t) + ' ' + esc(describe(m).replace('엄마 상태', ''))).join(' · ') + '</p>';
  if (d.notes.length) h += '<p class="small"><b>메모</b> ' + d.notes.map(n => fmtMD(n.t) + ' ' + esc(n.text)).join(' · ') + '</p>';
  h += '</div><div class="row2"><button class="btn gray" id="dl-html">리포트 파일</button><button class="btn gray" id="dl-csv">전체 기록 CSV</button></div>';
  return h;
}
const avg = a => { const v = a.filter(x => x > 0); return v.length ? Math.round(v.reduce((s, x) => s + x, 0) / v.length) : 0; };
async function download(kind) {
  const dl = window.claude && window.claude.use ? await window.claude.use('downloads') : null;
  if (!dl) { toast('여기서는 파일 저장을 쓸 수 없어요. 화면 캡처를 써 주세요.', true); return; }
  const stamp = dayKey(Date.now());
  let filename, data;
  if (kind === 'csv') {
    const q = v => '"' + String(v ?? '').replace(/"/g, '""') + '"';
    const lines = [['시각', '종류', '아기', '기록자', '내용', 'ml', '원본'].map(q).join(',')];
    for (const e of state.events) lines.push([new Date(e.t).toLocaleString('ko-KR'), e.type, NAME(e.baby), e.by, describe(e), e.type === 'session' ? sessionMl(e) : (e.ml ?? ''), JSON.stringify(e)].map(q).join(','));
    filename = 'twin-feeding-' + stamp + '.csv'; data = '﻿' + lines.join('\n');
  } else {
    filename = 'twin-feeding-report-' + stamp + '.html';
    data = '<!doctype html><meta charset="utf-8"><title>쌍둥이 수유 리포트 ' + stamp + '</title><style>body{font-family:system-ui,"Malgun Gothic",sans-serif;max-width:760px;margin:24px auto;padding:0 16px;color:#191F28}table{border-collapse:collapse;width:100%;font-size:13px}th,td{border-bottom:1px solid #ccc;padding:6px;text-align:right}th:first-child,td:first-child{text-align:left}.bad{color:#EF4452;font-weight:700}.xs,.muted{color:#8B95A1;font-size:12px}svg{display:none}h2{font-size:17px}</style>' + $('#report').innerHTML;
  }
  try { await dl.save({ filename, data }); } catch (e) { if (e && e.code !== 'declined') toast('저장하지 못했어요 (' + (e.code || '오류') + ')', true); }
}

/* ---------- 렌더 ---------- */
function render() {
  const ae = document.activeElement;
  if (ae && $('#main').contains(ae) && /INPUT|TEXTAREA|SELECT/.test(ae.tagName)) { state.pending = true; return; }
  if (!$('#sheet').hidden) { state.pending = true; return; }
  state.pending = false;
  validTab();
  document.documentElement.dataset.night = state.night ? '1' : '0';
  $('#night').setAttribute('aria-pressed', state.night);
  $('#dol').textContent = '생후 ' + dayOfLife(Date.now(), state.cfg) + '일';
  const sy = $('#sync'); sy.className = 'sync ' + (state.mode === 'db' ? 'ok' : state.mode === 'db-wait' || state.mode === 'loading' ? '' : 'warn');
  sy.title = state.mode === 'db' ? '공유 중' : '공유 안 됨';
  const views = { feed: viewFeed, todo: viewTodo, kids: viewKids, milk: viewMilk, log: viewLog };
  $('#main').innerHTML = (state.me ? undoBar() : '') + (state.me ? (views[state.tab] || viewFeed)() : viewRole());
  // 아빠 할 일 화면의 하단 고정 빠른 기록
  const dock = state.me === 'dad' && state.tab === 'todo';
  $('#dock').hidden = !dock;
  $('#mainEl').classList.toggle('with-dock', dock);
  if (dock) $('#dockIn').innerHTML = '<div class="quick four">' + qk('wet', 'pee', 'pee', '소변') + qk('stool', 'poop', 'poop', '대변') + qk('both', 'both', 'diaper', '둘 다') + qk('bottle', 'bottle', 'bottle', '젖병') + '</div>';
  const tabs = TABS[state.me] || [];
  const urgent = state.me === 'dad' ? tasks(state.events, state.bags, state.cfg, Date.now()).filter(t => t.kind === 'process' || t.kind === 'expired' || t.kind === 'deficit' || (t.kind === 'wash' && t.urgent)).length : 0;
  $('#tabs').innerHTML = tabs.map(([id, label, ic]) => '<button data-tab="' + id + '" aria-current="' + (id === state.tab ? 'page' : 'false') + '">' + icon(ic) + label + (id === 'todo' && urgent ? '<span class="badge">' + urgent + '</span>' : '') + '</button>').join('');
  $('nav.tabs').hidden = !state.me;
  tick();
}
function tick() {
  const r = running(), el = document.getElementById('clock');
  if (r && el) { const s = Math.floor((Date.now() - r.t) / 1000); el.textContent = (s >= 3600 ? Math.floor(s / 3600) + ':' : '') + pad(Math.floor(s / 60) % 60) + ':' + pad(s % 60); }
}
setInterval(tick, 1000);
setInterval(() => { if ($('#sheet').hidden) render(); }, 30000);
document.addEventListener('focusout', () => setTimeout(() => { if (state.pending && $('#sheet').hidden) render(); }, 0));

/* ---------- 이벤트 위임 ---------- */
document.addEventListener('click', async e => {
  const b = e.target.closest('button'); if (!b || b.closest('#panel')) return;
  const d = b.dataset;
  if (d.tab) { state.tab = d.tab; ls.set('tf.tab2', d.tab); render(); window.scrollTo(0, 0); return; }
  if (d.role) { state.me = d.role; ls.set('tf.me', state.me); state.tab = null; render(); return; }
  if (b.id === 'night') { state.night = !state.night; ls.set('tf.night', state.night); render(); return; }
  if (b.id === 'gear') return settingsSheet();
  if (d.start) return startSession(d.start);
  if (d.end) { const r = state.events.find(x => x.id === d.end); if (r) endSession(r); return; }
  if (d.cancel) { const r = state.events.find(x => x.id === d.cancel); if (r) cancelSession(r); return; }
  if (d.side) { state.side = d.side; render(); return; }
  if (d.proc) { const r = state.events.find(x => x.id === d.proc); if (r) processSheet(r); return; }
  if (d.wash) return washDone(Number(d.wash));
  if (d.bag) { const bg = state.bags[d.bag]; if (bg) bagSheet(bg); return; }
  if (d.ev) { const r = state.events.find(x => x.id === d.ev); if (r) eventSheet(r); return; }
  if (d.send) return sendSheet();
  if (d.add) return addSheet();
  if (d.logview) { state.logView = d.logview; render(); return; }
  if (b.id === 'standby') {
    state.standby = !state.standby;
    if (state.standby) { try { audio = audio || new (window.AudioContext || window.webkitAudioContext)(); await audio.resume(); chime(); } catch {} lockScreen(); }
    else if (wakeLock) { try { wakeLock.release(); } catch {} wakeLock = null; }
    render(); return;
  }
  if (b.id === 'undo' && state.undos && state.undos.length) { const u = state.undos[state.undos.length - 1]; if (await act(u.fn, '되돌렸어요')) { state.undos = state.undos.filter(x => x !== u); render(); } return; }
  if (b.id === 'dl-html') return download('html');
  if (b.id === 'dl-csv') return download('csv');
  switch (d.q) {
    case 'wet': return quickDiaper(true, false);
    case 'stool': return quickDiaper(false, true);
    case 'both': return quickDiaper(true, true);
    case 'bottle': return bottleSheet();
    case 'weightD': return weightSheet('D');
    case 'weightS': return weightSheet('S');
    case 'order': return orderSheet();
    case 'mom': return momSheet();
    case 'note': return noteSheet();
  }
});

render();
Store.init();
})();
