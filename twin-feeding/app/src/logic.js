/* LOGIC START — 순수 계산 함수 (DOM 없음, tests/logic.test.js에서 검증) */
const HOUR = 3600e3, DAY = 24 * HOUR;
const DEFAULT_CONFIG = {
  birthDate: '2026-11-06',
  names: { D: '딸', S: '아들' },
  birthG: { D: 2630, S: 2640 },
  sonOrderMl: 0,            // (예전 방식) 처방 ml/일. 지금은 'order' 이벤트로 기록
  mlPerKg: 150,             // 완전수유 계획값 (소아과 확인)
  reserveDays: 2,           // 아들 완전수유 며칠치를 잠가둘지
  pumpBuffer: 1.2,          // 유축 목표 = 아들 완전수유 필요량 × 1.2 (현재 처방량이 아님)
  earlyDays: 14,            // 생후 이 날짜까지 짠 초기 모유는 아들 전용
  defaultDest: 'freezer',   // NICU에 냉동으로 전달 중
  roomH: 4, homeFridgeH: 96, nicuFridgeH: 48, freezerD: 180, thawedH: 24,
  momSleep: { start: '21:45', end: '02:30' },
  dadSleep: { start: '02:30', end: '09:00' },
  spareSets: 4,
  th: { confirmed: false, removalsMin: 8, maxGapH: 5, wetMin: 6, stoolMin: 1, feedsMin: 8, feedGapH: 4, momTemp: 38.5, epds: 10, gainMin: 0 },
};

function mergeConfig(c) {
  const out = JSON.parse(JSON.stringify(DEFAULT_CONFIG));
  if (!c || typeof c !== 'object') return out;
  for (const k of Object.keys(c)) {
    if (c[k] && typeof c[k] === 'object' && !Array.isArray(c[k]) && out[k] && typeof out[k] === 'object') Object.assign(out[k], c[k]);
    else if (c[k] !== undefined && c[k] !== null) out[k] = c[k];
  }
  return out;
}
const pad = n => String(n).padStart(2, '0');
function dayKey(t) { const d = new Date(t); return d.getFullYear() + '-' + pad(d.getMonth() + 1) + '-' + pad(d.getDate()); }
function startOfDay(t) { const d = new Date(t); d.setHours(0, 0, 0, 0); return d.getTime(); }
function birthTime(cfg) { const [y, m, d] = cfg.birthDate.split('-').map(Number); return new Date(y, m - 1, d).getTime(); }
function dayOfLife(t, cfg) { return Math.round((startOfDay(t) - birthTime(cfg)) / DAY); }
function hmMin(s) { const [h, m] = String(s).split(':').map(Number); return (h || 0) * 60 + (m || 0); }
function inWindow(t, win) {
  const d = new Date(t), m = d.getHours() * 60 + d.getMinutes(), a = hmMin(win.start), b = hmMin(win.end);
  return a <= b ? (m >= a && m < b) : (m >= a || m < b);
}
const isRemoval = e => e.type === 'session';
const isPump = e => e.type === 'session' && e.kind !== 'nurse';
const isNurse = e => e.type === 'session' && e.kind !== 'pump';
const sessionMl = e => (Number(e.mlL) || 0) + (Number(e.mlR) || 0);
const removalTimes = events => events.filter(isRemoval).map(e => e.t).sort((a, b) => a - b);

function latestWeight(events, baby) {
  let best = null;
  for (const e of events) if (e.type === 'weight' && e.baby === baby && (!best || e.t > best.t)) best = e;
  return best;
}
// 완전수유 필요량 (체중 × ml/kg). 공급 목표와 아들 예비분 계산에 쓴다.
function need(events, cfg, baby) {
  const w = latestWeight(events, baby);
  const g = w ? Number(w.g) : cfg.birthG[baby];
  return { ml: Math.round(g / 1000 * cfg.mlPerKg), g, src: (w ? g + 'g' : '출생체중') + ' × ' + cfg.mlPerKg + 'ml/kg' };
}
// 아들 현재 NICU 처방 (증량 중). 없으면 null
function latestOrder(events, now) {
  let best = null;
  for (const e of events) if (e.type === 'order' && e.t <= now && (!best || e.t > best.t)) best = e;
  return best;
}
function sonNow(events, cfg, now) {
  const o = latestOrder(events, now);
  if (o) return { ml: Number(o.ml) || 0, perFeed: o.perFeed, times: o.times, t: o.t, src: 'NICU 처방' + (o.perFeed ? ' ' + o.perFeed + 'ml×' + o.times + '회' : '') };
  if (Number(cfg.sonOrderMl) > 0) return { ml: Number(cfg.sonOrderMl), src: 'NICU 처방' };
  return null;
}
function hasFullDay(events, now) { return events.some(e => e.t <= now - DAY); }

