# customer-agent · 协作规则（给 AI 助手和贡献者）

通用的「知识库 + AI 客服」服务。动手前先读 [技术方案](docs/02-技术方案.md)（§0 约束、§3 目录、§6 检索链路）和[路线图](docs/04-路线图.md)。文档、注释和提交说明用中文。

本机特有的环境和私有事项写在 `CLAUDE.local.md`（不进版本管理）。

## 原则

- **产品要通用，不依赖某台机器。** 功能、界面、默认值都不能依赖开发机：路径和密钥走环境变量（`server/.env.example`），某台机器的特殊情况只放它自己的 `server/.env`。
- **结论要有实测或出处，** 不凭印象。实测结果写进 `docs/05-实测记录.md`，写明硬件和条件；没测过的标「未测」。
- 大改动、换选型之前，先写方案（参考 `docs/07`–`docs/10` 的格式）。

## 写代码的规矩

1. **模块像积木，靠组合。** 每个模块做一件事，对外是一个小而明确的接口；功能靠把模块组合起来实现，不靠在一个模块里加开关和分支。
2. **高内聚、低耦合。** 一起变化的东西放一起；模块之间只通过接口说话，不伸手碰对方的内部。`rag` 不知道有对话和接入方；具体接入方只出现在 `connectors` 里，具体渠道只出现在 `channels` 里。
3. **不写兼容代码。** 换掉的接口、表、参数直接改掉，不留旧名字、旧路径、开关和迁移垫片。
4. **不写胶水代码。** 两个模块对不上时改接口让它们对上，不在中间加一层转换；不为「以后可能用到」提前加抽象层。
5. **没用的代码删掉。** 换掉的函数、文件、依赖、文档在同一个改动里删；不留注释掉的代码和没人调用的函数。
6. **保持简洁。** 能用标准库和几行代码解决的，不引入框架；不写只被调用一次的包装函数。

可替换的部件（向量模型、重排、向量库、解析器、模型供应商）各有一个接口和若干实现，这是设计里定好的替换点，不算提前抽象；除此之外不加。

## 目录

```
server/          Python 客服服务（uv 项目）
  src/customer_agent/
    rag/                检索链路的积木，一块一个文件：
                        parsers 解析 · sources 来源和清洗 · chunkers 切块 · embedders 向量模型 ·
                        stores 向量库 · ingest 导入 · retrieval 检索 · answer 回答 · metrics 分数
    db.py               数据表（改了表就生成迁移）
    llm.py              回答用的模型（兼容 OpenAI 接口，默认 DeepSeek）
    chat/               对话：agent 循环 · tools 四个工具 · handoff 转人工 · staff 人工接管 · copilot 起草回复 · images 买家发的图 · prompts 提示词 · guard 代码把关 · evaluate 对话层评测
    connectors/         接入方：base 接口 · http_shop 按 §5.2 调店铺
    channels/           渠道：push 把客服的话送出去 · telegram 和 Telegram 说话 · telegram_bot 把私聊接到对话上（docs/10）
    evals.py            评测
    model_files.py      下载模型并核对校验值（agent fetch-model）
    clock.py            「今天」按业务时区算；库里的时间都带时区
    kb_sources.py       知识库的资料从哪来：文件夹，或接入方的帮助文章
    service.py          总开关和限额（存在库里，后台可改）
    retention.py        到期清理：聊天记录和检索过程留 90 天
    runtime.py          按配置造出模型、向量库这些重的部件，命令行和接口共用
    api/                管理后台的接口（FastAPI），一页一个模块
    cli.py              命令行：只负责把积木拼起来
    settings.py         配置，全部来自环境变量
  migrations/           Alembic 迁移
  tests/                单元测试，加一组内存库上的流水线测试
  lab/                  实测脚本：量速度、试解析器、评草稿，结果记在 docs/05
admin/           管理后台（Vite + TanStack Router/Query + shadcn 的 Base UI 版 + Tailwind 4）
  src/routes/           页面，一页一个文件
  src/features/<页面>/  这一页自己的组件和数据整理
  src/components/ui/    shadcn 生成的基础组件（用 CLI 加，不手写）
  src/components/shell/ 外框、左侧菜单和几页共用的小部件
  src/styles/tokens.css 设计令牌，颜色只在这里定义
  src/api/              从接口定义生成的类型和客户端
widget/          聊天窗（React + Tailwind 4，打成一个 widget.js，挂在 Shadow DOM 里）
demo/            模拟店铺「示例商店」（单独的 uv 项目，代替真实接入方）
  demo_shop/            店铺接口 shop_api · 网页接口 site · 对话转发 relay · 访客令牌 tokens · 数据 store
  web/                  模拟店铺网页（不用框架，嵌聊天窗）
  data/                 样例数据：shop.json 商品和订单，posts/ 帮助文章
  e2e.py                端到端检查，用真实模型
deploy/          部署：compose.yaml、Caddyfile、.env.example（说明见 docs/06）
docs/            产品、技术方案、实测记录、各功能方案和效果图
evals/           评测题，一个知识库一个目录：evals/<知识库名>/questions.jsonl
var/             运行时数据（不进版本管理）：模型、Qdrant 存储、上传文件、图片
```

## 常用命令（在 `server/` 下）

| 做什么 | 命令 |
|---|---|
| 测试 | `uv run pytest -q` |
| 改了表 | `uv run alembic revision --autogenerate -m "short_english_slug"`（说明会成为文件名，用英文小写加下划线），再 `uv run alembic upgrade head` |
| 下载模型 | `uv run agent fetch-model BAAI/bge-m3`（下载并核对校验值） |
| 同步文档 | `uv run agent sync <知识库> <文件夹或 shop>`（shop：从接入方的帮助文章接口同步，要先起模拟店铺） |
| 建索引或更新 | `uv run agent index <知识库> <索引名> [--chunker --size --overlap --model]` |
| 提问 | `uv run agent ask <知识库> <索引名> "问题" [--no-answer]` |
| 评测 | `uv run agent eval <知识库> <索引名> ../evals/shop-help/questions.jsonl [--answers retrieve\|full]` |
| 对话层评测 | 先起模拟店铺，`uv run agent chat-eval <知识库> <索引名> ../evals/shop-help/questions.jsonl --visitor-token <令牌> [--only handoff,trap] [--model 换答题模型，打分不变]`；令牌在 `demo/` 下用 `uv run demo-shop token member-a` 签 |
| 手动清理到期记录 | `uv run agent cleanup [--days 90]`（服务自己每天清一次） |
| 启动服务 | `uv run uvicorn customer_agent.api:app --port 8000`；模拟店铺在 `demo/` 下 `uv run demo-shop serve --port 8100`；后台在 `admin/` 下 `pnpm dev` |
| 部署 | 见 [docs/06-部署.md](docs/06-部署.md)，在 `deploy/` 下 `docker compose` |
| 聊天窗 | `cd widget && pnpm build`，模拟店铺直接用 `widget/dist/widget.js` |
| 模拟店铺测试 | `cd demo && uv run pytest -q`；端到端 `uv run python e2e.py`（要先起 Qdrant、服务和模拟店铺；人工接管那段要设 `ADMIN_PASSWORD`） |
| 改了接口 | 在 `server/` 导出接口定义到 `admin/src/api/openapi.json`（见 docs/05 §13），再 `cd admin && pnpm gen:api` |
| 加基础组件 | `cd admin && pnpm dlx shadcn@4.23.0 add <组件名>`，加完把 `from "cn"` 改成 `from "@/lib/utils"` |
| 前端检查 | `cd admin && pnpm typecheck`，`cd widget && pnpm typecheck` |
