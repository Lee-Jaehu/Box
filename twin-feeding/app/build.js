// node twin-feeding/app/build.js → app/index.html (아티팩트로 게시하는 단일 파일)
const fs = require('fs'), path = require('path');
const src = f => fs.readFileSync(path.join(__dirname, 'src', f), 'utf8');
const html = src('shell.html').replace('<!--ICONS-->', src('icons.svg.html').trim())
  + '\n<script id="logic">\n' + src('logic.js') + '</script>\n<script>\n' + src('ui.js') + '</script>\n';
fs.writeFileSync(path.join(__dirname, 'index.html'), html);
console.log('index.html', (html.length / 1024).toFixed(1) + 'KB');
