// Adapted from the supplied efund-ppt-maker writing and visual-evidence contracts.
// Heuristics produce review prompts, not factual or aesthetic verdicts.
const writingRules = [
  ['contrast-not-but', /(?:不是|不只是|不再是|并非|绝非)[^。！？；\n]{1,48}?[，,]?(?:而是|而在于)/u, '直接说明对象、变化和结果'],
  ['not-only-more', /(?:不仅|不只)[^。！？；\n]{1,48}?[，,；;](?:更|而且|还|也)/u, '拆成具体动作和可验证结果'],
  ['three-more', /更[^，。！？；\n]{1,12}[、，]更[^，。！？；\n]{1,12}[、，]更[^，。！？；\n]{1,12}/u, '用具体指标替换连续排比'],
  ['make-truly', /让[^。！？；\n]{1,28}真正(?:成为|实现|释放|发挥)/u, '写明条件、动作和可观察结果'],
  ['slogan-engine', /(?:打造|构建|成为|培育|注入)[^。！？；\n]{0,24}(?:新引擎|新动能|新范式)/u, '写明能力或业务指标'],
  ['slogan-new-chapter', /(?:开启|书写|共创)[^。！？；\n]{0,20}(?:新篇章|新未来)/u, '说明下一阶段交付、责任和时间'],
  ['slogan-leap', /(?:实现|推动|完成|引领)[^。！？；\n]{0,24}(?:跃迁|蝶变)/u, '说明变化维度、基线和目标'],
  ['vague-empower', /(?:全面|深度|持续|智能|精准|高效|科技|AI|数据|平台)?赋能(?:业务|发展|增长|转型|创新|未来|组织|行业|千行百业|提质增效)/u, '写明支持、缩短、减少等实际动作'],
  ['slogan-closed-loop', /(?:打造|构建|形成)[^。！？；\n]{0,20}(?:智能|业务|管理|价值)?闭环/u, '写清触发、步骤、反馈和责任主体'],
  ['boilerplate-wave', /在[^，。！？；\n]{1,24}(?:浪潮|时代|大背景)下/u, '从与本页相关的事实切入'],
  ['boilerplate-development', /随着[^，。！？；\n]{1,28}不断(?:发展|演进|深入|加速)/u, '说明实际变化及业务影响'],
];

export function reviewContent(slides) {
  const warnings = [];
  const body = slides.filter(s => !['cover', 'agenda', 'closing'].includes(s.layout));
  for (const slide of slides) {
    const add = (code, message, extra = {}) => warnings.push({slide: slide.slide, code, message, ...extra});
    for (const [code, pattern, rewrite] of writingRules) {
      const match = slide.text.match(pattern);
      if (match) add(code, rewrite, {excerpt: match[0]});
    }
    if (slide.hasNotes) add('hidden-notes', '备注随 HTML 分发，请检查其是否可交付');
    if (!body.includes(slide)) continue;
    if (!slide.visualTypes.length && !slide.visualExemption) add('semantic-visual-missing', '正文须有支撑结论的信息视觉；逐字引文等例外需写明 visualExemption');
    if (slide.visualTypes.length) {
      const binding = slide.visualTextBinding;
      if (!binding || ['supportsClaim', 'textAnchor', 'informationCarried'].some(k => typeof binding[k] !== 'string' || !binding[k].trim())) add('visual-binding-missing', '填写 visualTextBinding，说明视觉支撑的结论和新增信息');
      else if (!slide.text.replace(/\s/g, '').includes(binding.textAnchor.replace(/\s/g, ''))) add('visual-anchor-missing', 'textAnchor 未出现在本页可见文字中，请核实图文对应');
      if (slide.visualTypes.some(t => ['chart', 'image', 'table'].includes(t)) && !slide.hasSource) add('evidence-source-missing', '补充图表、表格或图片来源、日期和口径；示意内容明确标注');
    }
  }
  for (let i = 2; i < body.length; i++) {
    if (body[i].layout === body[i - 1].layout && body[i].layout === body[i - 2].layout) warnings.push({slide: body[i].slide, code: 'repeated-layout', message: '连续三页使用同一布局，请核实内容关系；系列比较等合理例外可在审阅中说明'});
  }
  return warnings;
}