function stats24(events, now, cfg) {
  const from = now - DAY;
  const win = events.filter(e => e.t > from && e.t <= now);
  const all = removalTimes(events).filter(t => t <= now);
  const inWin = all.filter(t => t > from);
  const firstIdx = all.findIndex(t => t > from);
  const seq = firstIdx < 0 ? [] : all.slice(Math.max(0, firstIdx - 1));
  let longestGap = 0;
  for (let i = 1; i < seq.length; i++) longestGap = Math.max(longestGap, seq[i] - seq[i - 1]);
  const sinceLast = all.length ? now - all[all.length - 1] : null;
  const night = inWin.some(t => { const h = new Date(t).getHours(); return h >= 1 && h < 5; });
  const pumped = win.filter(isPump).reduce((s, e) => s + sessionMl(e), 0);
  const unmeasured = win.filter(e => isPump(e) && e.end && !e.processed).length;
  const dNurse = win.filter(e => isNurse(e)).length;
  const dBottles = win.filter(e => e.type === 'bottle' && e.baby === 'D');
  const dFeedTimes = win.filter(e => isNurse(e) || (e.type === 'bottle' && e.baby === 'D')).map(e => e.t);
  const lastDFeed = events.filter(e => (isNurse(e) || (e.type === 'bottle' && e.baby === 'D')) && e.t <= now).reduce((m, e) => Math.max(m, e.t), 0);
  const diapers = win.filter(e => e.type === 'diaper' && e.baby === 'D');
  const sFull = need(events, cfg, 'S');
  const sNow = sonNow(events, cfg, now);
  return {
    removals: inWin.length, longestGap, sinceLast, night, pumped, unmeasured,
    dFeeds: dNurse + dBottles.length, dNurse, dFeedTimes,
    sinceDFeed: lastDFeed ? now - lastDFeed : null,
    formula: dBottles.filter(b => b.milk === 'formula').reduce((s, b) => s + (Number(b.ml) || 0), 0),
    ebmD: dBottles.filter(b => b.milk === 'ebm').reduce((s, b) => s + (Number(b.ml) || 0), 0),
    wet: diapers.filter(d => d.wet).length, stool: diapers.filter(d => d.stool).length,
    sFull, sNow, pumpTarget: Math.round(sFull.ml * cfg.pumpBuffer), full: hasFullDay(events, now),
  };
}

// 밤 공백: day 키의 전날 21시 ~ 당일 12시 사이에 끝나는 비우기 간격 중 최댓값 (엄마 최장 수면 추정)
function nightGap(events, key) {
  const [y, m, d] = key.split('-').map(Number);
  const s = new Date(y, m - 1, d).getTime();
  const lo = s - 3 * HOUR, hi = s + 12 * HOUR;
  const all = removalTimes(events);
  let best = 0;
  for (let i = 1; i < all.length; i++) if (all[i] >= lo && all[i] < hi) best = Math.max(best, all[i] - all[i - 1]);
  return best;
}

