import { readFile, writeFile, mkdir, mkdtemp, rm } from 'node:fs/promises';
import { dirname, resolve, extname } from 'node:path';
import { fileURLToPath } from 'node:url';
import { parseArgs, promisify } from 'node:util';
import { execFile } from 'node:child_process';
import { tmpdir } from 'node:os';
import { renderDeck } from './render.mjs';

const ROOT = resolve(dirname(fileURLToPath(import.meta.url)), '..');
const fail = (path, message) => { throw new Error(`${path}: ${message}`); };
const text = (v, path, optional = false) => {
  if (optional && v === undefined) return;
  if (typeof v !== 'string' || !v.trim()) fail(path, '需要非空文字');
};
const object = (v, path) => {
  if (!v || typeof v !== 'object' || Array.isArray(v)) fail(path, '需要对象');
};
const list = (v, path, max = 100) => {
  if (!Array.isArray(v) || !v.length || v.length > max) fail(path, `需要 1–${max} 个项目`);
};
const strings = (v, path, max = 100) => {
  list(v, path, max); v.forEach((x, i) => text(x, `${path}[${i}]`));
};

function chart(v, path) {
  object(v, path);
  if (!['bar', 'line'].includes(v.type)) fail(path, 'chart.type 仅支持 bar / line');
  text(v.title, `${path}.title`);
  strings(v.labels, `${path}.labels`, 16);
  list(v.series, `${path}.series`, 4);
  v.series.forEach((s, i) => {
    object(s, `${path}.series[${i}]`); text(s.name, `${path}.series[${i}].name`);
    if (!Array.isArray(s.values) || s.values.length !== v.labels.length || s.values.some(n => typeof n !== 'number' || !Number.isFinite(n))) {
      fail(`${path}.series[${i}].values`, '每个类别都须有一个有限数值，不能缺值或使用字符串');
    }
    if (s.values.some(n => n !== 0 && (Math.abs(n) < 1e-100 || Math.abs(n) > 1e100))) fail(`${path}.series[${i}].values`, '数值量级超出绘图范围，请先转换单位（非零绝对值范围 1e-100–1e100）');
  });
  text(v.unit, `${path}.unit`, true);
}

function picture(v, path) {
  object(v, path); text(v.src, `${path}.src`); text(v.alt, `${path}.alt`);
  if (v.fit !== undefined && !['contain', 'cover'].includes(v.fit)) fail(path, 'image.fit 仅支持 contain / cover');
}

function indices(values, path, size, max = size) {
  if (values === undefined) return;
  if (!Array.isArray(values) || values.length > max || new Set(values).size !== values.length || values.some(n => !Number.isInteger(n) || n < 0 || n >= size)) fail(path, `需要不重复的零基索引，范围 0–${size - 1}，最多 ${max} 个`);
}

function table(v, path) {
  object(v, path); strings(v.columns, `${path}.columns`, 10);
  text(v.title, `${path}.title`, true); list(v.rows, `${path}.rows`, 15);
  v.rows.forEach((row, j) => {
    if (!Array.isArray(row) || row.length !== v.columns.length || row.some(x => typeof x !== 'string' && !(typeof x === 'number' && Number.isFinite(x)))) fail(`${path}.rows[${j}]`, '单元格数须匹配表头，值为文字或有限数值');
  });
  if (v.mode !== undefined && !['striped', 'row-highlight', 'compact-comparison', 'task-list'].includes(v.mode)) fail(`${path}.mode`, '使用 striped / row-highlight / compact-comparison / task-list');
  indices(v.numericColumns, `${path}.numericColumns`, v.columns.length);
  indices(v.highlightRows, `${path}.highlightRows`, v.rows.length, 2);
  indices(v.subtotalRows, `${path}.subtotalRows`, v.rows.length);
  if (v.columnWidths !== undefined && (!Array.isArray(v.columnWidths) || v.columnWidths.length !== v.columns.length || v.columnWidths.some(n => typeof n !== 'number' || !Number.isFinite(n) || n <= 0) || Math.abs(v.columnWidths.reduce((a, b) => a + b, 0) - 100) > .01)) fail(`${path}.columnWidths`, '列宽需要为正百分比，数量匹配表头且合计为 100');
  if (v.mode === 'task-list' && (v.columns.length !== 3 || v.rows.length < 3 || v.rows.length > 5)) fail(path, 'task-list 需要序号、模块、说明三列及 3–5 行');
}

