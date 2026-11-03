---
name: efund-slides-template
description: 当用户要求用易方达模板制作或修改 HTML 网页幻灯片、网页 PPT，或从该网页演示导出 PDF 时使用。以提供的易方达 V5 PPT 模板为视觉依据。
---

# 易方达网页幻灯片

产物是可离线打开的单文件 HTML。固定品牌图形来自原始 PPT 模板，标题、正文、表格和图表保留为 HTML/SVG 内容；更改内容后重新构建。技能自带易方达中文字体及 Arial 常规/粗体，生成时全部内嵌，无需在目标电脑安装字体。

## 制作

1. 明确主题、受众和材料；按内容选择封面、目录、文字、双栏、图表、表格、图片或封底。阅读 [authoring.md](references/authoring.md) 的输入字段，用 [demo.json](examples/demo.json) 为结构示例，编写项目内的 `deck.json`。示例数值只展示排版；实际报告用用户提供或已核实的数据。
2. 运行构建。`SKILL_DIR` 指本技能目录，命令中的输入、输出使用项目绝对路径：

   ```bash
   bun "$SKILL_DIR/scripts/build.mjs" --input "$PROJECT/deck.json" --output "$PROJECT/slides.html"
   ```

   常规构建只需 Bun，使用 `assets/fonts/` 中随技能分发的字体，不需要 Python、LibreOffice 或本机字体。只有显式替换中文字体时才用 `--font`；外部字体通过 `uv` 在临时副本中完成兼容修复和转换。已有输出默认保留，确认是在更新该产物时加 `--force`。
3. 运行浏览器检查，逐页查看截图。首次检查在技能目录运行 `bun install --frozen-lockfile`，使用本机 Chrome；没有 Chrome 时可 `bunx playwright install chromium` 并传 `--channel chromium`。

   ```bash
   bun "$SKILL_DIR/scripts/check.mjs" --input "$PROJECT/slides.html" --out "$PROJECT/qa"
   ```

   完成标准：`report.json` 的 `ok` 为 true，中英文三份字体和图片加载成功，无溢出、脚本错误或外部请求；逐页截图无遮挡、意外换行或错误数据。文字放不下时由 Agent 精简、换版式或拆页后重新构建和检查，保留原稿字号与品牌区域。构建器不会自动拆页或改写；自动检查不替代逐页判断内容密度、视觉层次、图表选择和内容准确性。
4. 交付 HTML 链接，并说明有无未验证事项。用户要 PDF 时给检查命令加 `--pdf`，核对 PDF 页数与截图。需要可编辑 PPTX 时另行转换并检查，当前工具不宣称提供 PPTX 导出。

## 模板维护

日常制作直接复用 `assets/backgrounds/` 与 `templates/`。仅用户更换源模板或要求重建底板时读取 [template.md](references/template.md)。保留源图形、页面比例、中文字体、蓝青配色、封面声明和正文页脚；不要把完整成品页作为背景图代替可编辑正文。

本技能与原生 PowerPoint 制作工具分开：这里的主产物始终是网页幻灯片。
