import { afterAll, beforeAll, test, expect } from 'bun:test';
import { mkdtemp, readFile, writeFile, rm, readdir, access } from 'node:fs/promises';
import { join } from 'node:path';
import { tmpdir } from 'node:os';
import { createHash } from 'node:crypto';
import JSZip from 'jszip';
import { PDFDocument } from 'pdf-lib';
import { build } from '../scripts/build.mjs';
import { exportSlides } from '../scripts/export.mjs';

let dir, html, source;
beforeAll(async () => {
  dir = await mkdtemp(join(tmpdir(), 'efund-export-test-'));
  const input = join(dir, 'deck.json');
  html = join(dir, 'slides.html');
  await writeFile(input, JSON.stringify({ title: '导出验证', slides: [
    { layout: 'cover', title: 'HTML 先行', subtitle: '中文、English 与数字 123', date: '2026 年 11 月' },
    { layout: 'chart', title: '零值与负值保持原样', source: '来源：导出测试数据，非业务事实', chart: { type: 'bar', title: '示例数据', labels: ['甲', '乙', '丙'], series: [{ name: '示例', values: [0, -2, 5] }] } },
  ] }));
  await build({ input, output: html });
  source = await readFile(html);
});
afterAll(async () => { if (dir) await rm(dir, { recursive: true, force: true }); });

test('export rejects unsupported formats, invalid scale and existing output without modifying input or output', async () => {
  await expect(exportSlides({ input: html, output: join(dir, 'slides.ppt') })).rejects.toThrow('.pptx');
  await expect(exportSlides({ input: html, output: join(dir, 'slides.pptx'), scale: 0 })).rejects.toThrow('1–4');
  const target = join(dir, 'existing.pdf');
  await writeFile(target, 'existing file');
  await expect(exportSlides({ input: html, output: target })).rejects.toThrow('--force');
  expect(await readFile(target, 'utf8')).toBe('existing file');
  expect((await readFile(html)).equals(source)).toBe(true);
});

test('PPTX contains every checked HTML page as an identical full-canvas embedded high-resolution PNG', async () => {
  const output = join(dir, 'slides.pptx');
  const result = await exportSlides({ input: html, output, qaDir: join(dir, 'qa-pptx') });
  expect(result.slides).toBe(2);
  expect(result.editableElements).toBe(false);
  expect(result.sourceSha256).toBe(createHash('sha256').update(source).digest('hex'));
  expect(result.validation.embeddedImagesMatch).toBe(true);
  expect(result.validation.canvasEmu).toEqual({ cx: 9144000, cy: 5148263 });
  expect(result.validation.images.every(size => size.width >= 1920 && size.height >= 1081)).toBe(true);
  const zip = await JSZip.loadAsync(await readFile(output), { checkCRC32: true });
  expect(Object.keys(zip.files).filter(name => /^ppt\/slides\/slide\d+\.xml$/.test(name))).toHaveLength(2);
  expect(Object.keys(zip.files).filter(name => /^ppt\/media\/.*\.png$/.test(name))).toHaveLength(2);
  expect((await readFile(html)).equals(source)).toBe(true);
  const qa = JSON.parse(await readFile(result.qaReport, 'utf8'));
  expect(qa.ok).toBe(true);
  expect(qa.fonts.filter(font => font.status === 'loaded')).toHaveLength(3);
}, 60000);

test('PDF is printed from the same HTML with matching page count and paper dimensions', async () => {
  const output = join(dir, 'slides.pdf');
  const result = await exportSlides({ input: html, output, qaDir: join(dir, 'qa-pdf') });
  const pdf = await PDFDocument.load(await readFile(output));
  expect(pdf.getPageCount()).toBe(2);
  expect(result.sourceSha256).toBe(createHash('sha256').update(source).digest('hex'));
  expect(pdf.getPages().every(page => Math.abs(page.getWidth() - 720) <= 1 && Math.abs(page.getHeight() - 405.375) <= 1)).toBe(true);
  expect((await readFile(html)).equals(source)).toBe(true);
}, 60000);

test('HTML overflow blocks delivery and preserves an existing artifact even with force', async () => {
  const badJson = join(dir, 'overflow.json'), badHtml = join(dir, 'overflow.html');
  await writeFile(badJson, JSON.stringify({ title: '过长输入', slides: [{ layout: 'text', title: '内容不能覆盖页脚', paragraphs: Array(12).fill('每段均需保留行高与间距') }] }));
  await build({ input: badJson, output: badHtml });
  const output = join(dir, 'protected.pdf'), qaDir = join(dir, 'qa-overflow');
  await writeFile(output, 'keep this file');
  await expect(exportSlides({ input: badHtml, output, qaDir, force: true })).rejects.toThrow('HTML 检查失败');
  expect(await readFile(output, 'utf8')).toBe('keep this file');
  const [run] = await readdir(qaDir);
  expect(JSON.parse(await readFile(join(qaDir, run, 'report.json'), 'utf8')).ok).toBe(false);
  await expect(access(join(qaDir, run, 'slides.pdf'))).rejects.toThrow();
}, 60000);
