# Dictation Dictionary Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 构建可反复调用的听写词库 Skill，可靠完成候选审核、主词库维护、三端同步及备份。

**Architecture:** Python CLI 负责词库、差异、审批绑定、备份、Codex 定点编辑和 Git 操作。GUI 适配通过正式浏览器/桌面工具执行，以脚本生成的已确认清单和备份凭据为入口，读回核验后记录结果。语义纠错由 Agent 判断，固定数据操作使用代码。

**Tech Stack:** Python 3.11+ 标准库，`uv` 运行；Git；可用的 CUA/Playwright；无 Node 依赖的 JavaScript UI 辅助函数，使用 `bun test` 验证。

**Spec:** `docs/superpowers/specs/2026-10-23-dictation-dictionary-design.md`

## Global Constraints

- 主词库默认 `~/.config/dictation-dictionary/vocabulary.json`，本地状态默认 `~/.local/state/dictation-dictionary/`；只同步主词库。
- 用户确认每批具体变更后，每个目标先备份再写入；读取远端用于比较时不改写本地主词库。
- Codex 只替换 `desktop.dictationDictionary` 数组值，区间外字节完全不变；恢复同样只恢复词典值。
- 三端只接收已启用词条的正确写法；保留现有词，不自动删除，不将误写设为全局替换。
- 不另存会议正文；GUI 备份只存提取后的词表，不存带会议正文的整页 DOM/无障碍快照。
- 实际词库和配置不是测试写入对象；首批真实变更须再次展示、确认。配置中不添加 MCP 或其他设置。
- 保留现有 `AGENTS.md`、`README.md` 和 `reading-mentor/` 未提交工作；只提交本任务的增量。

## Review Focus

- 用户批准后源文件又改变：拒绝执行并要求新预览，归属 Task 2。
- TOML 字符串/注释含伪造表头或方括号：准确定位或安全拒绝，归属 Task 2。
- 备份后用户改过其他 Codex 设置：恢复词典时保留那些修改，归属 Task 2。
- 另一设备在预览后推送：拒绝强制覆盖并保留本地成果，归属 Task 3。
- GUI 列表未加载完整或包含背景正文/按钮文字：不得形成可写入凭据，归属 Task 4。

---

### Task 1: 主词库与可审阅差异

**Files:** `dictation-dictionary/scripts/vocabulary.py`、`dictation-dictionary/scripts/ddict.py`、`dictation-dictionary/tests/test_vocabulary.py`。

**Interfaces:** `validate_library(value: dict) -> dict`、`merge_entries(base: dict, incoming: list[dict]) -> dict`、`active_words(library: dict) -> list[str]`、`diff_words(before: list[str], after: list[str]) -> dict`。

词库结构固定为 `{"version": 1, "entries": [...]}`；词条字段为 `id`、`term`、`misheard_as`、`domains`、`sources`、`enabled`。来源只含链接与可选时间/定位；相同正确写法合并来源，不合并不同合法词。CLI 的 `--help` 作为命令参数的权威说明。

- [ ] 先写并运行失败用例：中文专名、含空格的短语、大小写、重复来源、辅助信息投递隔离、损坏输入。
  ```python
  assert active_words(sample_library) == ["项目甲", "Claude Code"]
  assert diff_words(["已有词"], ["已有词", "项目甲"])["added"] == ["项目甲"]
  assert merge_entries(merged, same_entries) == merged
  ```
- [ ] 实现校验、合并和只读 CLI：校验、导出词表、比较词表；拒绝控制字符和无效结构。
- [ ] 运行 `uv run --no-project python -m unittest discover -s dictation-dictionary/tests -p 'test_vocabulary.py' -v`，全部通过后提交该单元。

### Task 2: 确认、备份与 Codex 定点编辑

**Files:** `scripts/transactions.py`、`scripts/codex_dictionary.py`、`tests/test_transactions.py`、`tests/test_codex_dictionary.py`（均位于 Skill 内）。

**Interfaces:** `make_plan(target: str, before: dict, after: dict) -> dict`、`plan_id(plan: dict) -> str`、`require_approval(plan: dict, approval: str) -> None`、`backup_bytes(root: Path, target: str, data: bytes, mode: int) -> Path`、`read_codex(data: bytes) -> list[str]`、`patch_codex(data: bytes, words: list[str]) -> bytes`。

计划绑定目标、旧状态哈希和完整变更；CLI 无对应的明确批准参数即拒绝写入。批准参数仅在 Agent 收到用户对该计划的确认后传入。Codex 计划不输出完整配置内容；执行时重新读文件、定点替换、校验 TOML 及唯一键差异。定位不可靠时拒绝，不采用整文件序列化兜底。

- [ ] 先写并运行失败用例：无批准、计划被改、源文件过期、备份失败、重复运行、原文件缺失。
- [ ] 为 TOML 假表头、字符串内 `]`、注释、多行数组、CRLF、无效类型及不支持的安全定位形式编写用例。
  ```python
  assert before[:start] == after[:start]
  assert before[end:] == after[new_end:]
  assert parsed_after["desktop"]["dictationDictionary"] == approved_words
  assert restored["other_setting"] == changed_after_backup
  ```
