---
name: init-agents
description: 显式调用命令，初始化 Codex、Claude Code 项目脚手架和 Git 仓库。
disable-model-invocation: true
---

# init-agents

仅在用户显式调用时执行：Codex 使用 `$init-agents` 或 Skill 选择器，Claude Code 使用 `/init-agents`。不要因语义相似自动执行。

运行本 Skill 目录中的脚本，将用户指定的项目路径作为单个参数；未指定时使用当前工作目录。替换下方路径占位符，保留引号：

```sh
bash "<skill目录>/scripts/init-agents.sh" "<项目目录>"
```

支持 macOS/Linux；Windows 暂不支持。仅初始化项目，保留已有文件；具体生成项见脚本 `--help`。按退出状态和输出报告结果；出错时不要绕过检查强行覆盖。