function diagram(v, path) {
  object(v, path); text(v.title, `${path}.title`);
  if (!['flow', 'matrix'].includes(v.type)) fail(`${path}.type`, '使用 flow / matrix');
  list(v.items, `${path}.items`, v.type === 'flow' ? 4 : 6);
  if (v.items.length < 2) fail(`${path}.items`, '至少需要两个信息节点');
  v.items.forEach((item, i) => { object(item, `${path}.items[${i}]`); text(item.label, `${path}.items[${i}].label`); text(item.detail, `${path}.items[${i}].detail`, true); });
  if (v.focus !== undefined && (!Number.isInteger(v.focus) || v.focus < 0 || v.focus >= v.items.length)) fail(`${path}.focus`, '必须是 items 内的零基索引');
  if (v.direction !== undefined && (v.type !== 'flow' || !['horizontal', 'vertical'].includes(v.direction))) fail(`${path}.direction`, '仅 flow 支持 horizontal / vertical');
  if (v.columns !== undefined && (v.type !== 'matrix' || ![2, 3].includes(v.columns))) fail(`${path}.columns`, '仅 matrix 支持 2 或 3 列');
}

export function validateDeck(deck) {
  object(deck, 'deck'); text(deck.title, 'deck.title'); list(deck.slides, 'deck.slides', 200);
  if (deck.lang !== undefined && !['zh-CN', 'en'].includes(deck.lang)) fail('deck.lang', '使用 zh-CN 或 en');
  deck.slides.forEach((s, i) => {
    const p = `slides[${i}]`;
    object(s, p); text(s.title, `${p}.title`);
    if (s.lang !== undefined && !['zh-CN', 'en'].includes(s.lang)) fail(`${p}.lang`, '使用 zh-CN 或 en');
    for (const key of ['source', 'notes', 'lead']) text(s[key], `${p}.${key}`, true);
    text(s.visualExemption, `${p}.visualExemption`, true);
    if (s.visualTextBinding !== undefined) {
      object(s.visualTextBinding, `${p}.visualTextBinding`);
      for (const key of ['supportsClaim', 'textAnchor', 'informationCarried']) text(s.visualTextBinding[key], `${p}.visualTextBinding.${key}`);
      for (const key of ['visualType', 'sourceOrGeneration', 'whyThisVisual']) text(s.visualTextBinding[key], `${p}.visualTextBinding.${key}`, true);
    }
    if (s.visualExemption && s.visualTextBinding) fail(p, 'visualExemption 与 visualTextBinding 不能同时声明');
    if (s.source !== undefined && ['cover', 'agenda', 'closing'].includes(s.layout)) fail(`${p}.source`, '本版式没有来源区域，请放到正文页');
    switch (s.layout) {
      case 'cover':
        for (const k of ['subtitle', 'presenter', 'date']) text(s[k], `${p}.${k}`, true);
        break;
      case 'agenda':
        strings(s.items, `${p}.items`, 7);
        if (s.active !== undefined && (!Number.isInteger(s.active) || s.active < 0 || s.active >= s.items.length)) fail(`${p}.active`, '必须是 items 内的零基索引');
        break;
      case 'text': strings(s.paragraphs, `${p}.paragraphs`, 12); break;
      case 'two-column':
        object(s.left, `${p}.left`); strings(s.left.paragraphs, `${p}.left.paragraphs`, 8);
        text(s.left.heading, `${p}.left.heading`, true);
        object(s.right, `${p}.right`); text(s.right.heading, `${p}.right.heading`, true);
        if (['paragraphs', 'chart', 'image', 'table', 'diagram'].filter(k => s.right[k] !== undefined).length !== 1) fail(`${p}.right`, 'paragraphs / chart / image / table / diagram 必须选一个');
        if (s.right.paragraphs) strings(s.right.paragraphs, `${p}.right.paragraphs`, 8);
        if (s.right.chart) chart(s.right.chart, `${p}.right.chart`);
        if (s.right.image) picture(s.right.image, `${p}.right.image`);
        if (s.right.table) table(s.right.table, `${p}.right.table`);
        if (s.right.diagram) diagram(s.right.diagram, `${p}.right.diagram`);
        break;
      case 'chart': chart(s.chart, `${p}.chart`); break;
      case 'table': table(s.table, `${p}.table`); break;
      case 'diagram': diagram(s.diagram, `${p}.diagram`); break;
      case 'image': picture(s.image, `${p}.image`); break;
      case 'closing': if (s.contact !== undefined) strings(s.contact, `${p}.contact`, 4); break;
      default: fail(`${p}.layout`, `不支持 ${JSON.stringify(s.layout)}`);
    }
  });
  return deck;
}

