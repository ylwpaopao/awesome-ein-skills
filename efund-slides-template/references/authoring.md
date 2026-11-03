# 输入与布局

构建器接受 UTF-8 JSON，所有文字按纯文本转义；换行用 `\n`。无需写 HTML，也不接受 HTML 字符串。图片路径相对 JSON 文件解析；最终产物会内嵌图片、字体、样式和脚本。

Agent 负责整理材料、选版式和控制每页信息量；Bun 运行脚本，将内容套入模板，并调用浏览器检查。脚本固定品牌样式和几何规则，不自动挑选版式、拆页或改写文案。生成成功仅表示输入合法；检查通过后仍须看逐页截图，确认密度、留白和图表表达适合本次内容。

```json
{
  "title": "报告名称",
  "lang": "zh-CN",
  "slides": [
    {"layout":"cover","title":"报告名称","subtitle":"副标题","presenter":"部门或报告人","date":"2026年11月"},
    {"layout":"two-column","title":"材料核实与视觉复核各有责任人","left":{"heading":"两项职责分别验收","paragraphs":["材料核实确认事实与来源。视觉复核检查图表表达和阅读顺序。"]},"right":{"diagram":{"type":"matrix","title":"两项交付检查","items":[{"label":"材料核实","detail":"核对事实与来源"},{"label":"视觉复核","detail":"查看每页渲染"}]}},"visualTextBinding":{"supportsClaim":"两项检查承担不同职责","textAnchor":"两项职责分别验收","informationCarried":"两个并列职责及各自检查对象"}},
    {"layout":"closing","title":"谢谢"}
  ]
}
```

顶层必填 `title`、非空 `slides`；`lang` 默认 `zh-CN`，可设为 `en`。每页必填 `layout`、`title`，可单独指定 `lang`。英文模式使用英文封面和封底；原稿的目录和正文品牌页脚为中文，保持原样。

| layout | 字段 | 使用方式 |
| --- | --- | --- |
| `cover` | `subtitle?`, `presenter?`, `date?` | 标题宜一行，副标题一行；双语可将译名放在副标题 |
| `agenda` | `items: string[]`, `active?: number` | 1–7项；active为零基索引，可用于章节导航 |
| `text` | `paragraphs: string[]`, `lead?: string` | 保留V5的15pt正文；用于确需文字结构的页面，普通正文优先用有信息视觉的版式 |
| `two-column` | `left: {heading?, paragraphs}`, `right: {heading?, paragraphs?或chart?或image?或table?或diagram?}` | 右侧五选一；有视觉时左38%／右62%（扣除32px栏隙），正文12pt／150%行距 |
| `chart` | `chart`, `lead?` | 主图占据正文区域 |
| `table` | `table: {title?, columns: string[], rows: (string或number)[][]}`, `lead?` | 青色表头与灰白交替底色；行数受实际内容高度限制 |
| `image` | `image`, `lead?` | 显示用户提供的截图、照片或预先绘制的复杂图表 |
| `diagram` | `diagram`, `lead?` | 简单真实流程或并列关系；不需要数值也能承载机制与职责信息 |
| `closing` | `contact?: string[]` | 标准答谢词，最多4行联系信息 |

正文页可添加 `source`，为页脚线以上单行来源文字（7pt）。`notes` 是隐藏的演讲备注，会随 HTML 交付；不要放不应交付的信息。封面、目录和封底的底部空间有固定用途，不接受 `source`，来源应放到对应正文页。

每个普通内容页填写 `visualTextBinding: {supportsClaim, textAnchor, informationCarried}`：分别写具体主张、相邻可见文字锚点、视觉独立表达的证据或关系。`textAnchor` 原样引用本页可见短句，例如 `"两项职责分别验收"`，不要添加不在画面上的“左侧／标题”等位置前缀。可追加 `visualType`、`sourceOrGeneration`、`whyThisVisual`。构建器将它写入非可视的 DOM 属性，供检查和复核使用；字段完整不证明图文关系成立。确有文字结构要求的页可用 `visualExemption: "具体原因"` 提交人工判断，不能与绑定同时填写，不能用它批量豁免普通正文；详细规则见 [design-rules.md](design-rules.md)。

证据双区左侧解释标题固定15pt粗体，右侧 `heading` 是10pt常规视觉标题；图表、表格和关系图自带标题时通常省略右侧 `heading`，避免重复。正文增多时精简、重排或拆页，不减小字号。结构上限只是数据校验上限，实际容量由浏览器换行与逐页视觉检查决定。

## 表格

```json
{
  "title":"各方案的办理时长",
  "mode":"compact-comparison",
  "columns":["方案","办理时长（天）","适用条件"],
  "rows":[["甲",2,"资料完整"],["乙",3,"需补充材料"]],
  "columnWidths":[25,25,50],
  "numericColumns":[1],
  "highlightRows":[0]
}
```

此例数值仅演示字段。`table` 可用于整页或 `two-column.right.table`。表头白字加粗居中，文字正文左对齐，数字列右对齐。`numericColumns` 为零基列索引；省略时只有整列均为 JSON 数字才自动识别，带百分号或单位的字符串需显式声明。同一列的精度、单位和符号由作者统一。

