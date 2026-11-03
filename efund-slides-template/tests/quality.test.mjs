import {test, expect} from 'bun:test';
import {mkdtemp, writeFile, readFile, rm} from 'node:fs/promises';
import {join} from 'node:path';
import {tmpdir} from 'node:os';
import {reviewContent} from '../scripts/content-review.mjs';
import {verifyReview} from '../scripts/verify-review.mjs';
import {build} from '../scripts/build.mjs';
import {check} from '../scripts/check.mjs';

test('writing and evidence prompts distinguish genuine missing context from explicit exemptions', () => {
  const warnings = reviewContent([
    {slide: 1, layout: 'text', text: '打造业务新引擎', visualTypes: []},
    {slide: 2, layout: 'text', text: '完整引用法规', visualTypes: [], visualExemption: '用户要求保留逐字原文'},
    {slide: 3, layout: 'chart', text: '处理量增长', visualTypes: ['chart'], hasSource: true, visualTextBinding: {supportsClaim: '处理量增长', textAnchor: '处理量增长', informationCarried: '季度处理量对比'}},
  ]);
  expect(warnings.map(w => w.code)).toContain('slogan-engine');
  expect(warnings.map(w => w.code)).toContain('semantic-visual-missing');
  expect(warnings.some(w => w.slide === 2 || w.slide === 3)).toBe(false);
});

test('browser reads actual wrapped lines, catches spacing, and never pre-approves visual review', async () => {
  const dir = await mkdtemp(join(tmpdir(), 'efund-quality-'));
  try {
    const input = join(dir, 'deck.json'), html = join(dir, 'slides.html'), qa = join(dir, 'qa');
    await writeFile(input, JSON.stringify({title: '检查样例', slides: [
      {layout: 'text', title: '真实换行检查', paragraphs: ['完整句子\n字'], visualExemption: '检查夹具'},
      {layout: 'chart', title: '实际间距检查', lead: '图表解释', chart: {type: 'bar', title: '完成量', labels: ['甲项','乙项'], series: [{name:'数量',values:[2,3]}]}},
    ]}));
    await build({input, output: html});
    const bytes = await readFile(html, 'utf8');
    await writeFile(html, bytes.replace('</head>', '<style>.lead{line-height:1;margin-bottom:-4px}</style></head>'));
    const report = await check({input: html, out: qa, pdf: true});
    expect(report.ok).toBe(false);
    expect(report.issues.some(x => x.type === 'single-han-line')).toBe(true);
    expect(report.issues.some(x => x.type === 'text-graphic-spacing')).toBe(true);
    expect(report.pdf).toBeUndefined();
    const lines = JSON.parse(await readFile(join(qa, 'text-layout.json'), 'utf8'));
    expect(lines.some(x => x.source === 'rendered' && x.lines.join('|') === '完整句子|字')).toBe(true);
    const template = JSON.parse(await readFile(join(qa, 'visual-review.template.json'), 'utf8'));
    expect(template.slides.every(s => s.verdict === 'pending' && s.checks.readability === null)).toBe(true);
    const review = join(qa, 'visual-review.json');
    await writeFile(review, JSON.stringify(template));
    const result = await verifyReview({input: html, qa, review});
    expect(result.ok).toBe(false);
    expect(result.issues).toContain('reviewer-missing');
    await writeFile(html, bytes + '\n');
    const stale = await verifyReview({input: html, qa, review});
    expect(stale.issues).toContain('review-stale-html');
    const legacy = join(dir, 'legacy.html');
    await writeFile(legacy, bytes.replace('</body>', '<script>delete window.efund.measureReadability</script></body>'));
    await expect(check({input: legacy, out: join(dir, 'legacy-qa')})).rejects.toThrow('重新构建 HTML');
  } finally {await rm(dir, {recursive:true, force:true});}
}, 60000);
