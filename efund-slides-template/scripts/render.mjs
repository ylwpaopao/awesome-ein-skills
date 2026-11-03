/** HTML authoring layer. Brand backgrounds are converted from the source PPTX. */
const COLORS = ['#005096', '#1EB9E1', '#0078B4', '#969696', '#B3EBFF', '#3C3C3C'];
const escape = (value = '') => String(value).replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const lines = value => escape(value).replace(/\n/g, '<br>');
const paragraph = value => `<p>${lines(value)}</p>`;
const paragraphs = values => (values ?? []).map(paragraph).join('');
const fmt = n => {
  if (n === 0) return '0';
  if (Math.abs(n) < .001 || Math.abs(n) >= 1e7) return n.toExponential(2).replace(/\.0+(?=e)/, '').replace(/(\.\d*?)0+(?=e)/, '$1');
  return n.toLocaleString('en-US', {maximumSignificantDigits: 6});
};

function textWidth(text) {
  return [...String(text)].reduce((sum, char) => sum + (/[^\u0000-\u00ff]/.test(char) ? 1 : 0.55), 0);
}

function wrapLabel(value, capacity) {
  const result = [''];
  for (const char of String(value)) {
    if (textWidth(result.at(-1) + char) > capacity && result.at(-1)) result.push('');
    result[result.length - 1] += char;
  }
  return result;
}

function dataTable(chart) {
  return `<table class="visually-hidden"><caption>${escape(chart.title)}</caption><thead><tr><th scope="col">类别</th>${chart.series.map(s => `<th scope="col">${escape(s.name)}</th>`).join('')}</tr></thead><tbody>${chart.labels.map((label, i) => `<tr><th scope="row">${escape(label)}</th>${chart.series.map(s => `<td>${escape(s.values[i])}${escape(chart.unit ?? '')}</td>`).join('')}</tr>`).join('')}</tbody></table>`;
}

function chartFigure(chart, width = 884, height = 300) {
  const values = chart.series.flatMap(s => s.values);
  let min = Math.min(0, ...values), max = Math.max(0, ...values);
  if (max === min) max = 1;
  const roughStep = (max - min) / 4;
  const magnitude = 10 ** Math.floor(Math.log10(roughStep));
  const fraction = roughStep / magnitude;
  const tickStep = (fraction <= 1 ? 1 : fraction <= 2 ? 2 : fraction <= 2.5 ? 2.5 : fraction <= 5 ? 5 : 10) * magnitude;
  min = Math.floor(min / tickStep) * tickStep;
  max = Math.ceil(max / tickStep) * tickStep;
  // Reserve a separate category-label band below direct negative-value labels.
  const left = 56, right = width - 16, top = 18, bottom = height - 70;
  const plotWidth = right - left, plotHeight = bottom - top;
  const y = v => bottom - (v - min) / (max - min) * plotHeight;
  const step = plotWidth / chart.labels.length;
  const center = i => left + (i + .5) * step;
  const axis = [];
  const tickCount = Math.round((max - min) / tickStep);
  for (let i = 0; i <= tickCount; i++) {
    const rawValue = min + tickStep * i;
    const value = Math.abs(rawValue) < tickStep * 1e-8 ? 0 : rawValue;
    const yy = y(value);
    axis.push(`<line x1="${left}" y1="${yy}" x2="${right}" y2="${yy}" stroke="#E6E6E6" stroke-width=".7"/><text x="${left - 9}" y="${yy + 4}" text-anchor="end" class="chart-tick">${escape(fmt(value))}</text>`);
  }
  axis.push(`<line x1="${left}" y1="${y(0)}" x2="${right}" y2="${y(0)}" stroke="#969696" stroke-width=".8"/>`);
  const marks = [];
  chart.series.forEach((series, si) => {
    const color = COLORS[si % COLORS.length];
    if (chart.type === 'line') {
      marks.push(`<polyline points="${series.values.map((value, i) => `${center(i)},${y(value)}`).join(' ')}" fill="none" stroke="${color}" stroke-width="2.4"/>`);
      series.values.forEach((value, i) => {
        marks.push(`<circle cx="${center(i)}" cy="${y(value)}" r="3" fill="${color}"/>`);
      });
    } else {
      const groupWidth = step * .7, barWidth = groupWidth / chart.series.length;
      series.values.forEach((value, i) => {
        const x = center(i) - groupWidth / 2 + si * barWidth;
        marks.push(`<rect x="${x}" y="${Math.min(y(0), y(value))}" width="${Math.max(1, barWidth - 2)}" height="${Math.abs(y(value) - y(0))}" fill="${color}"/>`);
      });
    }
    // Single-series direct labels stay readable. Multi-series values are in the accessible table.
    if (chart.series.length === 1) series.values.forEach((value, i) => {
      marks.push(`<text x="${center(i)}" y="${y(value) + (value < 0 ? 15 : -8)}" text-anchor="middle" class="chart-value">${escape(fmt(value))}</text>`);
    });
  });
  const labels = chart.labels.map((label, i) => `<text x="${center(i)}" y="${bottom + 36}" text-anchor="middle" class="chart-label">${wrapLabel(label, Math.max(2, step / 11 - 1)).map((line, lineIndex) => `<tspan x="${center(i)}" dy="${lineIndex ? 14 : 0}">${escape(line)}</tspan>`).join('')}</text>`).join('');
  const legend = chart.series.map((s, i) => `<span><i style="background:${COLORS[i % COLORS.length]}" aria-hidden="true"></i>${escape(s.name)}</span>`).join('');
  return `<figure class="chart-figure" data-semantic-visual="chart" data-check-overflow><figcaption>${escape(chart.title)}${chart.unit ? `（${escape(chart.unit)}）` : ''}</figcaption><div class="chart-legend" data-check-overflow>${legend}</div><svg class="data-chart" viewBox="0 0 ${width} ${height}" role="img" aria-label="${escape(chart.title)}" xmlns="http://www.w3.org/2000/svg"><title>${escape(chart.title)}</title>${axis.join('')}${marks.join('')}${labels}</svg>${dataTable(chart)}</figure>`;
}