function dailySeries(events, cfg, now, n) {
  const out = [];
  const today = startOfDay(now);
  for (let i = n - 1; i >= 0; i--) {
    const s = new Date(today); s.setDate(s.getDate() - i); const start = s.getTime();
    const e2 = new Date(start); e2.setDate(e2.getDate() + 1); const end = e2.getTime();
    const key = dayKey(start);
    const ev = events.filter(e => e.t >= start && e.t < end);
    const dB = ev.filter(e => e.type === 'bottle' && e.baby === 'D');
    const dia = ev.filter(e => e.type === 'diaper' && e.baby === 'D');
    const taps = who => ev.filter(e => e.by === who).length + ev.filter(e => e.type === 'session' && e.endBy === who).length;
    const sends = ev.filter(e => e.type === 'nicu').reduce((s, e) => s + (Number(e.ml) || 0), 0);
    const ord = latestOrder(events, end - 1);
    out.push({
      key, start, dol: dayOfLife(start, cfg), partial: start + DAY > now,
      removals: ev.filter(isRemoval).length,
      night: ev.filter(isRemoval).some(e => { const h = new Date(e.t).getHours(); return h >= 1 && h < 5; }),
      pumped: ev.filter(isPump).reduce((s, e) => s + sessionMl(e), 0),
      dFeeds: ev.filter(isNurse).length + dB.length,
      formula: dB.filter(b => b.milk === 'formula').reduce((s, b) => s + (Number(b.ml) || 0), 0),
      ebmD: dB.filter(b => b.milk === 'ebm').reduce((s, b) => s + (Number(b.ml) || 0), 0),
      wet: dia.filter(d => d.wet).length, stool: dia.filter(d => d.stool).length,
      nightGap: nightGap(events, key), momTaps: taps('mom'), dadTaps: taps('dad'), toNicu: sends,
      order: ord ? Number(ord.ml) || 0 : (Number(cfg.sonOrderMl) || 0),
      count: ev.length,
    });
  }
  return out;
}

function weightPoints(events, baby, cfg) {
  const pts = [{ t: birthTime(cfg), g: cfg.birthG[baby], birth: true }];
  for (const e of events) if (e.type === 'weight' && e.baby === baby) pts.push({ t: e.t, g: Number(e.g), src: e.src });
  return pts.sort((a, b) => a.t - b.t);
}
// 최근 days일 측정값의 최소제곱 기울기 (g/일). 출생점은 제외.
function weightSlope(events, baby, now, days) {
  const pts = events.filter(e => e.type === 'weight' && e.baby === baby && e.t > now - days * DAY && e.t <= now).map(e => ({ x: e.t / DAY, y: Number(e.g) }));
  if (pts.length < 2) return null;
  const span = Math.max(...pts.map(p => p.x)) - Math.min(...pts.map(p => p.x));
  if (span < 2) return null;
  const mx = pts.reduce((s, p) => s + p.x, 0) / pts.length, my = pts.reduce((s, p) => s + p.y, 0) / pts.length;
  let num = 0, den = 0;
  for (const p of pts) { num += (p.x - mx) * (p.y - my); den += (p.x - mx) ** 2; }
  return den ? num / den : null;
}

function bagExpiry(bag, cfg) {
  if (bag.state === 'fridge') return bag.pumpedAt + (bag.for === 'S' ? cfg.nicuFridgeH : cfg.homeFridgeH) * HOUR;
  if (bag.state === 'freezer') return bag.pumpedAt + cfg.freezerD * DAY;
  if (bag.state === 'thawed') return (bag.stateAt || bag.pumpedAt) + cfg.thawedH * HOUR;
  return null;
}
const ACTIVE = ['fridge', 'freezer', 'thawed'];
function inventory(bags, events, cfg, now) {
  const list = Object.values(bags).filter(b => ACTIVE.includes(b.state));
  const avail = list.filter(b => bagExpiry(b, cfg) > now);
  const expired = list.filter(b => bagExpiry(b, cfg) <= now);
  const total = avail.reduce((s, b) => s + (Number(b.ml) || 0), 0);
  const sFull = need(events, cfg, 'S');
  const reserve = Math.round(sFull.ml * cfg.reserveDays);
  return { avail, expired, total, reserve, surplus: total - reserve, sFull,
    byState: s => avail.filter(b => b.state === s).reduce((a, b) => a + (Number(b.ml) || 0), 0) };
}
// 배분 규칙 (설계서 1-4)
//  예비분 = 아들 '완전수유' 필요량 × 예비일수 (증량이 빨라도 버틸 양)
//  초기 모유(생후 earlyDays일까지 짠 것)는 아들 전용. 딸에게는 가장 최근에 짠 것부터
function allocate(bags, events, cfg, now, ml) {
  const st = stats24(events, now, cfg);
  const inv = inventory(bags, events, cfg, now);
  if (st.full && st.sNow && st.pumped < st.sNow.ml) {
    return { milk: 'formula', rule: 3, reason: '최근 24시간 유축 ' + st.pumped + 'ml < 아들 현재 처방 ' + st.sNow.ml + 'ml. 모유는 전부 아들 몫', inv };
  }
  if (inv.surplus < ml) {
    return { milk: 'formula', rule: 2, reason: '여유분 ' + Math.max(0, inv.surplus) + 'ml < ' + ml + 'ml. 아들 예비분(완전수유 ' + cfg.reserveDays + '일치 ' + inv.reserve + 'ml)을 먼저 채우는 중', inv };
  }
  const earlyEnd = birthTime(cfg) + cfg.earlyDays * DAY;
  const cand = inv.avail.filter(b => b.pumpedAt >= earlyEnd || b.for === 'any');
  if (!cand.length) {
    return { milk: 'formula', rule: 2, reason: '보관분이 모두 생후 ' + cfg.earlyDays + '일 이전의 초기 모유라 아들 몫', inv };
  }
  const order = { thawed: 0, fridge: 1, freezer: 2 };
  const pick = cand.slice().sort((a, b) => ((b.for === 'any') - (a.for === 'any')) || (order[a.state] - order[b.state]) || (b.pumpedAt - a.pumpedAt))[0];
  return { milk: 'ebm', rule: 2, bag: pick, reason: '여유분 ' + inv.surplus + 'ml (보관 ' + inv.total + ' − 아들 예비 ' + inv.reserve + '). 최근에 짠 것부터', inv };
}

