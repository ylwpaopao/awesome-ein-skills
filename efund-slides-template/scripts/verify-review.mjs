import { readFile } from 'node:fs/promises';
import { resolve, dirname } from 'node:path';
import { createHash } from 'node:crypto';
import { parseArgs } from 'node:util';

const hash = async path => createHash('sha256').update(await readFile(path)).digest('hex');
const checks = ['hierarchy', 'layout', 'readability', 'evidence', 'privacy'];

// Validates evidence completeness/freshness; it cannot prove an image was inspected.
export async function verifyReview({input, qa, review}) {
  const issues = [];
  try {
    const report = JSON.parse(await readFile(resolve(qa, 'report.json'), 'utf8'));
    const record = JSON.parse(await readFile(review, 'utf8'));
    const sha = await hash(input);
    if (!report.ok) issues.push('browser-qa-not-passed');
    if (sha !== report.inputSha256 || sha !== record.inputSha256) issues.push('review-stale-html');
    if (!['human', 'image-capable-model'].includes(record.method) || !record.reviewer?.trim()) issues.push('reviewer-missing');
    if (!Array.isArray(record.slides) || record.slides.length !== report.slides || record.slides.some((s,i) => s.slide !== i + 1)) issues.push('review-pages-incomplete');
    for (const s of record.slides ?? []) {
      const reference = report.screenshotFiles.find(image => image.slide === s.slide);
      if (!reference || s.imageSha256 !== reference.sha256 || await hash(resolve(dirname(review), s.image)) !== s.imageSha256) issues.push(`slide-${s.slide}:review-stale-image`);
      if (s.verdict !== 'pass' || checks.some(k => s.checks?.[k] !== true)) issues.push(`slide-${s.slide}:review-not-passed`);
      if (!s.observation?.trim()) issues.push(`slide-${s.slide}:observation-missing`);
      if (!Array.isArray(s.findings) || !Array.isArray(s.changes)) issues.push(`slide-${s.slide}:findings-or-changes-missing`);
    }
  } catch (e) { issues.push(`review-invalid: ${e.message}`); }
  return {ok: !issues.length, issues};
}

if (import.meta.main) {
  try {
    const {values} = parseArgs({options: {input: {type: 'string'}, qa: {type: 'string'}, review: {type: 'string'}, help: {type: 'boolean'}}});
    if (values.help) console.log('bun scripts/verify-review.mjs --input slides.html --qa qa --review qa/visual-review.json');
    else {
      if (!values.input || !values.qa || !values.review) throw new Error('需要 --input、--qa 和 --review');
      const result = await verifyReview(values); console.log(JSON.stringify(result, null, 2)); if (!result.ok) process.exitCode = 1;
    }
  } catch (e) { console.error(e.message); process.exitCode = 1; }
}
