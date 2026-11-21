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

/* ---------- 성장·수유 가이드 (책 + 질병관리청 2017 성장도표 = 36개월 미만은 WHO 성장기준) ---------- */
// 연령(개월)별 몸무게 백분위 1·25·50·75·99 (kg). 책 66–67쪽 표 = WHO 성장기준 값과 같음
const WFA = {
  S: { p1: [2.3, 3.2, 4.1, 4.8, 5.4, 5.8, 6.1, 6.4, 6.7, 6.9, 7.1, 7.3], p25: [3.0, 4.1, 5.1, 5.9, 6.5, 7.0, 7.4, 7.7, 8.0, 8.3, 8.5, 8.7],
       p50: [3.3, 4.5, 5.6, 6.4, 7.0, 7.5, 7.9, 8.3, 8.6, 8.9, 9.2, 9.4], p75: [3.7, 4.9, 6.0, 6.9, 7.6, 8.1, 8.5, 8.9, 9.3, 9.6, 9.9, 10.1], p99: [4.6, 6.0, 7.4, 8.3, 9.1, 9.7, 10.2, 10.7, 11.1, 11.4, 11.8, 12.1] },
  D: { p1: [2.3, 3.0, 3.8, 4.4, 4.8, 5.2, 5.5, 5.8, 6.0, 6.2, 6.4, 6.6], p25: [2.9, 3.8, 4.7, 5.4, 5.9, 6.4, 6.7, 7.0, 7.3, 7.6, 7.8, 8.0],
       p50: [3.2, 4.2, 5.1, 5.8, 6.4, 6.9, 7.3, 7.6, 7.9, 8.2, 8.5, 8.7], p75: [3.6, 4.6, 5.6, 6.4, 7.0, 7.5, 7.9, 8.3, 8.6, 8.9, 9.2, 9.5], p99: [4.4, 5.7, 6.9, 7.8, 8.6, 9.2, 9.7, 10.2, 10.6, 11.0, 11.3, 11.7] },
};
const PCTS = ['p1', 'p25', 'p50', 'p75', 'p99'];
// 생후 일수 → 각 백분위의 g (개월 사이는 직선으로 보간: 근사값)
function wfaAt(baby, ageDays) {
  const m = Math.max(0, Math.min(11, ageDays / 30.4375)), i = Math.min(10, Math.floor(m)), f = m - i;
  const out = {};
  for (const k of PCTS) out[k] = Math.round((WFA[baby][k][i] * (1 - f) + WFA[baby][k][i + 1] * f) * 1000);
  return out;
}
function pctLabel(baby, ageDays, g) {
  const b = wfaAt(baby, ageDays);
  if (g < b.p1) return '1백분위 미만';
  if (g < b.p25) return '1~25백분위';
  if (g < b.p50) return '25~50백분위';
  if (g < b.p75) return '50~75백분위';
  if (g < b.p99) return '75~99백분위';
  return '99백분위 이상';
}
// 체중 기반 수유량 (책 63쪽: 몸무게 × 120~150ml/일, 1회 = 하루량 ÷ 횟수(8~12회), 하루 1,000ml 넘지 않게)
function feedGuide(g) {
  const kg = g / 1000;
  const dayMin = Math.round(kg * 120), dayMax = Math.min(1000, Math.round(kg * 150));
  return { dayMin, dayMax, perMin: Math.round(dayMin / 12), perMax: Math.round(dayMax / 8) };
}
// 책 65쪽 월령표 (단태아 평균 체중 기준) — 비교용
const BOOK_AGE = [
  { upto: 28, label: '2주', avgKg: { S: 3.8, D: 3.6 }, perFeed: 80, gap: '2시간~2시간 30분', times: '8~12회' },
  { upto: 56, label: '6주', avgKg: { S: 4.9, D: 4.6 }, perFeed: 120, gap: '2시간 30분', times: '7~9회' },
  { upto: 75, label: '2개월', avgKg: { S: 5.6, D: 5.1 }, perFeed: 160, gap: '2시간 30분~3시간', times: '6~8회' },
  { upto: 120, label: '3개월', avgKg: { S: 6.2, D: 5.7 }, perFeed: 180, gap: '3~4시간', times: '5~7회' },
  { upto: 9999, label: '5개월', avgKg: { S: 7.5, D: 6.9 }, perFeed: 200, gap: '4시간', times: '4~6회' },
];
function bookRow(ageDays) { return BOOK_AGE.find(r => ageDays <= r.upto) || BOOK_AGE[BOOK_AGE.length - 1]; }
// 딸 최근 24시간 직수 패턴: 수유텀(시작→시작) 중앙값, 쪽별 평균 분, 30분 안에 이어진 수유(묶음) 수
function feedPattern(events, now) {
  const feeds = events.filter(e => (e.type === 'session' && e.kind !== 'pump') || (e.type === 'bottle' && e.baby === 'D')).filter(e => e.t > now - DAY && e.t <= now).sort((a, b) => a.t - b.t);
  const gaps = []; for (let i = 1; i < feeds.length; i++) gaps.push(feeds[i].t - feeds[i - 1].t);
  const sorted = gaps.slice().sort((a, b) => a - b);
  const median = sorted.length ? sorted[Math.floor(sorted.length / 2)] : null;
  const clusters = gaps.filter(g => g < 30 * 60e3).length;
  let sideMs = 0, sideN = 0;
  for (const e of feeds) if (e.type === 'session' && e.end) {
    const segs = e.segs && e.segs.length ? e.segs : [{ side: e.side, t: e.t }];
    segs.forEach((s, i) => { const ms = (i + 1 < segs.length ? segs[i + 1].t : e.end) - s.t; if (ms >= 60e3) { sideMs += ms; sideN++; } });
  }
  const weighed = feeds.filter(e => e.preG > 0 && e.postG > 0).map(e => e.postG - e.preG);
  return { count: feeds.length, median, clusters, sideAvgMin: sideN ? sideMs / sideN / 60000 : null, weighed };
}

