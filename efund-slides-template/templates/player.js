(() => {
  'use strict';
  const slides = [...document.querySelectorAll('.slide')];
  const root = document.documentElement;
  const status = document.querySelector('#slide-status');
  const buttons = Object.fromEntries([...document.querySelectorAll('[data-action]')].map(button => [button.dataset.action, button]));
  const params = new URLSearchParams(location.search);
  const slideWidth = parseFloat(getComputedStyle(root).getPropertyValue('--slide-width'));
  const slideHeight = parseFloat(getComputedStyle(root).getPropertyValue('--slide-height'));
  let index = 0;
  let overview = params.has('overview');
  root.classList.toggle('overview', overview);
  root.classList.toggle('print-view', params.has('print'));

  function resize() {
    root.style.setProperty('--scale', Math.max(.05, Math.min((innerWidth - 24) / slideWidth, (innerHeight - 82) / slideHeight)));
    root.style.setProperty('--overview-scale', Math.max(.05, Math.min(1, (innerWidth - 24) / slideWidth)));
  }
  function goTo(next, updateHash = true) {
    index = Math.max(0, Math.min(slides.length - 1, Number.isFinite(next) ? Math.trunc(next) : 0));
    slides.forEach((slide, i) => {
      slide.toggleAttribute('data-active', i === index);
      slide.setAttribute('aria-hidden', String(!overview && i !== index && !params.has('print')));
    });
    status.textContent = `${index + 1} / ${slides.length}`;
    buttons.previous.disabled = index === 0;
    buttons.next.disabled = index === slides.length - 1;
    if (updateHash && location.hash !== `#${index + 1}`) history.replaceState(null, '', `#${index + 1}`);
    return index;
  }
  function toggleOverview() {
    overview = !overview;
    root.classList.toggle('overview', overview);
    buttons.overview.setAttribute('aria-pressed', String(overview));
    goTo(index, false);
    resize();
  }
  function checkOverflow() {
    const issues = [];
    root.classList.add('measuring');
    try {
      slides.forEach((slide, slideIndex) => {
        const bounds = slide.getBoundingClientRect();
        for (const element of slide.querySelectorAll('[data-check-overflow]')) {
          const box = element.getBoundingClientRect();
          const id = element.className || element.tagName;
          const issue = type => issues.push({slide: slideIndex + 1, element: id, type});
          if (element.scrollWidth > element.clientWidth + 1 || element.scrollHeight > element.clientHeight + 1) issue('text-overflow');
          if (box.left < bounds.left - 1 || box.right > bounds.right + 1 || box.top < bounds.top - 1 || box.bottom > bounds.bottom + 1) issue('outside-slide');
          if (!['cover', 'closing', 'agenda'].includes(slide.dataset.layout) && !element.classList.contains('slide-title') && !element.classList.contains('source') && box.bottom - bounds.top > 488) issue('footer-clearance');
        }
        for (const svg of slide.querySelectorAll('.data-chart')) {
          const vb = svg.viewBox.baseVal;
          for (const label of svg.querySelectorAll('text')) {
            const box = label.getBBox();
            if (box.x < -1 || box.y < -1 || box.x + box.width > vb.width + 1 || box.y + box.height > vb.height + 1) {
              issues.push({slide: slideIndex + 1, element: 'chart-label', type: 'outside-chart', text: label.textContent});
            }
          }
        }
      });
    } finally { root.classList.remove('measuring'); }
    return issues;
  }
  // Read the browser's laid-out glyph rectangles, never estimate lines by character count.
  function measureReadability() {
    const textLayout = [], issues = [];
    root.classList.add('measuring');
    try {
      slides.forEach((slide, slideIndex) => {
        const bounds = slide.getBoundingClientRect();
        const targets = slide.querySelectorAll('h2,h3,p,figcaption,caption,th,td,.agenda-label,[data-readability]');
        for (const element of targets) {
          if (element.closest('[hidden],.visually-hidden') || element.classList.contains('source')) continue;
          const rows = [], walker = document.createTreeWalker(element, NodeFilter.SHOW_TEXT);
          let node;
          while ((node = walker.nextNode())) {
            let offset = 0;
            for (const char of node.textContent) {
              const range = document.createRange();
              range.setStart(node, offset); offset += char.length; range.setEnd(node, offset);
              const box = range.getBoundingClientRect();
              if (box.width === 0 || box.height === 0) continue;
              let row = rows.find(r => Math.min(r.bottom, box.bottom) - Math.max(r.top, box.top) > Math.min(r.bottom - r.top, box.height) * .5);
              if (!row) { row = { text: '', top: box.top, bottom: box.bottom }; rows.push(row); }
              row.text += char; row.top = Math.min(row.top, box.top); row.bottom = Math.max(row.bottom, box.bottom);
            }
          }
          rows.sort((a, b) => a.top - b.top);
          const lines = rows.map(r => r.text.trim()).filter(Boolean);
          if (!lines.length) continue;
          const record = { slide: slideIndex + 1, element: element.className || element.tagName.toLowerCase(), source: 'rendered', lineCount: lines.length, lines };
          textLayout.push(record);
          if (lines.length > 1 && lines.some(line => /^[\p{P}\s]*\p{Script=Han}[\p{P}\s]*$/u.test(line))) issues.push({ slide: slideIndex + 1, element: record.element, type: 'single-han-line', lines });
          const next = element.nextElementSibling;
          if (element.matches('h3,.lead') && next?.matches('figure,table,.diagram')) {
            const gap = next.getBoundingClientRect().top - Math.max(...rows.map(r => r.bottom));
            if (gap < 15.5) issues.push({ slide: slideIndex + 1, element: record.element, type: 'text-graphic-spacing', gap: Math.round(gap * 10) / 10, minimum: 16 });
          }
          if (!['cover', 'closing', 'agenda'].includes(slide.dataset.layout) && !element.matches('.slide-title') && Math.max(...rows.map(r => r.bottom)) - bounds.top > 488) issues.push({ slide: slideIndex + 1, element: record.element, type: 'text-footer-clearance' });
        }
        const title = slide.querySelector('.slide-title');
        if (title && getComputedStyle(title).color !== 'rgb(255, 255, 255)') issues.push({slide: slideIndex + 1, type: 'title-color'});
        for (const element of slide.querySelectorAll('*')) {
          const style = getComputedStyle(element);
          if (style.textShadow !== 'none' || style.boxShadow !== 'none') {
            issues.push({slide: slideIndex + 1, element: element.className || element.tagName, type: 'shadow'});
            break;
          }
        }
      });
    } finally { root.classList.remove('measuring'); }
    return { textLayout, issues };
  }
  buttons.previous.addEventListener('click', () => goTo(index - 1));
  buttons.next.addEventListener('click', () => goTo(index + 1));
  buttons.overview.addEventListener('click', toggleOverview);
  buttons.print.addEventListener('click', () => window.print());
  buttons.fullscreen.addEventListener('click', async () => {
    try {
      if (document.fullscreenElement) await document.exitFullscreen();
      else if (root.requestFullscreen) await root.requestFullscreen();
    } catch { /* Fullscreen can be denied by an embedded browser; slides remain usable. */ }
  });
  document.addEventListener('keydown', event => {
    if (event.altKey || event.ctrlKey || event.metaKey || event.target.closest('button,input,textarea,select,[contenteditable="true"]')) return;
    const targets = {ArrowLeft: index - 1, PageUp: index - 1, ArrowRight: index + 1, PageDown: index + 1, Home: 0, End: slides.length - 1};
    if (event.key in targets) { event.preventDefault(); goTo(targets[event.key]); }
  });
  window.addEventListener('resize', resize);
  window.addEventListener('hashchange', () => goTo(Number(location.hash.slice(1)) - 1, false));
  const ready = Promise.all([
    document.fonts.load('400 16px EFund', '易方达'),
    document.fonts.load('400 16px EFundLatin', 'Arial 0123'),
    document.fonts.load('700 16px EFundLatin', 'Arial 0123'),
    document.fonts.ready,
    ...[...document.images].map(img => img.decode().catch(() => { throw new Error(`Image could not be decoded: ${img.alt || img.className}`); }))
  ]).then(() => {
    if (!document.fonts.check('16px EFund', '易方达')) throw new Error('The EFund font did not load.');
    if (!document.fonts.check('400 16px EFundLatin', 'Arial 0123') || !document.fonts.check('700 16px EFundLatin', 'Arial 0123')) throw new Error('The bundled Latin fonts did not load.');
    goTo(Number(location.hash.slice(1)) - 1, false);
    buttons.overview.setAttribute('aria-pressed', String(overview));
    resize();
    return true;
  });
  window.efund = {ready, goTo, get currentIndex() { return index; }, checkOverflow, measureReadability};
  resize();
  goTo(Number(location.hash.slice(1)) - 1, false);
})();