function imageFigure(image) {
  return `<figure class="image-figure" data-semantic-visual="image" data-check-overflow><img class="content-image fit-${image.fit ?? 'contain'}" src="${escape(image.src)}" alt="${escape(image.alt)}"></figure>`;
}

function tableFigure(table, fallbackTitle) {
  const numericColumns = table.numericColumns ?? table.columns.map((_, i) => table.rows.every(row => typeof row[i] === 'number') ? i : -1).filter(i => i >= 0);
  const mode = table.mode ?? 'striped';
  const columns = table.columnWidths ? `<colgroup>${table.columnWidths.map(width => `<col style="width:${width}%">`).join('')}</colgroup>` : '';
  return `<table class="data-table table-${mode}" data-table-mode="${mode}" data-semantic-visual="table" data-check-overflow><caption${table.title ? '' : ' class="visually-hidden"'}>${escape(table.title ?? fallbackTitle)}</caption>${columns}<thead><tr>${table.columns.map(c => `<th scope="col">${lines(c)}</th>`).join('')}</tr></thead><tbody>${table.rows.map((row, ri) => `<tr${table.highlightRows?.includes(ri) ? ' class="highlight-row"' : table.subtotalRows?.includes(ri) ? ' class="subtotal-row"' : ''}>${row.map((cell, ci) => {
    const tag = ci === (mode === 'task-list' ? 1 : 0) ? 'th' : 'td';
    return `<${tag}${tag === 'th' ? ' scope="row"' : ''}${numericColumns.includes(ci) ? ' class="numeric-column"' : ''} data-readability>${lines(cell)}</${tag}>`;
  }).join('')}</tr>`).join('')}</tbody></table>`;
}