/* ---------- 검진·접종 일정 (두 아이 각각) ----------
 * 출처: 질병관리청 국가예방접종(BCG 생후 4주 이내·34일까지, B형간염 0·1·6개월),
 * 국민건강보험공단 영유아건강검진(1차 생후 14~35일, 2차 4~6개월), 신생아 선별검사 안내.
 * 접종 백신 종류·간격의 최종 확인은 예방접종도우미(nip.kdca.go.kr)와 모자보건수첩으로. */
const CARE_ITEMS = [
  { id: 'hepb1', kind: '접종', name: 'B형간염 1차', from: { d: 0 }, to: { d: 1 }, hospital: true, note: '출생 시 병원에서. 퇴원요약지에서 날짜 확인' },
  { id: 'nbs', kind: '검사', name: '선천성대사이상검사 결과', from: { d: 2 }, to: { d: 14 }, hospital: true, note: '생후 48시간~7일에 병원에서 채혈. 결과가 정상인지 확인' },
  { id: 'hear', kind: '검사', name: '신생아 청각선별검사', from: { d: 0 }, to: { m: 1 }, hospital: true, note: '보통 출산 병원에서 퇴원 전. 생후 1개월 안. 재검이 나오면 3개월 안 정밀검사' },
  { id: 'chk1', kind: '검진', name: '영유아건강검진 1차', from: { d: 14 }, to: { d: 35 }, note: '키·몸무게·머리둘레 측정. 기간 안에 받으면 본인부담 없음' },
  { id: 'hepb2', kind: '접종', name: 'B형간염 2차', from: { m: 1 }, to: { m: 1, d: 14 }, note: '생후 1개월. BCG와 같은 날 맞기를 권장' },
  { id: 'bcg', kind: '접종', name: 'BCG(결핵, 피내용)', from: { d: 0 }, to: { d: 34 }, note: '생후 4주 이내(34일까지). 국가 지원은 피내용' },
  { id: 'm2', kind: '접종', name: '2개월 접종 (DTaP·폴리오·Hib·폐렴구균·로타 1차)', from: { m: 2 }, to: { m: 2, d: 14 }, note: '백신 종류와 간격은 예방접종도우미에서 확인' },
  { id: 'chk2', kind: '검진', name: '영유아건강검진 2차', from: { m: 4 }, to: { m: 6 }, note: '생후 4~6개월' },
];
function addAge(cfg, a) {
  const [y, mo, d] = cfg.birthDate.split('-').map(Number);
  return new Date(y, mo - 1 + (a.m || 0), d + (a.d || 0)).getTime();
}
function careSchedule(cfg) { return CARE_ITEMS.map(it => Object.assign({}, it, { fromT: addAge(cfg, it.from), toT: addAge(cfg, it.to) })); }
// 최근 'care' 기록: {type:'care', baby, item, status:'done'|'nicu'|'ok'|'undo', date}
function careStatus(events, baby, id) {
  let best = null;
  for (const e of events) if (e.type === 'care' && e.baby === baby && e.item === id && (!best || e.t > best.t)) best = e;
  return best && best.status !== 'undo' ? best : null;
}
// 해야 할 일: 기간이 열렸거나 7일 안에 열리는데 아직 안 한 것 (아이별)
function careDue(events, cfg, now) {
  const out = [];
  for (const it of careSchedule(cfg)) for (const baby of ['D', 'S']) {
    if (careStatus(events, baby, it.id)) continue;
    if (it.fromT > now + 7 * DAY) continue;
    out.push({ baby, item: it, overdue: !it.hospital && now > it.toT + DAY, open: now >= it.fromT, confirm: !!it.hospital });
  }
  return out.sort((a, b) => a.item.toT - b.item.toT);
}
// 울음 묶음: 30분 안에 이어진 울음을 하나로 보고, 그 사이 '그침'이 없으면 계속 우는 중
function cryEpisode(events, now) {
  const evs = events.filter(e => (e.type === 'cry' || e.type === 'calm') && e.t <= now && e.t > now - 3 * HOUR).sort((a, b) => b.t - a.t);
  if (!evs.length || evs[0].type === 'calm') return null;
  let start = evs[0].t;
  for (const e of evs) { if (e.type === 'calm') break; if (start - e.t > 30 * 60e3) break; start = e.t; }
  if (now - evs[0].t > 30 * 60e3) return null;
  return { start, minutes: Math.round((now - start) / 60000) };
}
/* LOGIC END */
