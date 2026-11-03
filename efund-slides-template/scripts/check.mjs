import { chromium } from 'playwright';
import { mkdir, writeFile } from 'node:fs/promises';
import { resolve } from 'node:path';
import { pathToFileURL } from 'node:url';
import { parseArgs } from 'node:util';

// The same checks are used for authoring QA and optional PDF export.
export async function check({ input, out, pdf = false, browser: executablePath, channel = 'chrome' }) {
  const htmlPath = resolve(input), outDir = resolve(out);
  await mkdir(outDir, { recursive: true });
  const instance = await chromium.launch({ headless: true, ...(executablePath ? { executablePath } : { channel }) });
  const issues = [], errors = [], requests = [];
  try {
    const page = await instance.newPage({ viewport: { width: 1200, height: 760 }, deviceScaleFactor: 1 });
    page.on('pageerror', e => errors.push(e.message));
    page.on('console', message => { if (message.type() === 'error') errors.push(message.text()); });
    page.on('request', req => { if (/^https?:/.test(req.url())) requests.push(req.url()); });
    await page.goto(pathToFileURL(htmlPath).href, { waitUntil: 'load' });
    await page.evaluate(async () => { if (!window.efund) throw new Error('缺少 efund 播放器'); await window.efund.ready; });
    const state = await page.evaluate(() => ({
      count: document.querySelectorAll('.slide').length,
      fonts: [...document.fonts].map(f => ({ family: f.family, status: f.status })),
      images: [...document.images].filter(i => !i.complete || !i.naturalWidth).map(i => i.alt || 'background'),
      overflow: window.efund.checkOverflow(),
    }));
    issues.push(...state.overflow);
    const invalidGeometry = await page.evaluate(() => [...document.querySelectorAll('.data-chart *')].flatMap(el => [...el.attributes].filter(a => /(?:NaN|Infinity)/.test(a.value) && ['x', 'y', 'x1', 'x2', 'y1', 'y2', 'cx', 'cy', 'r', 'width', 'height', 'points', 'd'].includes(a.name)).map(a => `${el.tagName}.${a.name}=${a.value}`)));
    if (invalidGeometry.length) issues.push({ reason: '图表几何数值无效', attributes: invalidGeometry });
    if (!state.fonts.some(f => f.family.replace(/['"]/g, '') === 'EFund' && f.status === 'loaded')) issues.push({ reason: '品牌字体未加载' });
    if (state.images.length) issues.push({ reason: '图片加载失败', images: state.images });
    for (let i = 0; i < state.count; i++) {
      await page.evaluate(n => window.efund.goTo(n), i);
      await page.evaluate(() => new Promise(resolve => requestAnimationFrame(() => requestAnimationFrame(resolve))));
      await page.locator('.slide[data-active]').screenshot({ path: resolve(outDir, `slide-${String(i + 1).padStart(2, '0')}.png`) });
    }
    await page.evaluate(() => window.efund.goTo(0));
    if (state.count > 1) {
      await page.locator('body').click({ position: { x: 2, y: 2 } });
      await page.keyboard.press('ArrowRight');
      if (await page.evaluate(() => window.efund.currentIndex) !== 1) issues.push({ reason: '右键翻页失败' });
      await page.keyboard.press('Home');
      if (await page.evaluate(() => window.efund.currentIndex) !== 0) issues.push({ reason: 'Home 翻页失败' });
    }
    await page.setViewportSize({ width: 390, height: 844 });
    await page.evaluate(() => new Promise(resolve => requestAnimationFrame(() => requestAnimationFrame(resolve))));
    const mobile = await page.locator('.slide[data-active]').boundingBox();
    if (!mobile || mobile.width > 391 || mobile.x < -1) issues.push({ reason: '小屏缩放溢出', mobile });
    await page.setViewportSize({ width: 1200, height: 760 });
    await page.evaluate(() => new Promise(resolve => requestAnimationFrame(() => requestAnimationFrame(resolve))));
    if (pdf) {
      await page.emulateMedia({ media: 'print' });
      await page.pdf({ path: resolve(outDir, 'slides.pdf'), printBackground: true, preferCSSPageSize: true, displayHeaderFooter: false });
    }
    const report = { ok: !issues.length && !errors.length && !requests.length, slides: state.count, issues, errors, networkRequests: requests, fonts: state.fonts, screenshots: outDir, pdf: pdf ? resolve(outDir, 'slides.pdf') : undefined };
    await writeFile(resolve(outDir, 'report.json'), JSON.stringify(report, null, 2));
    return report;
  } finally { await instance.close(); }
}

if (import.meta.main) {
  try {
    const { values } = parseArgs({ options: { input: { type: 'string' }, out: { type: 'string' }, pdf: { type: 'boolean' }, browser: { type: 'string' }, channel: { type: 'string' }, help: { type: 'boolean' } } });
    if (values.help) console.log('bun scripts/check.mjs --input slides.html --out qa [--pdf] [--channel chrome | --browser /path/to/browser]');
    else {
      if (!values.input || !values.out) throw new Error('需要 --input 和 --out');
      const result = await check(values); console.log(JSON.stringify(result, null, 2)); if (!result.ok) process.exitCode = 1;
    }
  } catch (e) { console.error(e.message); process.exitCode = 1; }
}
