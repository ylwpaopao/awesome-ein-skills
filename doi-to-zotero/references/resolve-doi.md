# 从文献链接提取 DOI

输入是普通文献链接时，先用可用连接器或浏览器打开原链接并跟随正常重定向。核对主标题，优先读取当前论文声明的 `citation_doi`、`prism.doi` 或 DOI 类型的 `DC.Identifier`；没有元数据时，读取标题、作者附近明确标出的主 DOI 链接。

使用 Computer Use 的浏览器时，可在已打开的文章标签页通过只读 DOM 查询取得最小证据，例如：

```javascript
await tab.playwright.evaluate(() => ({
  url: location.href,
  title: document.querySelector('h1')?.textContent?.trim() || document.title,
  metadata: Array.from(document.querySelectorAll('meta[name], meta[property]'))
    .filter(el => /^(citation_doi|prism\.doi|dc\.identifier|dc\.identifier\.doi)$/i
      .test(el.getAttribute('name') || el.getAttribute('property') || ''))
    .map(el => ({
      name: el.getAttribute('name') || el.getAttribute('property'),
      content: el.getAttribute('content')
    }))
}));
```

将结果保存到任务临时 JSON 文件，运行 `uv run scripts/workflow_files.py resolve '〔证据文件〕'` 规范化 DOI；脚本路径相对本技能目录。若只有标题旁标出的主 DOI，或已核对它以解决元数据冲突，将该值写入 `primary_doi` 字段，脚本优先使用此已核实声明。

只使用当前论文的主 DOI，不对整页所有 `10.…` 字符串取第一个匹配。元数据冲突时核对标题旁的声明；仍无法确定、页面无法读取或没有主 DOI 时，明确提示未能从该链接确定 DOI，并请用户提供 DOI。成功解析后继续同一套固定入库流程，不再要求其他参数。
