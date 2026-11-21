// node twin-feeding/app/build.js
//  → app/index.html            : Claude 아티팩트용 (공유 DB)
//  → stage1/gas/Index.html     : 구글 Apps Script 웹 페이지용 (아내도 Claude 계정 없이)
//  → stage1/gas/project.json   : Apps Script 프로젝트 가져오기용 (Code.gs + Index.html + 매니페스트)
const fs = require('fs'), path = require('path');
const src = f => fs.readFileSync(path.join(__dirname, 'src', f), 'utf8');
const body = (pre) => src('shell.html').replace('<!--ICONS-->', src('icons.svg.html').trim())
  + pre + '\n<script id="logic">\n' + src('logic.js') + '</script>\n<script>\n' + src('ui.js') + '</script>\n';
const art = body('');
fs.writeFileSync(path.join(__dirname, 'index.html'), art);
const gasDir = path.join(__dirname, '..', 'stage1', 'gas');
const gasHtml = body('\n<script>window.TF_BACKEND = \'gas\'; window.TF_TOKEN = \'__TOKEN__\';</script>');
if (gasHtml.includes('<?')) throw new Error('Index.html에 <? 가 있으면 HtmlService가 깨질 수 있어요');
fs.writeFileSync(path.join(gasDir, 'Index.html'), gasHtml);
const manifest = { timeZone: 'Asia/Seoul', exceptionLogging: 'STACKDRIVER', runtimeVersion: 'V8',
  oauthScopes: ['https://www.googleapis.com/auth/spreadsheets', 'https://www.googleapis.com/auth/script.external_request', 'https://www.googleapis.com/auth/script.scriptapp'],
  webapp: { executeAs: 'USER_DEPLOYING', access: 'ANYONE_ANONYMOUS' } };
fs.writeFileSync(path.join(gasDir, 'appsscript.json'), JSON.stringify(manifest, null, 2) + '\n');
console.log('index.html', (art.length / 1024).toFixed(1) + 'KB · gas Index.html', (gasHtml.length / 1024).toFixed(1) + 'KB');
