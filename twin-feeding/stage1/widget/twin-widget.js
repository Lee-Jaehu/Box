// 쌍둥이 수유 보드 — 잠금화면 위젯 (Scriptable 앱용)
// 설치: Scriptable 앱 → + → 이 파일 내용 붙여넣기 → 이름 '수유 위젯'.
// 잠금화면 편집 → 위젯 추가 → Scriptable → 'Script: 수유 위젯', 'Parameter: 단축어에 넣는 기록 주소(…/exec?k=…)'.
// 화면을 켜면 진행 중 수유 시간이 초 단위로 올라가고(아이폰이 직접 셈), 상황 자체는 iOS가 허락하는 간격(보통 5~15분)마다 새로 읽는다.
// 이름·체중은 받지 않는다: 잠금화면은 누구나 볼 수 있으니까.

const KEY = 'tf.base';
const CACHE = 'tf-widget-cache.json';
const fm = FileManager.local();
const cachePath = fm.joinPath(fm.cacheDirectory(), CACHE);

async function base() {
  const p = (args.widgetParameter || '').trim();
  if (p) return p;
  if (Keychain.contains(KEY)) return Keychain.get(KEY);
  if (config.runsInWidget) return null;
  const a = new Alert();
  a.title = '기록 주소';
  a.message = '단축어에 넣는 주소(…/exec?k=…)를 붙여 넣어 주세요.';
  a.addTextField('https://script.google.com/macros/s/…/exec?k=…');
  a.addAction('저장'); a.addCancelAction('취소');
  if ((await a.present()) < 0) return null;
  const v = a.textFieldValue(0).trim();
  if (v) Keychain.set(KEY, v);
  return v || null;
}

async function load(b) {
  try {
    const r = new Request(b + (b.includes('?') ? '&' : '?') + 'a=widget');
    r.timeoutInterval = 10;
    const d = await r.loadJSON();
    if (!d || typeof d.now !== 'number') throw new Error('bad');
    fm.writeString(cachePath, JSON.stringify(d));
    return { d, stale: false };
  } catch (e) {
    if (fm.fileExists(cachePath)) return { d: JSON.parse(fm.readString(cachePath)), stale: true };
    return { d: null, stale: true };
  }
}

// 위젯에 쓸 문장 만들기 (시험 가능하도록 따로 둠)
function lines(d) {
  if (!d) return { title: '수유 보드', main: null, sub: '주소를 확인해 주세요', inline: '수유 보드 · 주소 확인' };
  if (d.crying && d.crying.minutes >= 20) return { title: '울음 ' + d.crying.minutes + '분째', main: { t: d.crying.start, style: 'timer' }, sub: '흔들지 말고, 힘들면 침대에 눕히고 쉬기', inline: '울음 ' + d.crying.minutes + '분째', alert: true };
  if (d.running) return { title: d.running.label + (d.running.long ? ' · 30분 넘음' : ''), main: { t: d.running.t, style: 'timer' }, sub: d.running.long ? '졸리면 아기 먼저 침대에' : '다음 ' + d.nextSide, inline: d.running.label + ' 진행 중', alert: !!d.running.long };
  const sub = '다음 ' + d.nextSide + (d.lastDiaper ? ' · 기저귀' : '');
  return { title: d.lastFeed ? '마지막 수유 · ' + d.lastFeed.label : '수유 기록 없음', main: d.lastFeed ? { t: d.lastFeed.t, style: 'relative' } : null, sub, diaper: d.lastDiaper, inline: '다음 ' + d.nextSide + (d.lastFeed ? ' · 수유' : '') };
}

function addWhen(stack, m, font) {
  const x = stack.addDate(new Date(m.t));
  if (m.style === 'timer') x.applyTimerStyle(); else x.applyRelativeStyle();
  x.font = font;
  return x;
}

function build(d, stale, family, b) {
  const L = lines(d);
  const w = new ListWidget();
  if (b) w.url = b;
  w.refreshAfterDate = new Date(Date.now() + 5 * 60e3);
  if (family === 'accessoryInline') {
    // 한 줄: 시간 앞에 붙는 글자는 iOS가 한 줄로 합쳐 보여 준다
    if (L.main) { const s = w.addStack(); s.addText(L.inline + ' '); addWhen(s, L.main, Font.body()); }
    else w.addText(L.inline);
    return w;
  }
  if (family === 'accessoryCircular') {
    w.addAccessoryWidgetBackground = true;
    const t = w.addText(L.alert ? '!' : d && d.running ? '수유' : d ? d.nextSide.slice(0, 1) : '?');
    t.font = Font.boldSystemFont(15); t.centerAlignText();
    if (L.main) { const x = addWhen(w, L.main, Font.systemFont(11)); x.centerAlignText(); }
    return w;
  }
  if (family === 'accessoryRectangular') {
    const t = w.addText(L.title); t.font = Font.boldSystemFont(13); t.lineLimit = 1;
    if (L.main) addWhen(w, L.main, Font.systemFont(15));
    const s = w.addStack();
    const st = s.addText(L.sub + (stale ? ' · 예전 정보' : '')); st.font = Font.systemFont(11); st.lineLimit = 1;
    if (L.diaper && !L.alert) { s.addText(' '); addWhen(s, { t: L.diaper, style: 'relative' }, Font.systemFont(11)); }
    return w;
  }
  // 홈 화면 작은 위젯
  w.backgroundColor = L.alert ? new Color('#FFF4E5') : new Color('#FFFFFF');
  const t = w.addText(L.title); t.font = Font.semiboldSystemFont(13); t.textColor = new Color('#4E5968');
  w.addSpacer(4);
  if (L.main) { const x = addWhen(w, L.main, Font.boldSystemFont(24)); x.textColor = new Color(L.alert ? '#D9480F' : '#191F28'); }
  w.addSpacer();
  const st = w.addText(L.sub); st.font = Font.systemFont(12); st.textColor = new Color('#8B95A1');
  if (L.diaper) { const s = w.addStack(); const a = s.addText('기저귀 '); a.font = Font.systemFont(12); a.textColor = new Color('#8B95A1'); const x = addWhen(s, { t: L.diaper, style: 'relative' }, Font.systemFont(12)); x.textColor = new Color('#8B95A1'); }
  if (stale) { const z = w.addText('예전 정보 · 연결 확인'); z.font = Font.systemFont(10); z.textColor = new Color('#F04452'); }
  return w;
}

async function main() {
  const b = await base();
  const { d, stale } = b ? await load(b) : { d: null, stale: true };
  const family = config.widgetFamily || 'small';
  const w = build(d, stale, family, b);
  if (config.runsInWidget) Script.setWidget(w);
  else if (family === 'small') await w.presentSmall();
  Script.complete();
  return w;
}

// Scriptable에도 module이 있으므로, 시험(node)에서만 켜는 표시로 구분
if (globalThis.__TF_WIDGET_TEST__) globalThis.__TF_WIDGET_TEST__.api = { lines, build, main };
else await main();
