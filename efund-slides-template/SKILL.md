---
name: efund-slides-template
description: 按易方达模板制作或修改幻灯片，以 HTML 为制作母版；用户要求网页、PDF 或 PPT/PPTX 时均先完成 HTML，再按需导出。沿用 V5 品牌视觉及经过打磨的内容、版式与复核规则。
metadata:
  version: "0.1.1"
---

# 易方达网页幻灯片

制作母版始终是可离线打开的单文件 HTML，用户只要 PPT/PDF 时也一样。固定品牌图形来自原始 PPT 模板，标题、正文、表格和图表保留为 HTML/SVG 内容；更改内容后重新构建。技能自带易方达中文字体及 Arial 常规/粗体，生成时全部内嵌，无需在目标电脑安装字体。

## 制作

1. 制作前读 [design-rules.md](references/design-rules.md)，确定受众、故事线和每页结论，按内容关系选择版式。普通正文提供承载证据或关系的视觉，并填写 `visualTextBinding`；法务或用户明确要求的纯文字页写 `visualExemption`。优先适用的左解释右证据布局，不以卡片墙、装饰图或虚构数据凑页。
2. 阅读 [authoring.md](references/authoring.md) 的输入字段，用 [demo.json](examples/demo.json) 为结构示例，编写项目内的 `deck.json`。例子是版式样例，不照抄其中的数值或目录；实际报告用用户提供或已核实的数据。
3. 运行构建。`SKILL_DIR` 指本技能目录，命令中的输入、输出使用项目绝对路径：

   ```bash
   bun "$SKILL_DIR/scripts/build.mjs" --input "$PROJECT/deck.json" --output "$PROJECT/slides.html"
   ```

   常规构建只需 Bun，使用 `assets/fonts/` 中随技能分发的字体，不需要 Python、LibreOffice 或本机字体。只有显式替换中文字体时才用 `--font`；外部字体通过 `uv` 在临时副本中完成兼容修复和转换。已有输出默认保留，确认是在更新该产物时加 `--force`。
4. 按 [quality-review.md](references/quality-review.md) 运行浏览器检查并逐页查看截图。首次检查/导出在技能目录运行 `bun install --frozen-lockfile`，使用本机 Chrome；没有 Chrome 时可 `bunx playwright install chromium` 并传 `--channel chromium`。

   ```bash
   bun "$SKILL_DIR/scripts/check.mjs" --input "$PROJECT/slides.html" --out "$PROJECT/qa"
   ```

   完成标准：`report.json.ok` 为 true，逐项处理 `warnings`，按实际截图填写 `visual-review.json` 并用 `verify-review.mjs` 验证。检查覆盖字体、图片、溢出、真实换行、单字尾行、已实现间距和运行错误；视觉判断另核对主焦点、证据、留白、字形与隐私。文字放不下时精简、换版式或拆页，不能缩字救场。Bun 负责执行脚本，不能保证任意输入自动美观；固定模板与检查也不能替代逐页审阅。
5. 用户要 PDF 或 PPT/PPTX 时，从这份已完成的 HTML 导出：

   ```bash
   bun "$SKILL_DIR/scripts/export.mjs" --input "$PROJECT/slides.html" --output "$PROJECT/slides.pdf"
   bun "$SKILL_DIR/scripts/export.mjs" --input "$PROJECT/slides.html" --output "$PROJECT/slides.pptx"
   ```

   按请求执行对应命令。导出会重跑浏览器检查，失败不写交付文件；检查最终格式的页数、顺序、尺寸与实际打开效果。PDF 从同一 HTML 直接打印。PPTX 每页嵌入 2 倍分辨率的完整 HTML 截图，可用 `--scale 3` 或 `4` 提高清晰度，保留画面但不提供逐元素编辑；修改回到 JSON/HTML。用户明确要求原生可编辑时说明这一限制，不悄悄切到直接制作原生 PPT。默认保留已有文件，更新时才加 `--force`。
6. 交付用户要求的格式，同时保留 HTML 来源；简短说明栅格 PPTX 的编辑边界，以及实际未完成的检查。没有逐页观察或目标软件打开证据时不声称已完成这些检查。

## 模板维护

内容或行为变更时按语义化版本更新 `metadata.version` 与 `package.json.version`，两处保持一致。

日常制作直接复用 `assets/backgrounds/` 与 `templates/`。仅用户更换源模板或要求重建底板时读取 [template.md](references/template.md)。保留源图形、页面比例、中文字体、蓝青配色、封面声明和正文页脚；不要把完整成品页作为背景图代替可编辑正文。

内容、布局与验收规则移植自用户提供的 `efund-ppt-maker`，适配为网页渲染与检查；详见两份规则文档末尾的来源与边界。运行不依赖该原生 Skill 副本。
