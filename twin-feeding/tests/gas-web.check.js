// node twin-feeding/tests/gas-web.check.js   (Playwright 필요)
// Apps Script 웹 페이지(stage1/gas/Index.html)를 브라우저에서 열고, Code.gs를 같은 페이지 안의
// 구글 서비스 흉내 환경에서 돌려 google.script.run을 연결한다. 단축어 호출 → 화면 반영 → 팩 차감까지 확인.
const { chromium } = require('playwright');
const fs = require('fs'), path = require('path');
const root = path.join(__dirname, '..');
(async () => {
  const code = fs.readFileSync(path.join(root, 'stage1/gas/Code.gs'), 'utf8');
  const index = fs.readFileSync(path.join(root, 'stage1/gas/Index.html'), 'utf8');
  const mock = `
  (function(){
    const saved = JSON.parse(sessionStorage.getItem('mockdb') || '{"rows":{},"props":{}}');
    const sheets = {}, props = saved.props;
    const persist = () => { const rows = {}; for (const n in sheets) rows[n] = sheets[n].rows; sessionStorage.setItem('mockdb', JSON.stringify({ rows, props })); };
    const mkSheet = name => { const sh = { rows: [] };
      const range = (r,c,nr,nc) => ({ getValues: () => Array.from({length:nr},(_,i)=>Array.from({length:nc},(_,j)=>((sh.rows[r-1+i]||[])[c-1+j] ?? ''))),
        setValues: v => { v.forEach((row,i)=>{ sh.rows[r-1+i] = sh.rows[r-1+i] || []; row.forEach((x,j)=>{ sh.rows[r-1+i][c-1+j] = x; }); }); persist(); },
        getValue: () => ((sh.rows[r-1]||[])[c-1] ?? ''), setNumberFormat(){ return this; },
        createTextFinder: t => ({ matchEntireCell(){ return this; }, findNext: () => { const i = sh.rows.findIndex(row => String(row[0]) === String(t)); return i >= 0 ? { getRow: () => i + 1 } : null; } }) });
      Object.assign(sh, { getLastRow: () => sh.rows.length, getRange: (a,b,c,d) => typeof a === 'string' ? range(1,1,sh.rows.length,1) : range(a,b,c||1,d||1), appendRow: v => { sh.rows.push(v.slice()); persist(); }, setFrozenRows(){} });
      return sh; };
    for (const n in saved.rows) { sheets[n] = mkSheet(n); sheets[n].rows = saved.rows[n]; }
    const ss = { getSheetByName: n => sheets[n] || null, insertSheet: n => (sheets[n] = mkSheet(n)), getUrl: () => 'https://docs.google.com/spreadsheets/d/TEST' };
    window.SpreadsheetApp = { openById: () => ss };
    window.PropertiesService = { getScriptProperties: () => ({ getProperty: k => props[k] ?? null, setProperty: (k,v) => { props[k] = String(v); persist(); } }) };
    window.LockService = { getScriptLock: () => ({ waitLock(){}, releaseLock(){} }) };
    window.Utilities = { getUuid: () => 'tok00000-0000-0000-0000-000000000000', formatDate: (d, tz, f) => f === 'H' ? String(d.getHours()) : d.toISOString().slice(0,16) };
    window.ContentService = { createTextOutput: s => ({ text: s }) };
    window.HtmlService = {}; window.ScriptApp = { getService: () => ({ getUrl: () => 'https://script.google.com/macros/s/TEST/exec' }) };
    window.Logger = { log(){} };
    window.__props = props;
  })();`;
  const bridge = `
    setup();
    window.TF_TOKEN = PropertiesService.getScriptProperties().getProperty('TOKEN');
    window.google = { script: { get run() {
      let ok = () => {}, no = () => {};
      const p = new Proxy({}, { get: (_, fn) => fn === 'withSuccessHandler' ? (f => { ok = f; return p; }) : fn === 'withFailureHandler' ? (f => { no = f; return p; })
        : (...args) => setTimeout(() => { try { ok(JSON.parse(JSON.stringify(window[fn](...args)))); } catch (e) { no(e); } }, 30) });
      return p; } } };
    window.shortcut = q => doGet({ parameter: Object.assign({ k: window.TF_TOKEN, by: 'mom', src: 'siri' }, q) }).text;`;
  const html = index.replace("<script>window.TF_BACKEND = 'gas'; window.TF_TOKEN = '__TOKEN__';</script>",
    '<script>' + mock + '</script><script>(function(){\n' + code + "\nObject.assign(window, { setup, doGet, act_, api_getAll, api_rev, api_addEvent, api_patchEvent, api_getBag, api_setBag, api_updateBag, api_setConfig, readEvents_ });\n})();\n" + bridge + "\nwindow.TF_BACKEND = 'gas';</script>");
  const file = path.join(require('os').tmpdir(), 'tf-gas-web.html');
  fs.writeFileSync(file, '<!doctype html><html><head><meta charset=utf8><meta name=viewport content="width=device-width,initial-scale=1"></head><body>' + html + '</body></html>');
  const b = await chromium.launch(); const p = await b.newPage({ viewport: { width: 390, height: 844 } });
  const errs = []; p.on('pageerror', e => errs.push(e.message));
  await p.addInitScript(() => { if (!localStorage.getItem('tf.me')) localStorage.setItem('tf.me', '"mom"'); });
  await p.goto('file://' + file); await p.waitForTimeout(600);
  const res = {};
  res.syncOk = await p.$eval('#sync', x => x.className);
  // 단축어로 직수 시작 → 화면(8초 주기 대신 다시 불러오기)에 진행 중 표시
  res.siriStart = await p.evaluate(() => window.shortcut({ a: 'start', kind: '직수', side: '왼' }));
  // 페이지는 8초마다 바뀐 게 있는지 확인: 진행 중 표시가 뜰 때까지 최대 20초
  await p.waitForFunction(() => /직수 중/.test((document.querySelector('.title h1') || {}).textContent || ''), null, { timeout: 20000 }).catch(() => {});
  res.momTitle = await p.textContent('.title h1');
  res.siriEnd = await p.evaluate(() => window.shortcut({ a: 'end' }));
  // 아빠가 팩을 하나 저장해 두고, 엄마가 단축어로 모유 젖병 60ml → 아빠 화면이 열리면 차감
  await p.evaluate(() => { api_setBag(window.TF_TOKEN, { id: 'bagA', code: '1122-0800', ml: 100, state: 'fridge', for: 'any', pumpedAt: Date.now() - 3600e3, stateAt: Date.now() }); });
  res.siriBottle = await p.evaluate(() => window.shortcut({ a: 'bottle', ml: '60', milk: '모유' }));
  res.siriCry = await p.evaluate(() => window.shortcut({ a: 'cry' }));
  await p.evaluate(() => localStorage.setItem('tf.me', '"dad"')); await p.reload();
  // 아빠 화면이 열리면 팩 차감이 끝날 때까지 최대 10초 기다림
  await p.waitForFunction(() => { const g = api_getBag(window.TF_TOKEN, 'bagA'); return g && g.bag.ml !== 100 && readEvents_().some(e => e.type === 'bottle' && e.applied === true); }, null, { timeout: 10000 }).catch(() => {});
  res.bagAfter = await p.evaluate(() => { const g = api_getBag(window.TF_TOKEN, 'bagA'); return g.bag.ml + ':' + g.bag.state + ':' + JSON.stringify(g.bag.used); });
  res.bottleApplied = await p.evaluate(() => readEvents_().filter(e => e.type === 'bottle').map(e => e.applied));
  await p.click('nav.tabs [data-tab="log"]'); await p.waitForTimeout(200);
  res.logHasCry = /울음/.test(await p.textContent('#main'));
  await p.click('#gear'); await p.waitForTimeout(200);
  res.execUrlShown = await p.$eval('#execUrl', x => x.value).catch(() => null);
  console.log(JSON.stringify(res, null, 1)); console.log('errors', errs);
  await b.close();
  const ok = res.syncOk.includes('ok') && /왼쪽 직수 중/.test(res.momTitle) && res.bagAfter.startsWith('40:') && res.bottleApplied[0] === true && res.logHasCry && /exec\?k=/.test(res.execUrlShown || '') && !errs.length;
  console.log(ok ? 'PASS' : 'FAIL'); process.exit(ok ? 0 : 1);
})();
