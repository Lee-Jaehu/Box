// Scriptable 위젯 스크립트를 가짜 Scriptable 환경에서 돌려 본다 (실제 아이폰 표시는 기기에서 확인)
const fs = require('fs'), path = require('path'), assert = require('assert');
const src = fs.readFileSync(path.join(__dirname, '..', 'stage1', 'widget', 'twin-widget.js'), 'utf8');

function env(family, json, opts = {}) {
  const texts = [], dates = [], files = {};
  let set = null;
  const node = () => ({
    addText(s) { const t = { text: s, centerAlignText() {} }; texts.push(s); return t; },
    addDate(d) { const x = { date: d, style: null, applyTimerStyle() { this.style = 'timer'; }, applyRelativeStyle() { this.style = 'relative'; }, centerAlignText() {} }; dates.push(x); return x; },
    addStack() { return node(); }, addSpacer() {},
  });
  class ListWidget { constructor() { Object.assign(this, node()); } presentSmall() { set = this; } }
  const g = {
    args: { widgetParameter: opts.param === undefined ? 'https://script.google.com/macros/s/X/exec?k=abc' : opts.param },
    config: { runsInWidget: true, widgetFamily: family },
    ListWidget, Font: new Proxy({}, { get: () => () => ({}) }), Color: function (h) { this.hex = h; },
    Keychain: { contains: () => false, get: () => null, set() {} },
    FileManager: { local: () => ({ joinPath: (a, b) => a + '/' + b, cacheDirectory: () => '/c', writeString: (p, s) => { files[p] = s; }, readString: p => files[p], fileExists: p => p in files }) },
    Request: function (url) { this.url = url; g.lastUrl = url; this.loadJSON = async () => { if (json instanceof Error) throw json; return json; }; },
    Script: { setWidget(w) { set = w; }, complete() {} },
    Alert: function () {},
    __TF_WIDGET_TEST__: {},
  };
  return { g, texts, dates, files, get set() { return set; } };
}
async function run(family, json, opts) {
  const e = env(family, json, opts);
  new Function(...Object.keys(e.g), 'globalThis', 'return (async () => {' + src + '})()')(...Object.values(e.g), e.g);
  await new Promise(r => setTimeout(r, 0));
  await e.g.__TF_WIDGET_TEST__.api.main();
  return e;
}

const NOW = Date.UTC(2026, 10, 22, 14, 0);
const idle = { now: NOW, running: null, lastFeed: { t: NOW - 95 * 60e3, label: '오른쪽에서 끝' }, nextSide: '왼쪽', lastDiaper: NOW - 40 * 60e3, crying: null };
const running = Object.assign({}, idle, { running: { t: NOW - 12 * 60e3, label: '왼쪽 직수', long: false } });
const longNight = Object.assign({}, idle, { running: { t: NOW - 34 * 60e3, label: '왼쪽 직수', long: true } });
const crying = Object.assign({}, idle, { crying: { start: NOW - 22 * 60e3, minutes: 22 } });

let n = 0;
const test = async (name, fn) => { await fn(); n++; console.log('ok', name); };
(async () => {
  await test('asks the server for the widget summary using the parameter address', async () => {
    const e = await run('accessoryRectangular', idle);
    assert.strictEqual(e.g.lastUrl, 'https://script.google.com/macros/s/X/exec?k=abc&a=widget');
    assert.ok(e.set, 'widget set');
  });
  await test('rectangular, idle: last feed counts up relative, next side and diaper shown', async () => {
    const e = await run('accessoryRectangular', idle);
    assert.deepStrictEqual(e.texts.slice(0, 2), ['마지막 수유 · 오른쪽에서 끝', '다음 왼쪽 · 기저귀']);
    assert.strictEqual(e.dates[0].style, 'relative'); assert.strictEqual(+e.dates[0].date, idle.lastFeed.t);
    assert.strictEqual(e.dates[1].style, 'relative'); assert.strictEqual(+e.dates[1].date, idle.lastDiaper);
  });
  await test('rectangular, running: a live timer from the start time', async () => {
    const e = await run('accessoryRectangular', running);
    assert.strictEqual(e.texts[0], '왼쪽 직수'); assert.strictEqual(e.dates[0].style, 'timer'); assert.strictEqual(+e.dates[0].date, running.running.t);
  });
  await test('night feed over 30 minutes and long crying are flagged, with the safety line', async () => {
    let e = await run('accessoryRectangular', longNight);
    assert.strictEqual(e.texts[0], '왼쪽 직수 · 30분 넘음'); assert.ok(/침대/.test(e.texts[1]));
    e = await run('accessoryRectangular', crying);
    assert.strictEqual(e.texts[0], '울음 22분째'); assert.ok(/흔들지/.test(e.texts[1]));
    e = await run('accessoryCircular', crying); assert.strictEqual(e.texts[0], '!');
  });
  await test('inline and circular fit their size', async () => {
    let e = await run('accessoryInline', running); assert.strictEqual(e.texts[0], '왼쪽 직수 진행 중 '); assert.strictEqual(e.dates[0].style, 'timer');
    e = await run('accessoryCircular', idle); assert.strictEqual(e.texts[0], '왼');
    e = await run('small', idle); assert.ok(e.texts.includes('기저귀 '));
  });
  await test('offline: shows the last saved summary marked as old; nothing saved → asks to check address', async () => {
    const e1 = env('accessoryRectangular', new Error('offline'));
    e1.files['/c/tf-widget-cache.json'] = JSON.stringify(idle);
    new Function(...Object.keys(e1.g), 'globalThis', 'return (async () => {' + src + '})()')(...Object.values(e1.g), e1.g);
    await e1.g.__TF_WIDGET_TEST__.api.main();
    assert.ok(e1.texts.some(t => /예전 정보/.test(t)), e1.texts.join('|'));
    const e2 = await run('accessoryRectangular', new Error('offline'));
    assert.ok(e2.texts.some(t => /주소를 확인/.test(t)));
    const e3 = await run('accessoryRectangular', idle, { param: '' });
    assert.ok(e3.texts.some(t => /주소를 확인/.test(t)) && !e3.g.lastUrl);
  });
  console.log('\n' + n + ' tests passed');
})().catch(e => { console.error(e); process.exit(1); });