function tasks(events, bags, cfg, now) {
  const out = [];
  for (const e of events) {
    if (e.type !== 'session') continue;
    if (!e.end) out.push({ kind: 'running', pri: 0, e });
    else if (e.kind !== 'nurse' && !e.processed) {
      const due = e.end + cfg.roomH * HOUR;
      out.push({ kind: 'process', pri: due < now + HOUR ? 1 : 3, e, due, overdue: due < now });
    }
  }
  const lastWash = events.filter(e => e.type === 'wash').reduce((m, e) => Math.max(m, e.t), 0);
  const used = events.filter(e => isPump(e) && e.end && e.t > lastWash).length;
  if (used > 0) out.push({ kind: 'wash', pri: used >= cfg.spareSets - 1 ? 2 : 6, n: used, urgent: used >= cfg.spareSets - 1 });
  const inv = inventory(bags, events, cfg, now);
  for (const b of inv.expired) out.push({ kind: 'expired', pri: 2, bag: b });
  for (const b of inv.avail) { const x = bagExpiry(b, cfg); if (x - now < 12 * HOUR && b.state !== 'freezer') out.push({ kind: 'expiring', pri: 3, bag: b, at: x }); }
  const sBags = inv.avail.filter(b => b.for === 'S' && b.state !== 'thawed');
  const sentToday = events.some(e => e.type === 'nicu' && dayKey(e.t) === dayKey(now));
  if (sBags.length && !sentToday) out.push({ kind: 'nicu', pri: 4, n: sBags.length, ml: sBags.reduce((s, b) => s + (Number(b.ml) || 0), 0) });
  const st = stats24(events, now, cfg);
  if (st.full && st.sNow && st.pumped < st.sNow.ml) out.push({ kind: 'deficit', pri: 2, pumped: st.pumped, need: st.sNow.ml });
  const lo = latestOrder(events, now);
  if (!lo || now - lo.t > DAY) out.push({ kind: 'order', pri: 5, last: lo });
  const w = latestWeight(events, 'D');
  if (!w || now - w.t > 3 * DAY) out.push({ kind: 'weigh', pri: 7, last: w });
  const ep = events.filter(e => e.type === 'momcheck' && e.epds !== undefined && e.epds !== null && e.epds !== '').reduce((m, e) => Math.max(m, e.t), 0);
  if (!ep || now - ep > 7 * DAY) out.push({ kind: 'epds', pri: 8 });
  return out.sort((a, b) => a.pri - b.pri);
}

