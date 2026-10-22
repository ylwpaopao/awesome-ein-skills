# Zotero 保存方式

## 创建 item

先通过可用 Zotero 插件/MCP 按 DOI 精确查询。`library_search` 可使用 `conditions: [{condition: "DOI", operator: "is", value: DOI}]` 并传入目标 `libraryID`；普通全文检索结果必须再次核对 DOI，不能据此直接认定存在或不存在。

新建时优先 `library_import({kind: "identifiers", identifiers: [DOI], libraryID, targetCollectionId})`，随后 `library_read` 核对 DOI、类型、作者、期刊、年份与归属。已有 item 只增加目标 collection 归属，不移除其他分类。

需要出版商站点适配器、DOI 导入不可用或元数据缺失时，在单篇论文原文页使用 Chrome Zotero Connector：

1. 在 Zotero 选中目标 collection（默认“我的文库 / AssetPricing”，用户明确指定时覆盖）。如插件可查询当前目标，核对文库、完整分类路径及可写状态；只输出需要的字段。
2. 打开用户的原文链接，或通过 DOI 正常跳转到原文页，核对主标题和 DOI。在页面空白处右键，选择“保存到 Zotero”，也可使用扩展工具栏按钮。
3. 首选实际菜单列出的站点适配器。适配器名称不等于出版社名称，例如 Oxford Academic 页面可能显示 `Silverchair`。以当前菜单为准，不能把此名称用于所有来源。
4. 站点适配器不能完成时，检查它是否已创建 item，再依次尝试 `Embedded Metadata`、`DOI` 等结构化后备方式；通用 `Web Page` 保存不是期刊论文元数据的等效成功结果。
5. 等待并核对 item 的 DOI、标题、作者、期刊、年份、卷期和页码，以及目标 collection 归属。出现超时或 Linter 错误提示时先核对现有结果，避免再次保存产生重复项。

插件及 Connector 均不可用时，使用 Zotero Desktop 的“通过标识符添加条目”；仍无法完成则报告具体阻碍。不下载或手工导出 RIS/BibTeX 兜底，不在 Downloads 留下元数据中间文件。

Connector 的站点适配能力不等于公开的“按 URL 保存”API。旧的 `/connector/savePage` 已移除；`/connector/saveItems` 接受翻译后的条目数据，不能当作 URL 翻译服务。依据：[官方 Connector HTTP 文档](https://www.zotero.org/support/dev/client_coding/connector_http_server)、[Zotero 团队说明](https://forums.zotero.org/discussion/128498/outdated-documentation-on-connector-http-endpoints)（2026-10-22 核对）。

## 附件及核对

先读当前插件工具签名。若插件有指定父 item 的存储附件接口，直接使用。当前 `zotero_script(access: "privileged", effect: "write")` 可调用 `Zotero.Attachments.importFromFile({file: SOURCE, parentItemID: ITEM_ID})`，返回新 attachment；`ITEM_ID` 和 `SOURCE` 均来自本次已核对状态，不由用户填写。写入前快照父 item，创建后调用 `env.recordCreatedItem(attachment)`，并返回附件 ID、父 ID、存储类型及 `await attachment.getFilePathAsync()`。不要设置 `moveFile`，让校验脚本统一处理源文件清理。依据：[Zotero 附件源码](https://github.com/zotero/zotero/blob/main/chrome/content/zotero/xpcom/attachments.js)。

若该接口未暴露，可用 `library_import(kind: "files")` 后检查实际返回对象；只有它返回独立 attachment 时，再用 `library_update(kind: "parent")` 归入已确认的父 item。不假定 `activeItemId` 是附件导入目标，不能误建第二个文献 item。普通 `zotero_script(access: "library")` 未必暴露完整 `Zotero.Attachments` API，不能假定方法存在。

实际安装版本没有所需能力时，再用 Computer Use 操作“附件 → 添加 → 文件”和“显示文件”。首页可用插件 `paper_read(mode: "visual")` 渲染指定附件，或打开 Zotero 阅读器核对，不能用摘要/索引代替渲染验证。
