import { readFile, writeFile, mkdir, mkdtemp, lstat, rename, link, unlink, rm } from 'node:fs/promises';
import { basename, dirname, extname, join, posix, resolve } from 'node:path';
import { createHash } from 'node:crypto';
import { parseArgs } from 'node:util';
import PptxGenJS from 'pptxgenjs';
import JSZip from 'jszip';
import { PDFDocument, PDFName, PDFDict, PDFRawStream } from 'pdf-lib';
import { check } from './check.mjs';

const hash = bytes => createHash('sha256').update(bytes).digest('hex');
const slideFile = (dir, i) => join(dir, `slide-${String(i + 1).padStart(2, '0')}.png`);
const ensure = (condition, message) => { if (!condition) throw new Error(message); };

function pngSize(bytes) {
  ensure(bytes.length > 24 && bytes.subarray(0, 8).equals(Buffer.from([137, 80, 78, 71, 13, 10, 26, 10])), '截图不是有效 PNG');
  return { width: bytes.readUInt32BE(16), height: bytes.readUInt32BE(20) };
}

// Read only XML produced by PptxGenJS here; this is not a general OOXML importer.
const attributes = tag => Object.fromEntries([...tag.matchAll(/([\w:]+)="([^"]*)"/g)].map(m => [m[1], m[2]]));
async function zipText(zip, name) {
  ensure(zip.file(name), `PPTX 缺少 ${name}`);
  return zip.file(name).async('string');
}

export async function verifyPptx(bytes, { slides, canvas, screenshots }) {
  const zip = await JSZip.loadAsync(bytes, { checkCRC32: true });
  const presentation = await zipText(zip, 'ppt/presentation.xml');
  const size = attributes(presentation.match(/<p:sldSz\b[^>]*>/)?.[0] ?? '');
  const expected = { cx: Math.round(canvas.width * 9525), cy: Math.round(canvas.height * 9525) };
  ensure(Number(size.cx) === expected.cx && Number(size.cy) === expected.cy, 'PPTX 页面尺寸与 HTML 不一致');
  const parts = Object.keys(zip.files).filter(name => /^ppt\/slides\/slide\d+\.xml$/.test(name));
  ensure(parts.length === slides && (presentation.match(/<p:sldId\s/g) ?? []).length === slides, 'PPTX 页数与 HTML 不一致');
  const imageSizes = [];
  for (let i = 0; i < slides; i++) {
    const xml = await zipText(zip, `ppt/slides/slide${i + 1}.xml`);
    const pictures = [...xml.matchAll(/<p:pic>.*?<\/p:pic>/gs)];
    ensure(pictures.length === 1 && !/<p:sp>/.test(xml), `PPTX 第 ${i + 1} 页应只有一张完整页面截图`);
    const picture = pictures[0][0];
    const offset = attributes(picture.match(/<a:off\b[^>]*>/)?.[0] ?? '');
    const extent = attributes(picture.match(/<a:ext\b[^>]*>/)?.[0] ?? '');
    ensure(offset.x === '0' && offset.y === '0' && Number(extent.cx) === expected.cx && Number(extent.cy) === expected.cy, `PPTX 第 ${i + 1} 页截图未铺满画布`);
    const imageId = attributes(picture.match(/<a:blip\b[^>]*>/)?.[0] ?? '')['r:embed'];
    const rels = await zipText(zip, `ppt/slides/_rels/slide${i + 1}.xml.rels`);
    const relation = [...rels.matchAll(/<Relationship\b[^>]*>/g)].map(m => attributes(m[0])).find(r => r.Id === imageId);
    ensure(relation && relation.Type.endsWith('/image') && relation.TargetMode !== 'External', `PPTX 第 ${i + 1} 页没有内嵌截图`);
    const target = posix.normalize(posix.join('ppt/slides', relation.Target));
    ensure(target.startsWith('ppt/media/') && zip.file(target), `PPTX 第 ${i + 1} 页截图关系无效`);
    const embedded = await zip.file(target).async('nodebuffer');
    ensure(embedded.equals(screenshots[i]), `PPTX 第 ${i + 1} 页截图与已检查 HTML 不一致`);
    imageSizes.push(pngSize(embedded));
  }
  return { slides, canvasEmu: expected, images: imageSizes, embeddedImagesMatch: true };
}

export async function verifyPdf(bytes, { slides, canvas, scale = 2 }) {
  const pdf = await PDFDocument.load(bytes);
  ensure(pdf.getPageCount() === slides, 'PDF 页数与 HTML 不一致');
  const dimensions = pdf.getPages().map(page => page.getSize());
  ensure(dimensions.every(size => Math.abs(size.width - canvas.width * .75) < .001 && Math.abs(size.height - canvas.height * .75) < .001), 'PDF 页面尺寸与 HTML 不一致');
  const images = pdf.getPages().map((page, i) => {
    const objects = page.node.Resources()?.lookupMaybe(PDFName.of('XObject'), PDFDict);
    const embedded = (objects?.entries() ?? []).map(([, ref]) => pdf.context.lookup(ref)).filter(object => object instanceof PDFRawStream && object.dict.get(PDFName.of('Subtype')) === PDFName.of('Image'));
    ensure(embedded.length === 1, `PDF 第 ${i + 1} 页没有完整的单页截图`);
    const size = { width: Number(embedded[0].dict.get(PDFName.of('Width'))), height: Number(embedded[0].dict.get(PDFName.of('Height'))) };
    ensure(Math.abs(size.width - canvas.width * scale) <= 2 && Math.abs(size.height - canvas.height * scale) <= 2, `PDF 第 ${i + 1} 页截图尺寸异常`);
    return size;
  });
  return { slides, pagesPoints: dimensions, images, embeddedPageImages: true };
}

async function writeArtifact(output, bytes, force) {
  const staging = await mkdtemp(join(dirname(output), '.efund-export-'));
  const pending = join(staging, basename(output));
  try {
    await writeFile(pending, bytes, { flag: 'wx' });
    if (force) await rename(pending, output);
    else {
      // A hard link atomically refuses a file created after the initial existence check.
      await link(pending, output);
      await unlink(pending);
    }
  } finally { await rm(staging, { recursive: true, force: true }); }
}

export async function exportSlides({ input, output, qaDir, browser, channel = 'chrome', scale = 2, force = false }) {
  ensure(input && output, '需要 --input 和 --output');
  const htmlPath = resolve(input), dest = resolve(output);
  const format = extname(dest).slice(1).toLowerCase();
  ensure(['pdf', 'pptx'].includes(format), '输出扩展名只支持 .pdf / .pptx（PowerPoint 使用 .pptx）');
  ensure(['.html', '.htm'].includes(extname(htmlPath).toLowerCase()), '输入必须是完成的 HTML 幻灯片');
  ensure(htmlPath !== dest, '输出不能覆盖输入 HTML');
  ensure(Number.isFinite(scale) && scale >= 1 && scale <= 4, '--scale 需要 1–4 之间的数字');
  const existing = await lstat(dest).catch(e => { if (e.code === 'ENOENT') return null; throw e; });
  ensure(!existing || (force && existing.isFile()), existing?.isFile() ? '输出已存在；确认更新时加 --force' : '输出已存在且不是普通文件');
  const htmlBytes = await readFile(htmlPath);
  const sourceSha256 = hash(htmlBytes);
  const qaRoot = resolve(qaDir ?? join(dirname(dest), `${basename(dest, extname(dest))}-qa`));
  await mkdir(qaRoot, { recursive: true });
  const qa = await mkdtemp(join(qaRoot, 'export-'));
  const report = await check({ input: htmlPath, out: qa, pdf: format === 'pdf', browser, channel, scale });
  ensure(report.ok, `HTML 检查失败，未生成交付文件。详见 ${join(qa, 'report.json')}`);
  ensure(hash(await readFile(htmlPath)) === sourceSha256, '检查过程中 HTML 发生变化；请重新导出');
  ensure(Number.isInteger(report.slides) && report.slides > 0, 'HTML 没有可导出的幻灯片');
  const canvas = report.canvas;
  ensure(canvas && Number.isFinite(canvas.width) && canvas.width > 0 && Number.isFinite(canvas.height) && canvas.height > 0, 'HTML 页面尺寸无效');
  let bytes, validation;
  if (format === 'pdf') {
    bytes = await readFile(join(qa, 'slides.pdf'));
    validation = await verifyPdf(bytes, report);
  } else {
    const pptx = new PptxGenJS();
    const width = canvas.width / 96, height = canvas.height / 96;
    pptx.defineLayout({ name: 'EFUND_HTML', width, height });
    pptx.layout = 'EFUND_HTML';
    pptx.author = 'efund-slides-template';
    pptx.company = '';
    pptx.subject = 'HTML slides rendered as full-page images';
    pptx.title = '易方达演示';
    pptx.lang = 'zh-CN';
    const screenshots = [];
    for (let i = 0; i < report.slides; i++) {
      const png = await readFile(slideFile(qa, i));
      const size = pngSize(png);
      ensure(Math.abs(size.width - canvas.width * scale) <= 2 && Math.abs(size.height - canvas.height * scale) <= 2, `第 ${i + 1} 页截图尺寸异常`);
      screenshots.push(png);
      pptx.addSlide().addImage({ data: `image/png;base64,${png.toString('base64')}`, x: 0, y: 0, w: width, h: height, altText: `第 ${i + 1} 页，来自 HTML 的完整画面` });
    }
    bytes = Buffer.from(await pptx.write({ outputType: 'nodebuffer', compression: true }));
    validation = await verifyPptx(bytes, { ...report, screenshots });
  }
  await mkdir(dirname(dest), { recursive: true });
  await writeArtifact(dest, bytes, force);
  const result = { ok: true, format, output: dest, slides: report.slides, canvas, sourceSha256, outputSha256: hash(bytes), qaReport: join(qa, 'report.json'), validation, ...(format === 'pptx' ? { editableElements: false, note: '每页为 HTML 高清截图；修改内容请编辑源 deck.json 并重新构建和导出。' } : { searchableText: false, note: '每页为 HTML 高清截图，保留视觉外观；PDF 文字不可搜索或选中，修改内容请回到源 JSON/HTML。' }) };
  await writeFile(join(qa, 'export.json'), JSON.stringify(result, null, 2));
  return result;
}

if (import.meta.main) {
  try {
    const { values } = parseArgs({ options: { input: { type: 'string' }, output: { type: 'string' }, 'qa-dir': { type: 'string' }, browser: { type: 'string' }, channel: { type: 'string' }, scale: { type: 'string' }, force: { type: 'boolean' }, help: { type: 'boolean' } } });
    if (values.help) console.log('bun scripts/export.mjs --input slides.html --output slides.pptx|slides.pdf [--qa-dir qa] [--scale 2] [--channel chrome | --browser /path/to/browser] [--force]\n始终先检查 HTML。PPTX/PDF 每页为完整高清截图；PPTX 正文不可逐元素编辑，PDF 文字不可搜索或选中。HTML 保留可编辑内容。');
    else console.log(JSON.stringify(await exportSlides({ ...values, qaDir: values['qa-dir'], scale: values.scale === undefined ? 2 : Number(values.scale) }), null, 2));
  } catch (e) { console.error(e.message); process.exitCode = 1; }
}