- [ ] 实现私有本地状态目录、不可覆盖的备份、写前复查、同目录原子写入和权限保留；恢复走新的变更计划，只恢复词典值。
- [ ] 将主词库创建/更新也接入同一确认和备份流程；已有文件不变化时不重写。
- [ ] 运行该单元测试及 Task 1 测试；全部通过后提交。

### Task 3: 主词库 Git 同步

**Files:** `scripts/git_store.py`、`tests/test_git_store.py`，扩展 `scripts/ddict.py`。

**Interfaces:** `inspect_store(repo: Path) -> dict`、`fetch_remote_library(repo: Path) -> dict`、`plan_store_update(repo: Path, desired: dict) -> dict`、`apply_store_update(plan: dict, approval: str, state: Path) -> dict`。

使用 Git 子进程参数数组。先 fetch 并读取远端对象生成预览；用户确认并备份后，才允许更新本地词库、提交和推送。只暂存主词库；检查已暂存文件、工作区状态和远端版本；并发或不相关文件变化时拒绝覆盖。不执行强制推送。首次私有仓库初始化由明确配置流程完成，不将 Skill 或备份塞入该仓库。

- [ ] 用临时裸仓库和两个克隆先写失败用例：fetch 不改词库、批准后快进/提交/推送、离线、无远端、并发推送、意外暂存文件。
  ```python
  assert local_library.read_bytes() == before_fetch
  assert remote_library_after_approved_push == desired_library
  assert competing_remote_commit_survives_rejected_push
  ```
- [ ] 实现初始化/接入检查、远端只读比较和已确认更新；失败返回分阶段结果，保留备份及本地成果。
- [ ] 运行前三个单元的测试；全部通过后提交。

### Task 4: GUI 同步的执行与核验

**Files:** `scripts/ui_helpers.js`、`references/ui-sync.md`、`tests/ui_helpers.test.js`，扩展 Python CLI 的 GUI 凭据和核验命令。

**Interfaces:** UI 辅助函数接收已经取得的原生 app/浏览器 tab 句柄和已批准词表，不自行登录、安装或修改配置。CLI 接收 `{"target": "typeless|plaud-cn", "words": [...], "complete": true, "evidence": {...}}` 格式的实时清点结果；校验与计划相同后保存旧词表，输出待执行清单。写入后以新清点结果核验全部已批准变化及现有词保留情况。

- [ ] 先用模拟 app/tab 测试无批准凭据、重复项、保存失败、列表截断及含背景正文的清点；不连接实际应用。
  ```javascript
  expect(incompleteInventory.canWrite).toBe(false);
  expect(actionsForExistingWord).toEqual([]);
  expect(verifiedWords).toContain("原有词");
  ```
- [ ] 实现按已确认清单循环新增及逐项读回的 UI 辅助函数；遇到不匹配或控件变化即停止，不继续猜测。
- [ ] 文档记录实机已核查路径：Typeless 无障碍控件的词典/新词；PLAUD 中国区登录网页中自定义术语 DOM。完整清点必须有数量或列表到底的证据；不足则只报告不可写入。
- [ ] CSV 格式未实测前使用已验证的单词输入方式，不凭猜测导入；CSV 后续验证也先取得实际变更确认。
- [ ] 运行 `bun test dictation-dictionary/tests/ui_helpers.test.js` 及 Python GUI 凭据测试；通过后提交。

### Task 5: Skill 包装、行为验证与交付

**Files:** `SKILL.md`、`agents/openai.yaml`、`references/schema.md`（均位于 Skill 内），根 `README.md`。

**Interfaces:** Skill 调用 CLI 的帮助中定义的命令；主流程为读取证据 → 提出候选与各端具体差异 → 用户确认 → 备份 → 执行 → 读回报告。文档指向所需模式的具体参考文件。

- [ ] 在临时环境做无 Skill 的基线压力场景：恢复旧词典时，当前配置的其他设置已更新；记录 Agent 的可观察行为。
- [ ] 编写简短 Skill、元数据和 schema，覆盖单条纠错/成对材料/仅同步/恢复；实际词库变更逐批确认，失败明确报告。
- [ ] 独立 Agent 在临时样例中用 Skill 完成恢复、远端差异和不完整 GUI 清点场景；只据观察到的失败补充说明。
- [ ] 运行完整 Python 测试、Bun 测试和 bundled skill-creator 校验；独立审阅整个改动。
- [ ] 读取用户示例，形成首批真实候选及三端差异预览；停在实际词库写入之前等待该批确认。
- [ ] README 仅加入新 Skill 行，选择性暂存本任务改动；提交并推送开发成果，保留已有未提交工作。

## 自检

- 设计中每项范围均对应上述任务；真实词库初始化与实际写入均受确认约束。
- 方案只同步主词库；备份和运行记录保留本机；Codex 恢复也遵守区间外字节不变。
- GUI 适配为 Agent 使用正式工具执行的可复用流程，不声称存在未验证的私有词库 API。
- 所有测试在临时文件/仓库或模拟 UI 上运行；真实听写准确率及热加载行为需要后续实测，不以单元测试代替。
