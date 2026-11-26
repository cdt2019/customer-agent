# 参与贡献

谢谢你愿意帮忙。提 Issue、修文档、修 bug、加功能都欢迎。

## 开始之前

- 先读 [README](README.md) 和 [CLAUDE.md](CLAUDE.md)：后者写了目录结构、常用命令和写代码的规矩，人和 AI 助手都照它来。
- 大改动（换选型、加新功能、改接口和表）请先开 Issue 讨论，最好按 `docs/07`–`docs/10` 的格式写一份简短方案：范围、做法、接口和表的改动、怎么验收、要定的问题。
- 发现安全问题请不要公开提 Issue，见 [SECURITY.md](SECURITY.md)。

## 开发环境

见 README 的「本地跑起来」。机器相关的设置（缓存目录、代理、模型放哪）放在你自己的 `server/.env`、`demo/.env` 或工具的用户配置里，不要写进仓库里的文件。

## 提交前检查

```bash
cd server && uv run pytest -q && uv run ruff check src tests lab
cd demo && uv run pytest -q
cd admin && pnpm typecheck
cd widget && pnpm typecheck
```

- 改了表：生成 Alembic 迁移（`uv run alembic revision --autogenerate -m "short_english_slug"`（说明会成为文件名，用英文小写加下划线）），和代码一起提交。
- 改了后台接口：重新导出 `admin/src/api/openapi.json` 并 `pnpm gen:api`。
- 改了对话、提示词或检索：跑一遍评测（`agent eval` / `agent chat-eval`），把前后分数写进 PR 描述；有意义的结果补进 `docs/05-实测记录.md`，写明硬件和条件。
- 改了聊天窗或模拟店铺：能跑的话跑一遍 `demo/e2e.py`（要真实模型密钥）。

## 写代码的规矩（摘要）

完整版见 [CLAUDE.md](CLAUDE.md)。

- 模块像积木：一个模块做一件事，靠组合实现功能，不在一个模块里堆开关。
- 高内聚、低耦合：`rag` 不知道有对话和接入方；具体接入方只在 `connectors`，具体渠道只在 `channels`。
- 不写兼容代码、不写胶水代码、不为以后提前加抽象；没用的代码在同一个改动里删掉。
- 能用标准库解决的不引入框架。
- 文档、注释、提交说明用中文。

## 提交 PR

- 一个 PR 做一件事，说明为什么改、怎么验证的。
- 提交说明写清楚改了什么（中文即可）。
- 不要提交 `.env`、密钥、模型文件、`var/` 下的运行时数据。

提交贡献即表示你同意按本仓库的 [MIT 许可证](LICENSE) 发布你的代码。
