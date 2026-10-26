# GUI 词典同步

使用运行环境提供的浏览器/桌面工具。浏览器能用 Playwright 时优先使用；Typeless 的原生窗口使用无障碍控件。先读当前工具文档。不要调用网页私有 API、读取后台状态、自动安装 MCP 或改写应用配置来替代界面操作。

`scripts/ui_helpers.js` 定义无依赖的 `createDictationUI()`。将文件原样放入电脑操作 REPL，取得 `const ui = createDictationUI()`；传入已绑定的 tab/app 句柄。只调用当前工具支持的方法；接口不兼容时先适配并验证，不能声称完成。

## 清点与完整性

- PLAUD **中国区**：登录 `https://web.plaud.cn/` → 账号菜单 → 设置 → 自定义术语。核对账号、开关已启用。词条容器 `.words-item-title`；标题 `.vocabulary-title` 的 `常用术语 (N)` 必须与提取数量相等。`ui.readPlaudInventory(tab, observedAccount)` 返回清点结果。
- Typeless：打开词典 → 所有，搜索为空。滚动检查实际列表已加载到底；数据多时收集各屏并去重，不能把当前可见部分当完整清单。原生读取器只提取“搜索”之后词条容器中的文本；`ui.readTypelessInventory(app, observedAccount, {allTerms:true,endObserved:true})` 的两个布尔值必须由实际界面证据支持。账号应来自当前账号界面，不能随意填占位符。
- 界面首次打开可能短暂显示空表。确认加载完成后清点。没有数量/到底证据时 `complete:false`，停止写入。
- 清点只保存结构化词表和证据；不要落盘全页 DOM、无障碍快照、会议正文或截图。账号标识使用最小必要显示名，不保存凭据。

以上路径与 DOM 在 2026-10-26 实机只读核查过；当时 Typeless v2.8.3 读取 14 词、PLAUD 读取 19 词。实际新增尚待用户批准后验证，不能把模拟测试说成实机写入成功。

## 预览 → 批准 → 备份 → 写入 → 核验

所有路径放在私有本地状态目录的一次运行子目录，例如 `$HOME/.local/state/dictation-dictionary/runs/<unique>/`。命令入口记为 `uv run python <skill-dir>/scripts/ddict.py`；参数以 `--help` 为准。

1. 把完整清点存为 `before.json`；把主词库 `export` 的正确词数组存为 `words.json`。
2. `ui-plan --inventory before.json --words words.json --out plan.json`。向用户展示目标账号、逐项新增/删除和保留数；当前 GUI 适配仅新增，删除数应为零。收到该具体计划的确认后才继续。
3. 重新实时清点为 `current.json`，运行 `ui-prepare --plan plan.json --approve <id> --current current.json --out ready.json`。旧词表备份成功且哈希核验后才输出 `status:ready`。
4. 执行 `ui-check-ready --ready ready.json`，核对原批准计划、备份文件及 SHA-256 后，从真实文件读取凭据，不要手造或改动。调用 `ui.addPlaudWords(tab, ready, observedAccount)` 或 `ui.addTypelessWords(app, ready, observedAccount, proof)`。辅助函数用 Web Crypto 在首次写入前重算原计划 ID，校验操作内容；运行环境不支持时停止。它们逐词新增，逐项读回，旧词不会删除。
5. 将写入后重新清点结果存为 `after.json`，运行 `ui-verify --ready ready.json --current after.json`。只有完整词集与批准的结果相等且备份仍有效，才记录已验证成功。

固定控件：PLAUD 添加 `setting-glossary-add-button` → 占位文本 `请输入术语` → `dialog-confirm-button`（保存）；Typeless 新词 → 添加新词 → 添加词汇。原生索引每次操作前重新获取，不能复用上一次的编号。PLAUD 用测试 ID 避免“保存”恰好也是已有词条时误点。CSV 格式尚未实测，`export --format csv` 仅为通用单列导出，不直接导入应用。

## 中断与恢复

控件变化、列表截断、保存失败、词集或账号变化时立即停止。报告实际已新增的词和待处理的词，保留备份；重新清点并产生新的差异，重新确认后继续。不要自动回滚已成功词条，也不要重用旧计划。

GUI 恢复须读取指定备份与当前完整词表，展示逐项增删并再次确认、再次备份。辅助函数只支持新增；删除/编辑需要当场检查真实控件逐项执行，再用完整清点核验。未核查删除路径时只交付恢复预览，不能声称完成恢复。Codex 恢复使用专门的 `restore-codex-plan`，见 [操作说明](operations.md)。
