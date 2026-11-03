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
    document.fonts.ready,
    ...[...document.images].map(img => img.decode().catch(() => { throw new Error(`Image could not be decoded: ${img.alt || img.className}`); }))
  ]).then(() => {
    if (!document.fonts.check('16px EFund', '易方达')) throw new Error('The EFund font did not load.');
    goTo(Number(location.hash.slice(1)) - 1, false);
    buttons.overview.setAttribute('aria-pressed', String(overview));
    resize();
    return true;
  });
  window.efund = {ready, goTo, get currentIndex() { return index; }, checkOverflow};
  resize();
  goTo(Number(location.hash.slice(1)) - 1, false);
})();
