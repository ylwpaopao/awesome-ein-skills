---
name: dictation-dictionary
description: Use when the user reports dictation errors in names or specialist terms, provides corrected notes and an original transcript, or asks to maintain, sync, or restore vocabulary for Typeless, PLAUD China (plaud.cn), or ChatGPT/Codex desktop dictation.
---

# 听写词库

维护独立主词库，各应用只接收允许同步的正确词或短语。固定数据操作使用本 Skill 脚本；语义纠错由 Agent 根据原文判断。

## 入口与资料

命令统一为 `uv run python <skill-dir>/scripts/ddict.py`；先读 `--help`，参数以子命令帮助为准。

| 请求 | 先读 |
| --- | --- |
| 单条纠错、成对纪要/转写 | [词库结构](references/schema.md) |
| 首次接入、Git 同步、Codex、恢复 | [操作说明](references/operations.md) |
| Typeless、PLAUD 中国区同步 | [界面适配](references/ui-sync.md) |

默认主词库 `~/.config/dictation-dictionary/vocabulary.json`，父目录是独立私有 GitHub 仓库的本地副本。只同步该文件；Skill 与本机状态 `~/.local/state/dictation-dictionary/` 分离，不另设设备配置文件。其他路径由参数指定。

## 执行

1. **读取证据。** 读取用户提供的链接或材料；无法访问时明确缺失，不猜内容。PLAUD 区分 AI 总结、优化转写与“原始版本”，纠错以原始转写为基准。会议正文不另存；候选只存词条元数据与来源定位。
2. **提出候选。** 展示“原转写 → 正确词、必要上下文、来源定位、置信度/待核实”。人工纪要中的改写、补充、删节和事实修正不直接当成识别错误。合法同音词不做全局替换；低把握人名待用户确认。仅同步时跳过此步。
3. **生成完整预览。** 获取主词库远端对象并比较，不能先 pull/checkout 改词库。用户指定“某词不同步到某应用”时，记录该词的 `excluded_targets`；同词补来源时保留该字段，明确要求恢复同步时才移除对应目标。用 `exclusions` 查看清单。只读取本次获准目标的完整词表，优先用 `ui-plan --library` / `codex-plan --library` 自动按目标过滤，导出时用 `export --target`；全量导出不能作为应用投递词表。分别列出主词库、获准应用的具体变化与被排除的目标，注明账号。未完整清点的目标不可执行。
4. **等待具体确认。** 每次任何词库实际变化前，用户先看到该批目标及完整变更并确认；一次可批准明确列出的整批。确认词条拼写、批准开发 Skill、过去的同步授权均不代替本批写入确认。仅收到该预览确认后，才给脚本传入其 `--approve <plan-id>`。
5. **备份并执行。** 写前重新检查状态与批准计划一致；每个变化目标先保存并核验旧状态备份，再写入。无变化跳过；备份失败、状态变化或清点不足则停止该目标。默认只增补，不删应用现有词；误写、领域、来源不投递到应用。GUI 执行必须使用 `ui-prepare` 产生的真实备份凭据。
6. **读回报告。** 逐目标验证并报告成功、失败、未执行与备份路径；部分失败保留成果，下次重新预览。导出文件和 `status:ready` 不代表同步完成。主词库只提交并推送已批准词库变化，不强推。实际听写准确率与 Codex 热加载效果需使用后验证。

**Codex 硬边界：** `~/.codex/config.toml` 只允许替换 `desktop.dictationDictionary` 数组值，区间外字节全部保持。使用脚本定点编辑；缺失或无法安全定位就停止。恢复也只取旧词典值，不能整份配置覆盖，不能安装 MCP 或修改其他设置。

首次导入应用已有词、从远端更新本地词库、停用/删除、恢复备份，也执行同一套预览、确认和备份流程。真实词库不作为测试写入对象；没有对应界面工具时报告该端未完成。

排除清单是主词库的一部分，随私有仓库跨设备同步；它控制今后的增补，不自动删除应用里已有的词。一次仅执行某应用不等于永久排除其他应用；用户要求“记住不同步”时才持久记录。改变排除规则也先展示并确认。