// 연락 기준 (기본값은 소아과 확인 전). level: now(즉시) / today(당일 연락) / visit(진료 때 상의) / plan(공급 관리)
function flags(events, cfg, now) {
  const th = cfg.th, out = [];
  const st = stats24(events, now, cfg);
  const mc = events.filter(e => e.type === 'momcheck' && e.t > now - 2 * DAY).sort((a, b) => b.t - a.t)[0];
  if (mc) {
    if (Number(mc.epds10) >= 1) out.push({ level: 'now', who: 'mom', text: 'K-EPDS 10번 문항 응답 있음', act: '점수와 상관없이 바로 109(24시간) 또는 119' });
    const temp = Number(mc.temp);
    if (temp >= 39) out.push({ level: 'now', who: 'mom', text: '엄마 체온 ' + temp + '°C', act: '당일 진료/응급실' });
    else if (temp >= th.momTemp) out.push({ level: 'today', who: 'mom', text: '엄마 체온 ' + temp + '°C' + (mc.breast === 'red' ? ' + 유방 붉음·통증' : ''), act: '산과·모유수유 클리닉 당일 연락 (강한 마사지·과도한 유축 금지)' });
    else if (mc.breast === 'red') out.push({ level: 'today', who: 'mom', text: '유방 붉음·통증 기록', act: '24시간 넘게 지속되면 연락' });
    if (mc.epds !== undefined && mc.epds !== '' && Number(mc.epds) >= th.epds) out.push({ level: 'visit', who: 'mom', text: 'K-EPDS ' + mc.epds + '점 (기준 ' + th.epds + ')', act: '산과·정신건강의학과 상담 예약' });
    if (Number(mc.pain) >= 7) out.push({ level: 'visit', who: 'mom', text: '수유 통증 ' + mc.pain + '/10', act: 'IBCLC: 래치·깔때기 크기 점검' });
  }
  if (st.full) {
    if (st.wet < th.wetMin) out.push({ level: 'today', who: 'D', text: '최근 24시간 소변 ' + st.wet + '회 (기준 ' + th.wetMin + '회)', act: '소아과 당일 전화 (기록 누락이 아닌지 먼저 확인)' });
    if (st.stool < th.stoolMin) out.push({ level: 'today', who: 'D', text: '최근 24시간 대변 ' + st.stool + '회', act: '소아과 당일 전화' });
    if (st.dFeeds < th.feedsMin) out.push({ level: 'today', who: 'D', text: '최근 24시간 수유 ' + st.dFeeds + '회 (기준 ' + th.feedsMin + '회)', act: '소아과 당일 전화' });
    if (st.removals < th.removalsMin) out.push({ level: 'plan', who: 'mom', text: '젖 비우기 ' + st.removals + '회 (목표 ' + th.removalsMin + '회)', act: '공급 관리: 교대표 점검' });
    if (st.longestGap > th.maxGapH * HOUR) out.push({ level: 'plan', who: 'mom', text: '비우기 최장 공백 ' + (st.longestGap / HOUR).toFixed(1) + '시간 (목표 ≤' + th.maxGapH + ')', act: '공급 관리: 밤 교대 시각 점검' });
  }
  if (st.sinceDFeed !== null && st.sinceDFeed > th.feedGapH * HOUR) out.push({ level: 'today', who: 'D', text: '딸 마지막 수유 ' + (st.sinceDFeed / HOUR).toFixed(1) + '시간 전', act: '깨워서 수유 (소아과와 정한 최대 간격 ' + th.feedGapH + '시간)' });
  // 공급 점검: 완료된 날 3일 이상의 평균 유축량이 아들 완전수유 필요량보다 적으면 (생후 14일부터)
  const done = dailySeries(events, cfg, now, 8).filter(d => !d.partial && d.count > 0);
  if (dayOfLife(now, cfg) >= 14 && done.length >= 3) {
    const a = Math.round(done.reduce((s, d) => s + d.pumped, 0) / done.length);
    if (a < st.sFull.ml) out.push({ level: 'plan', who: 'mom', text: '유축 평균 ' + a + 'ml/일 < 아들 완전수유 ' + st.sFull.ml + 'ml', act: '아들이 아직 적게 먹어도 공급은 지금 맞춰야 해요. IBCLC 상담' });
  }
  const w = latestWeight(events, 'D');
  if (w && dayOfLife(now, cfg) >= 14 && Number(w.g) < cfg.birthG.D) out.push({ level: 'visit', who: 'D', text: '생후 14일 이후에도 출생체중 미회복 (' + w.g + 'g < ' + cfg.birthG.D + 'g)', act: '소아과 진료' });
  const sl = weightSlope(events, 'D', now, 7);
  if (th.gainMin > 0 && sl !== null && sl < th.gainMin) out.push({ level: 'visit', who: 'D', text: '딸 7일 증가 ' + Math.round(sl) + 'g/일 (기준 ' + th.gainMin + ')', act: '소아과 진료' });
  const order = { now: 0, today: 1, visit: 2, plan: 3 };
  return out.sort((a, b) => order[a.level] - order[b.level]);
}
/* LOGIC END */