const uri = (bytes, mime) => `data:${mime};base64,${bytes.toString('base64')}`;
export async function embedPicture(img, base) {
  // Only inert raster formats are accepted. Remote URLs are never fetched implicitly.
  if (/^data:image\/(png|jpeg|webp|gif);base64,[A-Za-z0-9+/=\s]+$/.test(img.src)) return;
  if (/^[a-z][a-z0-9+.-]*:/i.test(img.src)) fail('image.src', '使用本地 PNG/JPEG/WebP/GIF 文件或对应 data URI');
  const path = resolve(base, img.src);
  const mime = { '.png': 'image/png', '.jpg': 'image/jpeg', '.jpeg': 'image/jpeg', '.webp': 'image/webp', '.gif': 'image/gif' }[extname(path).toLowerCase()];
  if (!mime) fail('image.src', '支持 PNG/JPEG/WebP/GIF；先将其它格式转换为图片');
  img.src = uri(await readFile(path), mime);
}

async function readFont(fontPath) {
  const candidates = fontPath ? [resolve(fontPath)] : [resolve(ROOT, 'assets/fonts/efund.woff2'), ...(process.env.EFUND_FONT ? [resolve(process.env.EFUND_FONT)] : []), ...(process.env.HOME ? [resolve(process.env.HOME, 'Library/Fonts/STHeiti_YFD.ttf')] : [])];
  for (const path of candidates) {
    try {
      let bytes = await readFile(path);
      const signature = bytes.subarray(0, 4).toString('hex');
      const mime = { '774f4632': 'font/woff2', '774f4646': 'font/woff', '00010000': 'font/ttf', '4f54544f': 'font/otf' }[signature];
      if (!mime) fail('font', '字体文件格式无效');
      if (path !== resolve(ROOT, 'assets/fonts/efund.woff2')) {
        // The supplied TTF has an invalid vhea version that Chromium's sanitizer rejects.
        // Normalize a temporary copy; never modify the installed/source font.
        const dir = await mkdtemp(resolve(tmpdir(), 'efund-font-'));
        try {
          await promisify(execFile)('uv', ['run', resolve(ROOT, 'scripts/convert_template.py'), '--font-only', '--font', path, '--out', dir], { timeout: 180000 });
          bytes = await readFile(resolve(dir, 'fonts/efund.woff2'));
          return uri(bytes, 'font/woff2');
        } finally { await rm(dir, { recursive: true, force: true }); }
      }
      return uri(bytes, mime);
    } catch (e) { if (e.code !== 'ENOENT') throw e; }
  }
  fail('font', '未找到华文黑体_易方达。用 --font <字体文件> 或 EFUND_FONT 指定；不会静默替换字体。');
}

export async function build({ input, output, font, force = false }) {
  if (!input || !output) fail('arguments', '需要 --input 和 --output');
  const dest = resolve(output);
  const deck = validateDeck(JSON.parse(await readFile(resolve(input), 'utf8')));
  const base = dirname(resolve(input));
  for (const s of deck.slides) {
    if (s.image) await embedPicture(s.image, base);
    if (s.right?.image) await embedPicture(s.right.image, base);
  }
  const manifest = JSON.parse(await readFile(resolve(ROOT, 'assets/template-manifest.json'), 'utf8'));
  const backgrounds = {};
  for (const name of ['cover-cn', 'cover-en', 'toc', 'content', 'ending-cn', 'ending-en']) backgrounds[name] = uri(await readFile(resolve(ROOT, `assets/backgrounds/${name}.svg`)), 'image/svg+xml');
  const latinFonts = {};
  for (const weight of ['regular', 'bold']) latinFonts[weight] = uri(await readFile(resolve(ROOT, `assets/fonts/arial-${weight}.woff2`)), 'font/woff2');
  const html = renderDeck(deck, {
    backgrounds, font: await readFont(font), latinFonts, width: manifest.canvas.px.width, height: manifest.canvas.px.height,
    css: await readFile(resolve(ROOT, 'templates/slides.css'), 'utf8'),
    player: await readFile(resolve(ROOT, 'templates/player.js'), 'utf8'),
  });
  await mkdir(dirname(dest), { recursive: true });
  await writeFile(dest, html, { flag: force ? 'w' : 'wx' });
  return { output: dest, slides: deck.slides.length, bytes: Buffer.byteLength(html), template: manifest.source?.sha256 ?? manifest.source_sha256 ?? 'V5' };
}

if (import.meta.main) {
  try {
    const { values } = parseArgs({ options: { input: { type: 'string' }, output: { type: 'string' }, font: { type: 'string' }, force: { type: 'boolean' }, help: { type: 'boolean' } } });
    if (values.help) console.log('bun scripts/build.mjs --input deck.json --output slides.html [--font FONT] [--force]\n输入 schema 见 references/authoring.md；默认保留已有输出。');
    else console.log(JSON.stringify(await build(values), null, 2));
  } catch (e) { console.error(e.message); process.exitCode = 1; }
}
