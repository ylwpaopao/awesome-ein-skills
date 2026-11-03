import { chromium } from 'playwright';
import { mkdir, writeFile, readFile } from 'node:fs/promises';
import { createHash } from 'node:crypto';
import { resolve } from 'node:path';
import { pathToFileURL } from 'node:url';
import { parseArgs } from 'node:util';
import { reviewContent } from './content-review.mjs';
import { PDFDocument } from 'pdf-lib';

const digest = bytes => createHash('sha256').update(bytes).digest('hex');

// The same checks are used for authoring QA and optional PDF export.
export async function check({ input, out, pdf = false, browser: executablePath, channel = 'chrome', scale }) {
  if (!input || !out) throw new Error('需要 input 和 out');
  scale = Number(scale ?? (pdf ? 2 : 1));
  if (!Number.isFinite(scale) || scale < 1 || scale > 4) throw new Error('scale 必须在 1–4 之间');
  const htmlPath = resolve(input), outDir = resolve(out);
  const inputSha256 = digest(await readFile(htmlPath));
  await mkdir(outDir, { recursive: true });
  const instance = await chromium.launch({ headless: true, ...(executablePath ? { executablePath } : { channel }) });
  const issues = [], errors = [], requests = [], screenshots = [];
  try {
    const page = await instance.newPage({ viewport: { width: 1200, height: 760 }, deviceScaleFactor: scale });
    // A self-contained deck must not need a network, even during inspection.
    await page.route(/^https?:\/\//, route => route.abort());
    page.on('pageerror', e => errors.push(e.message));
    page.on('console', message => { if (message.type() === 'error') errors.push(message.text()); });
    page.on('request', req => { if (/^https?:/.test(req.url())) requests.push(req.url()); });
    await page.goto(pathToFileURL(htmlPath).href, { waitUntil: 'load' });
    await page.evaluate(async () => {
      if (!window.efund) throw new Error('缺少 efund 播放器');
      if (typeof window.efund.measureReadability !== 'function') throw new Error('HTML 播放器缺少真实换行检查接口；请使用当前 Skill 重新构建 HTML');
      await window.efund.ready;
    });
    const state = await page.evaluate(() => ({
      count: document.querySelectorAll('.slide').length,
      fonts: [...document.fonts].map(f => ({ family: f.family, weight: f.weight, status: f.status })),
      images: [...document.images].filter(i => !i.complete || !i.naturalWidth).map(i => i.alt || 'background'),
      overflow: window.efund.checkOverflow(),
      canvas: { width: parseFloat(getComputedStyle(document.documentElement).getPropertyValue('--slide-width')), height: parseFloat(getComputedStyle(document.documentElement).getPropertyValue('--slide-height')) },
      readability: window.efund.measureReadability(),
      content: [...document.querySelectorAll('.slide')].map((s, i) => {
        const copy = s.cloneNode(true);
        copy.querySelectorAll('[hidden],.visually-hidden,.page-number,.brand-background').forEach(el => el.remove());
        return {slide: i + 1, layout: s.dataset.layout, text: copy.textContent, visualTypes: [...s.querySelectorAll('[data-semantic-visual]')].map(el => el.dataset.semanticVisual), visualTextBinding: s.dataset.visualTextBinding ? JSON.parse(s.dataset.visualTextBinding) : null, visualExemption: s.dataset.visualExemption, hasSource: !!s.querySelector('.source'), hasNotes: !!s.querySelector('.speaker-notes')};
      }),
    }));
    issues.push(...state.overflow);
    issues.push(...state.readability.issues);
    if (!state.count || !Number.isFinite(state.canvas.width) || !Number.isFinite(state.canvas.height) || state.canvas.width <= 0 || state.canvas.height <= 0) throw new Error('页面数量或画布尺寸无效');
    const warnings = reviewContent(state.content);
    const invalidGeometry = await page.evaluate(() => [...document.querySelectorAll('.data-chart *')].flatMap(el => [...el.attributes].filter(a => /(?:NaN|Infinity)/.test(a.value) && ['x', 'y', 'x1', 'x2', 'y1', 'y2', 'cx', 'cy', 'r', 'width', 'height', 'points', 'd'].includes(a.name)).map(a => `${el.tagName}.${a.name}=${a.value}`)));
    if (invalidGeometry.length) issues.push({ reason: '图表几何数值无效', attributes: invalidGeometry });
    if (!state.fonts.some(f => f.family.replace(/['"]/g, '') === 'EFund' && f.status === 'loaded')) issues.push({ reason: '品牌字体未加载' });
    for (const weight of ['400', '700']) if (!state.fonts.some(f => f.family.replace(/['"]/g, '') === 'EFundLatin' && f.weight === weight && f.status === 'loaded')) issues.push({ reason: `内嵌拉丁字体 ${weight} 未加载` });
    if (state.images.length) issues.push({ reason: '图片加载失败', images: state.images });
    await page.setViewportSize({ width: Math.ceil(state.canvas.width + 24), height: Math.ceil(state.canvas.height + 82) });
    await page.evaluate(() => new Promise(resolve => requestAnimationFrame(() => requestAnimationFrame(resolve))));
    await page.evaluate(() => document.documentElement.style.setProperty('--scale', '1'));
    for (let i = 0; i < state.count; i++) {
      await page.evaluate(n => window.efund.goTo(n), i);
      await page.evaluate(() => new Promise(resolve => requestAnimationFrame(() => requestAnimationFrame(resolve))));
      const file = `slide-${String(i + 1).padStart(2, '0')}.png`;
      const bytes = await page.locator('.slide[data-active]').screenshot({ path: resolve(outDir, file) });
      screenshots.push({ slide: i + 1, file, sha256: digest(bytes) });
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
    let pdfPath;
    if (pdf && !issues.length && !errors.length && !requests.length) {
      pdfPath = resolve(outDir, 'slides.pdf');
      // Chromium's synthetic EFund bold produces broken Type3 outlines in print PDFs.
      // Package the same checked pixels as PPTX; retain the exact CSS canvas in points.
      const document = await PDFDocument.create();
      document.setCreator('efund-slides-template');
      for (const screenshot of screenshots) {
        const picture = await document.embedPng(await readFile(resolve(outDir, screenshot.file)));
        const width = state.canvas.width * .75, height = state.canvas.height * .75;
        document.addPage([width, height]).drawImage(picture, {x: 0, y: 0, width, height});
      }
      await writeFile(pdfPath, await document.save());
    }
    if (digest(await readFile(htmlPath)) !== inputSha256) issues.push({reason: '检查过程中 HTML 被修改，请重新运行'});
    const report = { ok: !issues.length && !errors.length && !requests.length, input: htmlPath, inputSha256, slides: state.count, canvas: state.canvas, scale, issues, warnings, errors, networkRequests: requests, fonts: state.fonts, screenshots: outDir, screenshotFiles: screenshots, pdf: pdfPath, ...(pdfPath ? {pdfMode: 'page-images', searchableText: false} : {}), visualReview: 'required' };
    await writeFile(resolve(outDir, 'text-layout.json'), JSON.stringify(state.readability.textLayout, null, 2));
    // This is deliberately an unfinished worksheet. Never manufacture visual approval.
    const review = {inputSha256, method: '', reviewer: '', slides: screenshots.map(s => ({slide: s.slide, image: s.file, imageSha256: s.sha256, verdict: 'pending', observation: '', checks: {hierarchy: null, layout: null, readability: null, evidence: null, privacy: null}, findings: [], changes: []}))};
    await writeFile(resolve(outDir, 'visual-review.template.json'), JSON.stringify(review, null, 2));
    await writeFile(resolve(outDir, 'report.json'), JSON.stringify(report, null, 2));
    return report;
  } finally { await instance.close(); }
}

if (import.meta.main) {
  try {
    const { values } = parseArgs({ options: { input: { type: 'string' }, out: { type: 'string' }, pdf: { type: 'boolean' }, scale: { type: 'string' }, browser: { type: 'string' }, channel: { type: 'string' }, help: { type: 'boolean' } } });
    if (values.help) console.log('bun scripts/check.mjs --input slides.html --out qa [--pdf] [--scale 1..4] [--channel chrome | --browser /path/to/browser]');
    else {
      if (!values.input || !values.out) throw new Error('需要 --input 和 --out');
      const result = await check(values); console.log(JSON.stringify(result, null, 2)); if (!result.ok) process.exitCode = 1;
    }
  } catch (e) { console.error(e.message); process.exitCode = 1; }
}
