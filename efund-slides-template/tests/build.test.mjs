import { test, expect } from 'bun:test';
import { mkdtemp, readFile, writeFile, rm } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { validateDeck, embedPicture, build } from '../scripts/build.mjs';
import { renderDeck } from '../scripts/render.mjs';

const deck = slides => ({ title: '演示', slides });
const chart = { type: 'bar', title: '数据', labels: ['甲', '乙'], series: [{ name: '组', values: [0, -2] }] };

test('accepts real numeric chart data including zeros and negatives', () => {
  expect(validateDeck(deck([{ layout: 'chart', title: '结论', chart }])).slides).toHaveLength(1);
});
test('rejects missing chart values, misleading coercions, and unknown layouts', () => {
  for (const values of [[1], ['1', 2], [Infinity, 2], [null, 2]]) {
    expect(() => validateDeck(deck([{ layout: 'chart', title: '结论', chart: { ...chart, series: [{ name: '组', values }] } }]))).toThrow('有限数值');
  }
  expect(() => validateDeck(deck([{ layout: 'unknown', title: '结论' }]))).toThrow('layout');
});
test('rejects table width mismatches and ambiguous two-column content', () => {
  expect(() => validateDeck(deck([{ layout: 'table', title: '表', table: { columns: ['甲'], rows: [[1, 2]] } }]))).toThrow('单元格数');
  expect(() => validateDeck(deck([{ layout: 'two-column', title: '说明', left: { paragraphs: ['一'] }, right: { paragraphs: ['二'], chart } }]))).toThrow('必须选一个');
});
test('rejects unrenderable magnitudes and footer text on brand-only layouts', () => {
  for (const values of [[1e308, -1e308], [1e-320, 2e-320]]) expect(() => validateDeck(deck([{ layout: 'chart', title: '结论', chart: { ...chart, series: [{ name: '组', values }] } }]))).toThrow('转换单位');
  expect(() => validateDeck(deck([{ layout: 'cover', title: '标题', source: '不应压在品牌声明上' }]))).toThrow('没有来源区域');
});
test('small nonzero chart values remain nonzero in visible SVG labels', () => {
  const values = [0.000001, 0.000002];
  const html = renderDeck(deck([{ layout: 'chart', title: '小数', chart: { ...chart, series: [{ name: '组', values }] } }]), { backgrounds: { content: '' }, font: 'data:font/woff2;base64,', width: 960, height: 540.5, css: '', player: '' });
  const labels = [...html.matchAll(/class="chart-value">([^<]+)<\/text>/g)].map(m => Number(m[1]));
  expect(labels).toEqual(values);
  expect(html).not.toMatch(/(?:NaN|Infinity)/);
});
test('never fetches remote images or embeds active SVG content', async () => {
  for (const src of ['https://example.com/image.png', 'javascript:alert(1)', 'data:image/svg+xml,<svg onload="alert(1)"/>']) {
    await expect(embedPicture({ src, alt: '测试' }, '/tmp')).rejects.toThrow('本地');
  }
});
test('build produces portable escaped HTML and preserves existing output', async () => {
  const dir = await mkdtemp(join(tmpdir(), 'efund-test-'));
  try {
    const input = join(dir, 'deck.json'), output = join(dir, 'deck.html');
    await writeFile(input, JSON.stringify(deck([{ layout: 'text', title: '</title><script>globalThis.pwned=1</script>', paragraphs: ['<img src=x onerror=alert(1)>'] }])));
    const result = await build({ input, output });
    const html = await readFile(output, 'utf8');
    expect(result.slides).toBe(1);
    expect(html).toContain('&lt;script&gt;');
    expect(html).not.toContain('<script>globalThis.pwned');
    expect(html).toContain('data:image/svg+xml;base64,');
    expect(html).toMatch(/data:font\/(woff2|ttf);base64,/);
    await expect(build({ input, output })).rejects.toThrow();
    expect(await readFile(output, 'utf8')).toBe(html);
  } finally { await rm(dir, { recursive: true, force: true }); }
});
