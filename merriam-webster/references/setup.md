# 凭据与运行

需要 [Collegiate Thesaurus](https://dictionaryapi.com/products/api-collegiate-thesaurus) 对应的 Key；Collegiate Dictionary 是另一个产品，其 Key 不能代替 Thesaurus Key。

## macOS：推荐钥匙串

**存储位置与传递方式分开考虑**：钥匙串用于长期加密保存，环境变量用于临时覆盖或由运行器注入。此脚本支持两者；无需把 Key 明文写入 `.zshrc`、Skill 或仓库。

用户在本机终端执行：

```bash
security add-generic-password -U -a "$USER" -s merriam-webster-thesaurus -w
```

`-w` 必须位于最后；`security` 会提示输入密码，此时粘贴 **Thesaurus API Key**。不要将 Key 接在命令后面，避免进入 shell 历史和进程参数。`-U` 允许更新同名项。该项保存在默认钥匙串，服务名为 `merriam-webster-thesaurus`，账户名为当前用户；不需要向聊天发送 Key。

脚本通过系统 `security` 工具读取此指定项；钥匙串锁定或访问控制要求确认时，由 macOS 弹窗处理。脚本不调整钥匙串访问权限。

配置后，将 `<skill-dir>` 换成 Skill 的绝对路径：

```bash
uv run "<skill-dir>/scripts/lookup.py" --check-key
uv run "<skill-dir>/scripts/lookup.py" "practical"
```

第一条只显示是否找到 Key 及其来源，不显示 Key、不请求 API；只有第二条查询成功才能证明 Key 有效且有正确产品权限。

## 环境变量接口

固定变量名：`MERRIAM_WEBSTER_THESAURUS_API_KEY`。若该变量非空，优先于钥匙串。CI、容器或其他系统可由自己的 secret manager 注入。

若使用 `.env` 文件，将其放在仓库外并设为仅本人可读（`chmod 600`），通过 `uv run --env-file /absolute/path/to/credentials.env ...` 显式注入。脚本不会自动搜索或读取任意 `.env`；只在 `.zshrc` 中设置变量，也不能保证其他启动器所启动的进程能继承。

## API 与错误

- 仅调用 `https://www.dictionaryapi.com/api/v3/references/thesaurus/json/{word}?key=...`；公开的原站链接不含 Key。请求失败时不输出请求 URL、原始错误正文或 Key。
- 当前官方非商业免费条件包括每日每个参考产品最多 1,000 次查询、最多使用两个参考产品；以 [官方说明](https://dictionaryapi.com/) 为准。每个英文候选分别占一次请求，不批量穷举、不自动重试额度错误。
- 字段语义以 [官方 JSON 文档](https://dictionaryapi.com/products/json) 第 3 节为准：`syn_list` 同义词，`sim_list` 同义与近义词，`phrase_list` 同义短语，`rel_list` 相关词，`near_list` 近反义词，`ant_list` 反义词，`opp_list` 反义与近反义词。
- 脚本的 PEP 723 元数据声明无第三方依赖；`uv run` 会隔离运行，不同步调用方项目。若沙箱仅因 uv 默认缓存目录不可写而失败，可加 `--cache-dir "${TMPDIR:-/tmp}/merriam-webster-uv-cache"`。