function diagramFigure(diagram) {
  const flow = diagram.type === 'flow';
  const direction = diagram.direction ?? 'horizontal';
  const tag = flow ? 'ol' : 'ul';
  const arrow = `<svg class="diagram-connector" viewBox="0 0 32 12" aria-hidden="true"><path d="M1 6H29M23 1L29 6L23 11" fill="none" stroke="currentColor" stroke-width="1.5"/></svg>`;
  return `<figure class="diagram-figure" data-semantic-visual="diagram" data-check-overflow><figcaption class="diagram-title">${escape(diagram.title)}</figcaption><${tag} class="diagram diagram-${diagram.type}${flow ? ` flow-${direction}` : ''}" role="list" style="--diagram-columns:${flow ? diagram.items.length : diagram.columns ?? 2}" data-check-overflow>${diagram.items.map((item, i) => `<li class="diagram-node${diagram.focus === i ? ' diagram-focus' : ''}"><h3 class="diagram-label" data-readability data-check-overflow>${lines(item.label)}</h3>${item.detail ? `<p class="diagram-detail" data-readability data-check-overflow>${lines(item.detail)}</p>` : ''}${flow && i < diagram.items.length - 1 ? arrow : ''}</li>`).join('')}</${tag}></figure>`;
}

function slideBody(slide) {
  switch (slide.layout) {
    case 'cover': return `<div class="cover-titles" data-check-overflow><h2>${lines(slide.title)}</h2>${slide.subtitle ? `<p class="cover-subtitle">${lines(slide.subtitle)}</p>` : ''}</div><div class="cover-meta" data-check-overflow>${slide.presenter ? paragraph(slide.presenter) : ''}${slide.date ? paragraph(slide.date) : ''}</div>`;
    case 'agenda': return `<ol class="agenda-list${slide.active !== undefined ? ' has-active' : ''}" role="list" data-check-overflow>${slide.items.map((item, i) => `<li${i === slide.active ? ' class="agenda-active"' : ''}><span class="agenda-number" aria-hidden="true">${String(i + 1).padStart(2, '0')}.</span><span class="agenda-label" data-check-overflow>${lines(item)}</span></li>`).join('')}</ol>`;
    case 'text': return `<div class="body-text" data-check-overflow>${slide.lead ? `<h3>${lines(slide.lead)}</h3>` : ''}${paragraphs(slide.paragraphs)}</div>`;
    case 'two-column': return `<div class="columns${slide.right.paragraphs ? '' : ' evidence-columns'}" data-check-overflow><div class="narrative" data-check-overflow>${slide.left.heading ? `<h3 class="standard-narrative-title">${lines(slide.left.heading)}</h3>` : ''}${paragraphs(slide.left.paragraphs)}</div><div class="visual-column" data-check-overflow>${slide.right.heading ? `<h3 class="${slide.right.paragraphs ? '' : 'standard-visual-title'}">${lines(slide.right.heading)}</h3>` : ''}${slide.right.paragraphs ? paragraphs(slide.right.paragraphs) : ''}${slide.right.chart ? chartFigure(slide.right.chart, 528.24, slide.right.heading ? 260 : 296) : ''}${slide.right.image ? imageFigure(slide.right.image) : ''}${slide.right.table ? tableFigure(slide.right.table, slide.right.heading ?? slide.title) : ''}${slide.right.diagram ? diagramFigure(slide.right.diagram) : ''}</div></div>`;
    case 'chart': return `<div class="content-panel${slide.lead ? ' has-lead' : ''}" data-check-overflow>${slide.lead ? `<p class="lead">${lines(slide.lead)}</p>` : ''}${chartFigure(slide.chart, 884, slide.lead ? 254 : 300)}</div>`;
    case 'table': return `<div class="content-panel table-panel" data-check-overflow>${slide.lead ? `<p class="lead">${lines(slide.lead)}</p>` : ''}${tableFigure(slide.table, slide.title)}</div>`;
    case 'diagram': return `<div class="content-panel${slide.lead ? ' has-lead' : ''}" data-check-overflow>${slide.lead ? `<p class="lead">${lines(slide.lead)}</p>` : ''}${diagramFigure(slide.diagram)}</div>`;
    case 'image': return `<div class="content-panel${slide.lead ? ' has-lead' : ''}" data-check-overflow>${slide.lead ? `<p class="lead">${lines(slide.lead)}</p>` : ''}${imageFigure(slide.image)}</div>`;
    case 'closing': return `<h2 class="closing-title" data-check-overflow>${lines(slide.title)}</h2><div class="closing-contact" data-check-overflow>${paragraphs(slide.contact)}</div>`;
    default: throw new Error(`Unknown slide layout: ${slide.layout}`);
  }
}

