# 输入与布局

构建器接受 UTF-8 JSON，所有文字按纯文本转义；换行用 `\n`。无需写 HTML，也不接受 HTML 字符串。图片路径相对 JSON 文件解析；最终产物会内嵌图片、字体、样式和脚本。

```json
{
  "title": "报告名称",
  "lang": "zh-CN",
  "slides": [
    {"layout":"cover","title":"报告名称","subtitle":"副标题","presenter":"部门或报告人","date":"2026年11月"},
    {"layout":"text","title":"本页结论","paragraphs":["正文第一段。","正文第二段。"]},
    {"layout":"closing","title":"谢谢"}
  ]
}
```

顶层必填 `title`、非空 `slides`；`lang` 默认 `zh-CN`，可设为 `en`。每页必填 `layout`、`title`，可单独指定 `lang`。英文模式使用英文封面和封底；原稿的目录和正文品牌页脚为中文，保持原样。

| layout | 字段 | 使用方式 |
| --- | --- | --- |
| `cover` | `subtitle?`, `presenter?`, `date?` | 标题宜一行，副标题一行；双语可将译名放在副标题 |
| `agenda` | `items: string[]`, `active?: number` | 1–7项；active为零基索引，可用于章节导航 |
| `text` | `paragraphs: string[]`, `lead?: string` | 15pt正文；建议2–4段短文 |
| `two-column` | `left: {heading?, paragraphs}`, `right: {heading?, paragraphs?或chart?或image?}` | 左侧解释，右侧三种内容必须选一；正文12pt |
| `chart` | `chart`, `lead?` | 主图占据正文区域 |
| `table` | `table: {title?, columns: string[], rows: (string或number)[][]}`, `lead?` | 青色表头与灰白交替底色；行数受实际内容高度限制 |
| `image` | `image`, `lead?` | 显示用户提供的截图、照片或预先绘制的复杂图表 |
| `closing` | `contact?: string[]` | 标准答谢词，最多4行联系信息 |

正文页可添加 `source`，为页脚线以上单行来源文字（7pt）。`notes` 是隐藏的演讲备注，会随 HTML 交付；不要放不应交付的信息。封面、目录和封底的底部空间有固定用途，不接受 `source`，来源应放到对应正文页。

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

`type` 支持 `bar`、`line`。每个系列的 `values` 数量必须与 `labels` 相同，数值必须有限；支持零和负数，缺值应先处理并说明口径。最多16个类别、4个系列是结构上限，不代表都能排下。类别较多、名称较长或数值跨越较大时，应减少展示项、拆页或使用图片布局。图表带可访问的数据表，不会从文字推测数值。

非零数值绝对值需在 `1e-100` 到 `1e100` 之间，超出时先转换单位；构建器会报错，避免浮点溢出产生空图。

## 图片

```json
{"src":"figures/chart.png","alt":"各阶段完成数由12项增加到30项","fit":"contain"}
```

支持本地 PNG/JPEG/WebP/GIF 或对应 base64 data URI；不自动请求远程 URL，不接受活动 SVG。`fit` 默认 `contain` 保留全图，可显式选择 `cover` 裁切。图片先取得可用文件再构建；`alt` 描述图片表达的信息。

## 播放与检查

- 双击 HTML 即可离线打开；左右方向键、PageUp/PageDown、Home/End 翻页。
- 底部按钮提供总览、全屏和打印；`#3` 直达第三页，`?overview` 打开总览。
- 用 `check.mjs --pdf` 导出保留原稿页面尺寸的 PDF。手动打印时关闭浏览器页眉页脚并启用背景图形。
- 检查输出包括逐页 PNG、`report.json`，选用 PDF 时还包括 `slides.pdf`。长文本失败应调整输入后重新生成和检查。
- 构建是确定性的模板填充；用户指定的复杂新布局可以扩展 `render.mjs` 与 CSS，修改后覆盖原有场景并重新检查。
