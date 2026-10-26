# 主词库格式

默认文件 `~/.config/dictation-dictionary/vocabulary.json`，其父目录是独立私有 Git 仓库。Skill、备份和运行文件不放进去。不设置额外的设备配置文件；其他路径用 CLI 参数指定。

```json
{
  "version": 1,
  "entries": [
    {
      "id": "stable-id",
      "term": "示例机构",
      "misheard_as": ["示例机购"],
      "domains": ["行业示例"],
      "sources": [{"url": "https://example.com/meeting", "locator": "00:12:30", "timestamp": "2026-10-26"}],
      "enabled": true
    }
  ]
}
```

- 完整条目字段固定为上述六个；`sources` 每项只允许 `url` 和可选的 `locator`、`timestamp`。不保存会议正文、附件、凭据或整段上下文。
- 候选 JSON 是条目数组；只需 `term`，其他字段可省略，脚本生成稳定 ID、空列表和 `enabled:true`。候选须在用户确认后才成为正式词库内容。
- 正确写法按精确字符串去重，保留大小写及短语空格；“同音”“相似”不构成合并依据。同一 `term` 合并误写、领域和来源，保留既有 ID。不同词条不得复用 ID。
- 只分发 `enabled:true` 的 `term`。例如 `misheard_as` 中的“示例机购”不会进入任何应用词典，也不是自动替换规则。
- 默认只增补；停用使用 `enabled:false`。应用端已有词保留，停用主词条不会自动删除应用词。
- `validate` 校验结构；`export` 输出正确词 JSON 数组；CSV 只是通用单列导出，尚未验证应用导入格式。

GUI 清点必须是以下形状；不能附加 `dom`、`body`、`screenshot` 等字段：

```json
{
  "target": "plaud-cn",
  "words": ["示例机构"],
  "complete": true,
  "evidence": {
    "kind": "count",
    "count": 1,
    "identity": "观察到的账号显示名",
    "observed_at": "2026-10-26T00:00:00+00:00",
    "all_terms": true,
    "enabled": true
  }
}
```

Typeless 可使用 `kind:"end", at_end:true` 替代 `kind/count`，须先真实核对“所有”、空搜索、列表到底。词表不得含重复项；数量不符、未启用或清点不完整时拒绝备份执行凭据。
