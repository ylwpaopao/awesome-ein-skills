import { test, expect } from 'bun:test';
import { mkdtemp, readFile, writeFile, rm, cp, mkdir } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import { join, resolve } from 'node:path';
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
test('rejects misleading table highlights, impossible widths, and unrelated flow options', () => {
  const table = { columns: ['方案', '时长'], rows: [['甲', 2], ['乙', 3], ['丙', 4]] };
  for (const extra of [{ highlightRows: [0, 1, 2] }, { numericColumns: [2] }, { subtotalRows: [1, 1] }, { columnWidths: [30, 60] }]) {
    expect(() => validateDeck(deck([{ layout: 'table', title: '比较', table: { ...table, ...extra } }]))).toThrow();
  }
  expect(() => validateDeck(deck([{ layout: 'table', title: '清单', table: { ...table, mode: 'task-list' } }]))).toThrow('三列');
  const diagram = { type: 'matrix', title: '职责', items: [{ label: '审阅' }, { label: '复核' }] };
  expect(() => validateDeck(deck([{ layout: 'diagram', title: '职责', diagram: { ...diagram, direction: 'horizontal' } }]))).toThrow('仅 flow');
  expect(() => validateDeck(deck([{ layout: 'diagram', title: '职责', diagram: { ...diagram, focus: 2 } }]))).toThrow('零基索引');
});
test('evidence layouts retain semantic tables, ordered relationships, and escaped review metadata', () => {
  const binding = { supportsClaim: '<数据支持判断>', textAnchor: '左侧说明', informationCarried: '方案时长差异' };
  const input = deck([
    { layout: 'two-column', title: '方案比较', left: { paragraphs: ['甲方案耗时更少。'] }, right: { table: { columns: ['方案', '时长'], rows: [['甲', 2], ['乙', 3]], mode: 'row-highlight', highlightRows: [0], columnWidths: [60, 40] } }, visualTextBinding: binding },
    { layout: 'diagram', title: '审阅顺序', diagram: { type: 'flow', title: '材料经两步审阅后交付', items: [{ label: '审阅' }, { label: '复核' }] } },
    { layout: 'diagram', title: '职责分工', diagram: { type: 'matrix', title: '两项独立职责', items: [{ label: '材料核实' }, { label: '视觉复核' }] } },
  ]);
  validateDeck(input);
  const html = renderDeck(input, { backgrounds: { content: '' }, font: 'data:font/woff2;base64,', latinFonts: { regular: '', bold: '' }, width: 960, height: 540.5, css: '', player: '' });
  expect(html).toContain('data-visual-text-binding="{&quot;supportsClaim&quot;:&quot;&lt;数据支持判断&gt;');
  expect(html).toContain('<th scope="row" data-readability>甲</th><td class="numeric-column"');
  expect(html).toContain('<caption class="visually-hidden">方案比较</caption>');
  expect(html).toContain('<ol class="diagram diagram-flow');
  expect(html).toContain('<ul class="diagram diagram-matrix');
  expect((html.match(/<svg class="diagram-connector"/g) ?? []).length).toBe(1);
  expect(() => validateDeck(deck([{ ...input.slides[0], visualTextBinding: { supportsClaim: '缺少锚点与信息' } }]))).toThrow('textAnchor');
});
test('rejects unrenderable magnitudes and footer text on brand-only layouts', () => {
  for (const values of [[1e308, -1e308], [1e-320, 2e-320]]) expect(() => validateDeck(deck([{ layout: 'chart', title: '结论', chart: { ...chart, series: [{ name: '组', values }] } }]))).toThrow('转换单位');
  expect(() => validateDeck(deck([{ layout: 'cover', title: '标题', source: '不应压在品牌声明上' }]))).toThrow('没有来源区域');
});
test('small nonzero chart values remain nonzero in visible SVG labels', () => {
  const values = [0.000001, 0.000002];
  const html = renderDeck(deck([{ layout: 'chart', title: '小数', chart: { ...chart, series: [{ name: '组', values }] } }]), { backgrounds: { content: '' }, font: 'data:font/woff2;base64,', latinFonts: {regular: '', bold: ''}, width: 960, height: 540.5, css: '', player: '' });
  const labels = [...html.matchAll(/class="chart-value">([^<]+)<\/text>/g)].map(m => Number(m[1]));
  expect(labels).toEqual(values);
  expect(html).not.toMatch(/(?:NaN|Infinity)/);
});
test('a copied skill builds identical HTML without home, environment fonts or Python', async () => {
  const dir = await mkdtemp(join(tmpdir(), 'efund-portable-'));
  const root = resolve(import.meta.dir, '..');
  try {
    for (const name of ['assets', 'templates', 'examples']) await cp(join(root, name), join(dir, name), { recursive: true });
    await mkdir(join(dir, 'scripts'));
    for (const name of ['build.mjs', 'render.mjs']) await cp(join(root, 'scripts', name), join(dir, 'scripts', name));
    const local = join(dir, 'local.html'), portable = join(dir, 'portable.html');
    await build({ input: join(root, 'examples/demo.json'), output: local });
    const child = Bun.spawnSync({ cmd: [process.execPath, join(dir, 'scripts/build.mjs'), '--input', join(dir, 'examples/demo.json'), '--output', portable], env: {}, cwd: dir });
    expect(child.exitCode, child.stderr.toString()).toBe(0);
    expect(await readFile(portable, 'utf8')).toBe(await readFile(local, 'utf8'));
  } finally { await rm(dir, { recursive: true, force: true }); }
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
