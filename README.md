# awesome-ein-skills

保存我开发的 AI Agent Skills。

## Skills

| Skill | 用途 |
| --- | --- |
| [merriam-webster](merriam-webster/SKILL.md) | 直接调用韦氏官方 Thesaurus API，支持英文、中文词和描述找词，按义项保留同义／近义词分组、例句与原站链接。 |
| [init-agents](init-agents/SKILL.md) | 初始化 Codex、Claude Code 项目配置和 Git 仓库，保留已有文件。支持 macOS 和 Linux。 |
| [reading-mentor](reading-mentor/SKILL.md) | 阅读文档时，从批量问题推断知识缺口，围绕主线串起背景、术语与解答。支持链接、PDF 和原文。 |
| [doi-to-zotero](doi-to-zotero/SKILL.md) | 只需 DOI 或文献链接，优先用 Zotero 插件与 Playwright 收录全文；默认存入 AssetPricing，支持指定其他分类，核对附件后清理下载文件。 |

## 使用

将所需 Skill 的完整目录复制到目标项目的 `.agents/skills/`（Codex）或 `.claude/skills/`（Claude Code）中，按该目录下的 `SKILL.md` 使用。

每个 Skill 独立存放，包含 `SKILL.md` 及运行所需的脚本、资源和元数据。本仓库的本地开发配置不纳入版本控制。
