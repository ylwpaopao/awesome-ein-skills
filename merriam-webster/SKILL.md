---
name: merriam-webster
description: 当用户想查 Merriam-Webster／韦氏词典、Thesaurus、英文同义词和近义词，或用中文词、概念描述寻找合适的英文表达时使用。
---

# Merriam-Webster 同义与近义词

直接调用官方 Collegiate Thesaurus API。默认提供同义词、近义词和同义短语；按词性、义项及词组的小分组整理，保留词典例句和原站链接。

## 选定英文词目

- **英文单词或短语**：直接查询，结合上下文选择对应义项。
- **中文词**：先翻译成最符合语境的英文候选；多义时选 1–3 个，并简短说明对应关系。
- **描述／想不起来的词**：先从描述提炼意思、词性和语境，提出 1–3 个英文候选，再分别查词核验。只有缺失的语境会明显改变选词时才追问。

翻译与候选选择由 Agent 完成；MW API 本身不提供中文翻译或按描述反向找词。候选是否合适，要对照 API 返回的具体义项；未被词典查询证实的猜词单独说明。

## 调用脚本

将 `<skill-dir>` 替换为本文件所在目录的绝对路径；在任意工作目录运行：

```bash
uv run "<skill-dir>/scripts/lookup.py" "practical" --format json
```

脚本仅使用 Python 标准库。默认从环境变量 `MERRIAM_WEBSTER_THESAURUS_API_KEY` 读取 Key；未设置时，在 macOS 中读取当前用户钥匙串的 `merriam-webster-thesaurus` 项。首次配置或提示缺少 Key 时，读取 [配置说明](references/setup.md)；Key 由用户在本机输入。

- 需要反义词、近反义词或更广的相关词时，加 `--all-relations`。
- 直接查看带链接的排版结果，省略 `--format json`；查看未转换的 API 字段用 `--format raw`。
- `status=suggestions` 仅表示拼写建议，确认候选后另查；`not_found` 表示没有词条。API 请求失败时如实说明，不能用模型生成的词表冒充查询结果。

## 整理答复

1. 中文或描述输入，先用一行给出“原意 → 英文候选”；语义选择、中文释义和用法建议属于 Agent 的解释。
2. 按**词目 → 词性 → 具体义项 → 词组小分组**展示。语境明确时优先相关义项；仅展示部分结果时标注“精选／主要义项”，脚本返回的完整分组保持可用。
3. 每个义项依次给出简短中文释义、带原站链接的同义／近义词、该义项的词典原例及必要的中文翻译。保留 formal、slang、British 等语域／地域标签；保留例句的原作者署名（若有）。
4. 使用返回的 `thesaurus_url`、`dictionary_url` 和 `source_url` 链接到原站。义项共用词目页链接；中文翻译、自拟示例和选词建议与词典原文区分。API 无例句时说明“该义项未提供例句”。

`synonyms`、`similar_words` 分别对应 `syn_list`、`sim_list`。`related_words` 是相关词；`near_antonyms` 是近反义词，均不混进默认近义词列表。使用 `senses` 内的字段及 `divided_sense`，保持数组分组；不要把 `meta.syns` 展平，或将整个词条的 `short_definitions` 与词表按位置强行配对。

## 完成标准

实际查询过所选英文词目；结果符合输入语境；每组词与所属义项、例句保持对应；原站链接可见；缺词、缺例句或请求失败都有明确交代。