| mode | 使用场景与样式 |
| --- | --- |
| `striped`（默认） | 兼容原有表格，灰白交替，无网格线 |
| `row-highlight` | 分类与重点对象：白底主体、浅灰小计、整行青色强调；无正文分隔线 |
| `compact-comparison` | 少量方案／指标对照，灰白交替，可高亮结论行；无正文分隔线 |
| `task-list` | 3–5项工作模块；固定三列“序号／模块／说明”，首列大号青色序号，仅细水平分隔线 |

`highlightRows` 为最多2个重点行的零基索引；`subtotalRows` 为浅灰小计行索引，重点行优先。`columnWidths` 可指定正百分比数组，列数须匹配且总和为100。后三种模式正文11pt，默认模式保留12pt；不会自动缩字。双区右侧表格宜少列、短说明，复杂分组拆页；当前不支持合并单元格。

## 关系图

```json
{
  "type":"flow",
  "title":"审阅完成后交付",
  "direction":"horizontal",
  "items":[{"label":"核对材料","detail":"确认来源与口径"},{"label":"逐页复核","detail":"检查表达与版式"},{"label":"交付成品","detail":"附上可追溯材料"}],
  "focus":1
}
```

`flow` 仅用于真实顺序、因果或阶段演进，支持2–4个节点，`direction` 为 `horizontal`（默认）或 `vertical`。右侧窄栏宜用2–3步纵向流程；节点说明过长会报溢出，不会自动缩小。`matrix` 用于并列职责／条件／比较，支持2–6项，`columns` 为2（默认）或3；不画连接线。两类都必填 `title`、`items[].label`，可加短 `detail`，以及唯一深蓝焦点 `focus`（零基索引）。

关系图可作为整页 `diagram` 或 `two-column.right.diagram`。它保留 HTML 文字和几何布局；复杂架构、反馈、泳道等关系应扩展有语义的专用布局或预绘图形，不把并列条件硬改成流程。

## 图表

```json
{
  "type":"bar",
  "title":"季度完成数",
  "labels":["一季度","二季度","三季度","四季度"],
  "series":[{"name":"完成数","values":[12,18,24,30]}],
  "unit":"项"
}
```

`type` 支持 `bar`、`line`。`unit` 会自动以括号追加到图表标题，填写后不要在 `title` 中重复单位。每个系列的 `values` 数量必须与 `labels` 相同，数值必须有限；支持零和负数，缺值应先处理并说明口径。最多16个类别、4个系列是结构上限，不代表都能排下。类别较多、名称较长或数值跨越较大时，应减少展示项、拆页或使用图片布局。图表带可访问的数据表，不会从文字推测数值。

非零数值绝对值需在 `1e-100` 到 `1e100` 之间，超出时先转换单位；构建器会报错，避免浮点溢出产生空图。

## 图片

```json
{"src":"figures/chart.png","alt":"各阶段完成数由12项增加到30项","fit":"contain"}
```

支持本地 PNG/JPEG/WebP/GIF 或对应 base64 data URI；不自动请求远程 URL，不接受活动 SVG。`fit` 默认 `contain` 保留全图，可显式选择 `cover` 裁切。图片先取得可用文件再构建；`alt` 描述图片表达的信息。

## 播放与检查

- 双击 HTML 即可离线打开；左右方向键、PageUp/PageDown、Home/End 翻页。
- 底部按钮提供总览、全屏和打印；`#3` 直达第三页，`?overview` 打开总览。
- 运行 `check.mjs --input slides.html --out qa`，检查输出包括逐页 PNG、`report.json`、`text-layout.json` 和待填写的 `visual-review.template.json`。`report.json.ok` 仅代表自动检查通过；逐项处理 `warnings`，查看真实换行，再按 [quality-review.md](quality-review.md) 逐页观察、填写 `visual-review.json` 并用 `verify-review.mjs` 校验。长文本失败应调整输入后重新生成和检查。
- 用户要求 PDF 或 PPT/PPTX 时仍先完成 HTML；运行 `bun scripts/export.mjs --input slides.html --output slides.pdf` 或把输出后缀换成 `.pptx`。可用 `--qa-dir` 指定导出检查目录；默认导出会重跑浏览器检查，失败不写交付文件。默认保留已有输出，更新时才用 `--force`。
- PDF/PPTX 均封装默认2倍分辨率的 HTML 整页图像，可用 `--scale 3` 或 `4` 提高清晰度。PPTX 不能逐元素编辑，PDF 文字不可直接选中或搜索；修改回到 JSON/HTML。采用截图是因为直接浏览器打印已复现中文合成粗体缺笔；播放器打印按钮仅作浏览器预览，正式交付使用导出脚本。每种最终格式分别核对页数、顺序、尺寸、实际打开和逐页外观，不能以 HTML 截图代替目标软件打开证据。
- 构建是确定性的模板填充；用户指定的复杂新布局可以扩展 `render.mjs` 与 CSS，修改后覆盖原有场景并重新检查。
