# 操作与恢复

全部 Python 命令使用 `uv run python <skill-dir>/scripts/ddict.py`。需要 Python 3.11+、Git；GitHub 私有性核验需要已有登录的 `gh`。没有第三方 Python 依赖。先看总 `--help`，再看所用子命令帮助。

## 本地文件与确认

主词库默认 `~/.config/dictation-dictionary/vocabulary.json`；运行目录和备份默认 `~/.local/state/dictation-dictionary/{runs,backups,receipts}/`。运行目录使用唯一名称，计划/凭据不能覆盖已有文件。候选和预览文件只保留词条元数据与必要的目标状态，不保存会议正文。

`library-plan --candidates <json> --out <plan>` 只生成预览；可用 `--desired <library>` 预览明确替换/恢复。`preview --plan <plan>` 展示包含 SHA-256 ID 的原始计划。只有收到用户对该具体变更的确认，才能把该 ID 传给 `apply --plan <plan> --approve <id>`。ID 是确认绑定，不是代替用户同意的口令。任何旧状态变化均重新预览、重新确认。

一个批次可以一次确认多个已列清的计划；执行时每个目标依次备份、检查、写入和核验。没有差异时跳过应用写入。备份与回执默认保留；不要自动清理。

## 按应用排除

每词的 `excluded_targets` 保存在主词库中，不另建第二份真相来源。`exclusions` 直接输出按应用分组的排除清单；`export --target plaud-cn` 等命令过滤排除项。`ui-plan --library <path>` 按清点的目标自动过滤，`codex-plan --library <path>` 自动过滤 Codex 排除项。优先用这两个词库入口；低层 `--words` 输入只接受已按目标过滤的词表，不能传入无 target 的全量导出。

用户只要求本次同步某端时，跳过其他端，不自行改变永久规则；明确要求记住不同步的词时，通过候选/desired 更新该字段，并在预览中展示。补来源不会清掉旧排除项。恢复同步须展示并确认移除对应排除目标，再重新生成该应用增补计划；排除规则不会删掉应用中原本已有的词。

## 私有 Git 词库

首次接入已有空的私有 GitHub 仓库用 `git-init --remote <url>`；只创建 Git 元数据，不建词库、不安装任何配置。需要新远端时，先向用户列清拟定的仓库名及 private 属性，经配置流程确认后使用现有 GitHub 工具创建空私有仓库，不添加 README 等文件。只允许跟踪 `vocabulary.json`。现有非空远端也可先初始化一个空本地目录，再通过以下计划取回词库，不能用 checkout/pull 隐式改写文件。

1. `git-inspect` 检查专用仓库、分支和无关文件。`git-fetch` 只取远端对象，输出远端词库，不修改本地 `vocabulary.json`。
   fetch/push 必须指向同一已核验地址，独立或多个 pushurl 会拒绝；计划绑定解析后的实际目标，写前及推送前再次检查配置。
2. 结合本地词库、已审核候选，先在运行目录构造完整 `desired.json`。若没有本地词库，用空结构作为起点。`git-plan --desired desired.json --out git-plan.json` 生成本地及远端差异；审查其最终 `after.library`（含排除项），并用该结果为本次获准应用生成计划。
3. 用户确认各计划后，运行 `git-apply --plan git-plan.json --approve <id>`；自动备份旧状态、写本地、只提交主词库、推送。远端更新也在同一批准计划内，不能先 `git pull`。
4. 并发冲突、远端变化、无关暂存或分支分歧会拒绝继续；重新生成预览。`push_failed` 表示可能已写本地/提交但未成功推送，检查结构化结果和备份；保留本地成果，不 reset、不强推。新一轮计划可重试。

同一词条在两端都改变时，完整预览中审核最终元数据与 enabled 值，不能只看新增词数。离线时报告 Git 未完成；用户明确选择仅本地更新后，才对单独的 `library-plan` 取得确认并执行。

两设备首次新增同一词却给出不同排除/启用策略时，拒绝自动合并；先审核远端策略，再统一为用户确认的选择并重新规划。不能用本机默认空排除列表清掉远端规则。

## Codex

`codex-plan --library <vocabulary.json> --out <plan>` 按 Codex 排除清单过滤后，默认增补到 `~/.codex/config.toml` 的 `desktop.dictationDictionary`。

**仅可替换该数组值区间，区间外字节完全不变。** 不通过整文件 TOML 格式化、不添加 MCP、不调整其他配置、不管理原有配置 Git 流程。脚本先校验完整文件版本，再保留数组区间外原字节；缺失键、歧义或不支持的语法直接停止。不要自己兜底整文件写回。

收到具体预览确认后用 `apply`。旧配置以受限权限备份到本机状态目录，读回验证该数组和其他字节；报告“配置已写入”，热加载及后续听写效果需要实际使用验证。

恢复使用 `restore-codex-plan --backup <old.toml> --out <new-plan>`，展示新增/删除，重新确认后 `apply`。只从旧备份取词典值；备份之后改变的模型、主题、MCP 等任何其他内容仍保持当前值，**禁止把完整备份复制回 config.toml**。

主词库恢复把备份作为 `library-plan --desired` 输入（或在 Git 流程中审核为 desired；默认 Git 保留条目，移除的词用 enabled:false），同样先预览与确认，再备份当前状态。首次创建的“不存在”备份标记不当作词库，恢复到不存在须单独展示删除计划并确认。

GUI 操作及恢复见 [ui-sync.md](ui-sync.md)。出现部分成功时分目标列出实际成功、失败及未执行项，不自动回滚。