export function renderDeck(deck, assets) {
  const slides = deck.slides.map((slide, i) => {
    const lang = slide.lang ?? deck.lang ?? 'zh-CN';
    const languageKey = lang === 'en' ? 'en' : 'cn';
    const backgroundKey = slide.layout === 'cover' ? `cover-${languageKey}` : slide.layout === 'closing' ? `ending-${languageKey}` : slide.layout === 'agenda' ? 'toc' : 'content';
    const framed = !['cover', 'closing'].includes(slide.layout);
    const visualMetadata = `${slide.visualTextBinding ? ` data-visual-text-binding="${escape(JSON.stringify(slide.visualTextBinding))}"` : ''}${slide.visualExemption ? ` data-visual-exemption="${escape(slide.visualExemption)}"` : ''}`;
    return `<section class="slide" data-layout="${slide.layout}" data-slide-number="${i + 1}"${visualMetadata}${i === 0 ? ' data-active' : ''} lang="${escape(lang)}" aria-label="${i + 1}. ${escape(slide.title)}" style="width:${assets.width}px;height:${assets.height}px"><img class="brand-background" src="${escape(assets.backgrounds[backgroundKey])}" alt="" aria-hidden="true">${framed ? `<h2 class="slide-title" data-check-overflow>${lines(slide.title)}</h2>` : ''}${slideBody(slide)}${framed ? `<span class="page-number">${i + 1}</span>` : ''}${slide.source ? `<p class="source" data-check-overflow>${lines(slide.source)}</p>` : ''}${slide.notes ? `<aside class="speaker-notes" hidden>${lines(slide.notes)}</aside>` : ''}</section>`;
  }).join('\n');
  const lang = deck.lang ?? 'zh-CN';
  const en = lang === 'en';
  const fontFormat = assets.font.startsWith('data:font/ttf') ? 'truetype' : assets.font.startsWith('data:font/otf') ? 'opentype' : assets.font.startsWith('data:font/woff;') ? 'woff' : 'woff2';
  const latinFaces = [['regular', 400], ['bold', 700]].map(([name, weight]) => `@font-face{font-family:EFundLatin;src:url("${assets.latinFonts[name]}") format("woff2");font-weight:${weight};font-style:normal;font-display:block}`).join('');
  return `<!doctype html>
<html lang="${escape(lang)}"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1"><meta name="generator" content="efund-slides-template"><title>${escape(deck.title)}</title><style>@font-face{font-family:EFund;src:url("${assets.font}") format("${fontFormat}");font-weight:400;font-style:normal;font-display:block}${latinFaces}:root{--slide-width:${assets.width}px;--slide-height:${assets.height}px}@page{size:${assets.width / 96}in ${assets.height / 96}in;margin:0}\n${assets.css}</style></head><body><h1 class="visually-hidden">${escape(deck.title)}</h1><main id="deck" class="deck">${slides}</main><nav class="player" aria-label="${en ? 'Presentation controls' : '幻灯片控制'}"><button type="button" data-action="previous" aria-label="${en ? 'Previous slide' : '上一页'}">←</button><output id="slide-status" aria-live="polite" aria-atomic="true">1 / ${deck.slides.length}</output><button type="button" data-action="next" aria-label="${en ? 'Next slide' : '下一页'}">→</button><button type="button" data-action="overview" aria-pressed="false">${en ? 'Overview' : '总览'}</button><button type="button" data-action="fullscreen">${en ? 'Fullscreen' : '全屏'}</button><button type="button" data-action="print">${en ? 'Print preview' : '打印预览'}</button></nav><noscript><style>.slide{display:block!important}.deck{display:block!important}.player{display:none!important}</style></noscript><script>${assets.player.replace(/<\/script/gi, '<\\/script')}</script></body></html>`;
}
