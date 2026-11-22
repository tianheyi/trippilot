# TripPilot

面向**中国境内旅行**场景的 AI 旅行规划助手。

用户用自然语言描述需求，例如：

> 我准备周五晚上从深圳出发，在长沙玩三天，预算 2000 元，喜欢美食和人文景点，不想每天安排得太满。

TripPilot 的目标是把这个句子变成一份**结构化、可解释、可修改**的行程。

---

## 当前状态

> **本仓库目前是最小工程骨架，不是可用的旅行规划器。**

已经能跑通的是**工程底座**：服务能启动、探针可信、日志可追踪、错误有统一形状、质量门禁可执行。
旅行规划本身（LLM、工作流、外部数据）**尚未实现**。

### 已实现 ✅

| 能力 | 位置 |
| --- | --- |
| FastAPI 应用工厂 + 生命周期管理 | `src/trippilot/main.py` |
| `GET /health` 存活探针 | `src/trippilot/api/health.py` |
| `GET /ready` 就绪探针（如实上报依赖状态） | 同上 |
| 统一响应信封 + 异常处理 | `src/trippilot/schemas/common.py`、`api/errors.py` |
| 结构化日志，带 traceId（JSON / console 双格式） | `src/trippilot/core/logging.py` |
| TraceId 中间件（复用入站 header，回写响应 header） | `src/trippilot/api/middleware.py` |
| 配置加载 + 启动期快速失败 | `src/trippilot/core/config.py` |
| 旅行需求领域模型与校验规则 | `src/trippilot/domain/models.py` |
| 测试 / Ruff / mypy / CI / Docker Compose | 仓库根目录与 `.github/` |

### 未实现 ❌

- LLM 槽位提取、意图识别、多轮合并
- 澄清追问流程
- LangGraph 工作流与 Checkpoint
- 景点 / 天气 / 交通等任何外部 Provider
- 行程生成、保存、版本管理
- 数据库读写与 Alembic 迁移
- 前端（未来为 React + TypeScript，本阶段 API 已按此预留契约）

`services/`、`agent/`、`tools/`、`infrastructure/` 与 `domain/ports/` 目前**只有 docstring**，说明该层将来承载什么、受什么约束。这不是空模块堆砌，而是把边界先钉在代码里。逐项目标 vs 现状对照见 `AGENTS.md` §13。

---

## 技术栈

| 类别 | 选型 | 当前锁定版本 |
| --- | --- | --- |
| 语言 | Python | 3.13（`requires-python >= 3.12`） |
| Web 框架 | FastAPI | 0.143.0 |
| ASGI 服务器 | Uvicorn | 0.54.0 |
| 数据校验 | Pydantic v2 | 2.14.0 |
| 配置 | pydantic-settings | 2.15.0 |
| Agent 工作流 | LangGraph | 1.2.14（已安装，尚未使用） |
| ORM | SQLAlchemy 2.x (async) | 2.1.4（已安装，尚未使用） |
| 迁移 | Alembic | 1.20.0（已安装，尚未使用） |
| 数据库 | PostgreSQL | 17（Compose 提供） |
| 测试 | pytest / pytest-asyncio / HTTPX | 9.1.1 / 1.4.0 / 0.28.1 |
| 检查与格式化 | Ruff | 0.17.0 |
| 类型检查 | mypy (strict) | 2.4.0 |
| 依赖管理 | uv | 锁文件 `uv.lock` |

依赖全部为稳定版，由 `uv.lock` 固定；未使用任何预发布版本。

---

## 架构概览

**依赖方向**（完整规则见 `AGENTS.md` 第 5 节）：

```
        api  ── 接口层：路由、中间件、异常映射、依赖
         |
         v
      services ────────> domain/ports（Repository 等抽象）
         |
         v
       agent ── LangGraph 编排
         |
         v
       tools ── Agent 工具
         |
         v
  infrastructure ── LLM / 持久化 / 搜索 / 可观测性适配器

  domain <───────── infrastructure 实现 domain 定义的接口

  main.py：创建具体实现并组装依赖
```

**最容易违反的三条**：

1. `tools/` 不得反向调用 `agent/`，也不得依赖 `api/`。
2. `domain/` 中出现 `from fastapi import ...` / `sqlalchemy` / `langgraph` 视为违规——这是保证业务规则可独立测试的关键。
3. Repository 接口由 `domain/ports/` 定义，具体实现由 `infrastructure/persistence/` 提供，内层不得导入具体实现。

当前只有 `api` / `core` / `domain` / `schemas` 有实际代码；`services` / `agent` / `tools` / `infrastructure` 是占位。

详细说明见 [`docs/architecture/overview.md`](docs/architecture/overview.md)，工程约束见 [`AGENTS.md`](AGENTS.md)。

---

## 环境要求

- Python **3.12+**
- [uv](https://docs.astral.sh/uv/)（依赖管理与运行）
- Docker + Docker Compose（可选，仅用于容器化运行与本地 PostgreSQL）
- GNU Make（可选，所有命令都有等价的 `uv` 原生写法）

Linux / macOS 均可。Windows 建议在 WSL2 下开发。

---

## 快速开始

### 1. 安装依赖

```bash
git clone <repo-url> trippilot
cd trippilot

uv sync --all-groups        # 等价于 make install
```

### 2. 配置环境变量

```bash
cp .env.example .env
```

`.env` 已被 `.gitignore` 忽略。**默认值即可启动**，无需修改任何内容——数据库 DSN 在本阶段是可选的。

### 3. 启动服务

```bash
make run-reload             # 等价于 uv run uvicorn trippilot.main:app --reload
```

服务监听 `http://127.0.0.1:8000`，交互式文档在 `http://127.0.0.1:8000/docs`。

### 4. 验证

```bash
curl http://127.0.0.1:8000/health
```

```json
{
  "code": "OK",
  "message": "service is alive",
  "data": {
    "status": "ok",
    "service": "TripPilot",
    "version": "0.1.0",
    "environment": "local",
    "uptimeSeconds": 0.036963
  },
  "traceId": "ea1d953170c249c6a9521e9e3b34e3d4"
}
```

```bash
curl http://127.0.0.1:8000/ready
```

```json
{
  "code": "READY",
  "message": "service is ready",
  "data": {
    "status": "ready",
    "service": "TripPilot",
    "version": "0.1.0",
    "environment": "local",
    "checkedAt": "2026-10-11T17:47:24.185384Z",
    "dependencies": [
      {
        "name": "database",
        "state": "not_configured",
        "required": false,
        "detail": "No database is wired up yet: TRIPPILOT_DATABASE_URL is unset and infrastructure/persistence/ has no implementation."
      }
    ]
  },
  "traceId": "db12b8ccef8c4ba9b80bbc9af33baa2e"
}
```

> `/ready` 这里的 `state` 是 `not_configured`，**不是** `ok`。
> 进程里没有创建任何数据库连接，所以没有"检查通过"这回事——探针如实说明"该依赖尚未接入"。
> 等第一个 repository 落地时，这个字段才会变成真实探测的结果。

### 使用 Docker Compose

```bash
make up                     # 构建并后台启动 api + db
make logs                   # 跟踪 api 日志
make down                   # 停止（make down V=1 会连数据库卷一起删除）
```

Compose 提供的 PostgreSQL 是为下一阶段准备的，**应用目前不会连接它**（因此 api 服务刻意没有 `depends_on: db`）。

---

## API 契约

所有响应共享同一个信封，JSON 采用 **camelCase**（面向未来的 React + TypeScript 前端）。

**成功**

```json
{ "code": "OK", "message": "ok", "data": { }, "traceId": "..." }
```

**失败**

```json
{ "code": "NOT_FOUND", "message": "Not Found", "details": null, "traceId": "..." }
```

`code` 是稳定的机器可读标识（客户端与评测可以断言），`message` 可能变化。
每个响应都带 `X-Trace-Id` 响应头，其值与 body 中的 `traceId` 一致；请求时可自带该 header，服务会复用，从而跨服务串联链路。

| 端点 | 状态码 | 说明 |
| --- | --- | --- |
| `GET /health` | 200 | 进程存活。不做任何 I/O，不依赖数据库。 |
| `GET /ready` | 200 / 503 | 所有 `required` 依赖可用时 200，否则 503。 |
| `GET /docs` | 200 | OpenAPI 交互文档。 |
| `GET /openapi.json` | 200 | OpenAPI 3 schema。 |

---

## 测试与代码质量

```bash
make test                   # 全部测试
make cov                    # 带覆盖率
make lint                   # Ruff 检查
make format                 # Ruff 自动格式化
make format-check           # 只校验格式，不改文件
make typecheck              # mypy strict
make check                  # lint + format-check + typecheck
make ci                     # check + cov —— 与 CI 完全一致
```

等价的底层命令：

```bash
uv run pytest
uv run pytest tests/unit/test_domain_trip.py::TestDateRules -v   # 单个测试类
uv run pytest -k "trace_id" -v                                   # 按名字筛选
uv run ruff check --fix .
uv run mypy
```

**当前实测结果**（本机 Python 3.13.13，2026-10-12）：

| 检查 | 命令 | 结果 |
| --- | --- | --- |
| 测试 | `uv run pytest` | **78 passed** |
| 覆盖率 | `uv run pytest --cov` | **98%**（431 语句，8 未覆盖） |
| Lint + 格式 | `uv run ruff check .` / `ruff format --check .` | **通过**，32 文件格式一致 |
| 类型 | `uv run mypy` | **通过**，28 文件无问题 |
| 镜像构建 | `docker build -t trippilot:local .` | **成功**（411 MB） |
| 容器运行 | `docker run` + `curl /health` | **200**，非 root（uid 1000），HEALTHCHECK → `healthy` |
| Compose 栈 | `make up` | **api 与 db 均 healthy**，PostgreSQL 17.11 |

CI 在 Pull Request 与推送到 `main` 时执行同样的检查，Python 矩阵 3.12 / 3.13。

---

## 配置

所有配置项都通过 `TRIPPILOT_` 前缀的环境变量注入，且**只在 `src/trippilot/core/config.py` 中读取**。
完整清单见 [`.env.example`](.env.example)。

| 变量 | 默认值 | 说明 |
| --- | --- | --- |
| `TRIPPILOT_APP_ENV` | `local` | `local` / `staging` / `production` |
| `TRIPPILOT_DEBUG` | `false` | `production` 下必须为 `false`，否则启动失败 |
| `TRIPPILOT_LOG_LEVEL` | `INFO` | 大小写不敏感 |
| `TRIPPILOT_LOG_FORMAT` | `console` | `json`（生产 / CI）或 `console`（本地） |
| `TRIPPILOT_TRACE_HEADER` | `X-Trace-Id` | 链路追踪 header 名 |
| `TRIPPILOT_DATABASE_URL` | 未设置 | PostgreSQL DSN；本阶段可选 |
| `TRIPPILOT_LLM_PROVIDER` / `_MODEL` / `_API_KEY` | 未设置 | **预留**，当前无任何代码读取 |

配置有问题时**启动即失败**，并且报错会指出具体的环境变量名：

```
ConfigurationError: Invalid TripPilot configuration:
  - TRIPPILOT_DEBUG must be false when TRIPPILOT_APP_ENV=production
  - TRIPPILOT_DATABASE_URL must be a PostgreSQL DSN starting with
    ('postgresql://', 'postgresql+asyncpg://'); got 'sqlite'
```

---

## 项目结构

```
trippilot/
├── AGENTS.md                 # 工程规约（编码 Agent 必读，唯一规约来源）
├── CLAUDE.md                 # 补充陷阱（Claude Code 用，导入 AGENTS.md）
├── src/trippilot/
│   ├── main.py               # 应用工厂 + lifespan + ASGI 入口
│   ├── api/                  # 接口层：路由、中间件、异常映射、依赖、运维探针
│   ├── core/                 # 通用组件：配置、日志、异常、运行时状态
│   ├── domain/               # 领域模型与业务规则（框架无关）
│   │   ├── models.py         # TripRequest 等
│   │   └── ports/            # Repository 等内层定义的接口（占位）
│   ├── schemas/              # 对外 API 契约
│   ├── services/             # 应用服务层（占位）
│   ├── agent/                # LangGraph 编排层（占位）
│   ├── tools/                # Agent 工具层（占位）
│   └── infrastructure/       # 基础设施适配层（占位）
├── docs/                     # 产品 / 架构 / 契约 / 质量文档
├── evals/cases.jsonl         # 评测用例格式与样例
├── tests/{unit,integration,e2e}/
├── Dockerfile / docker-compose.yml / Makefile
└── .github/workflows/ci.yml
```

目标结构与完整职责划分见 `AGENTS.md` 第 3、4 节；`api/v1/`、`services/` 下的具体模块、
`domain/ports/trip_repository.py`、`agent/graph.py`、`tools/registry.py`、
`infrastructure/{llm,persistence,search,observability}/`、`configs/`、`scripts/` 均**尚未创建**——
它们等各自有真实职责时再建，不提前铺空壳。

### 与初始目录规划的差异

三处**刻意未创建**，避免生成没有用途的空壳：

| 原规划 | 处理 | 理由 |
| --- | --- | --- |
| `migrations/env.py` | **未创建** | 当前没有任何 SQLAlchemy 模型，Alembic 初始化后会得到一个迁移不出任何东西的空目录。等第一个模型落地时再 `alembic init`。 |
| `tests/e2e/` 下的测试 | **仅放 README** | 端到端测试需要"请求进 → 完整行程出"的链路，而该链路尚不存在。现在写只会断言 stub，无法证明任何事。`e2e` marker 已注册备用。 |
| `evals/cases.jsonl` | 创建（仅格式样例） | 只定义数据格式，**不含任何编造的准确率或成功率**。 |

### 2026-10-13 结构迁移

按新版 `AGENTS.md`（引入 `services/` 应用服务层与依赖倒置）做了一次仓库结构调整：

| 变更 | 说明 |
| --- | --- |
| `app/trippilot/` → `src/trippilot/` | 采用 `src/` 布局；同步改了 `pyproject.toml`（hatchling / mypy / ruff / coverage）、`Dockerfile` |
| `core/errors.py` → `core/exceptions.py` | 与规约命名对齐 |
| `domain/trip.py` → `domain/models.py` | 同上；`domain/itinerary.py` 等行程模型落地时再建 |
| `api/routes/health.py` → `api/health.py` | 业务端点未来进 `api/v1/`，运维探针留在 `api/` 根 |
| **删除** `repositories/` | 新规约把抽象放 `domain/ports/`、实现放 `infrastructure/persistence/`，该顶层包不再有独立职责 |
| **删除** `observability/` | 并入 `infrastructure/observability/`（尚未创建） |
| **新增** `services/`、`infrastructure/`、`domain/ports/` | 仅 `__init__.py` docstring 占位 |

详见 ADR-0001（分层修订）与 ADR-0009（占位包策略修订）。

---

## 路线图

按依赖顺序推进，每一阶段都可独立验证：

**阶段 1 — 打通领域闭环（无 LLM）**
在 `domain/` 中实现槽位合并与冲突检测，用确定性规则实现 `missing_slots` / 冲突识别，并补齐单元测试。这是后续一切的地基，且不需要任何外部依赖。

**阶段 2 — 工具契约 + Mock Provider**
按 `docs/contracts/tool-contracts.md` 定义统一工具契约，实现景点 / 天气 / 路线三个 **Mock** 工具，覆盖超时、重试、错误分类与来源元数据。

**阶段 3 — 单一 LangGraph 工作流**
`parse → check_slots → clarify → gather_context → plan → respond`，接入阶段 1 的规则与阶段 2 的 Mock 工具。此时可跑通端到端评测，`tests/e2e/` 开始有真实内容。

**阶段 4 — 评测与可观测性**
落地 `docs/quality/evaluation-plan.md` 定义的指标，接入 `observability/` 的节点耗时与 Token 统计。

**阶段 5 — 持久化**
引入 Alembic 迁移、repository 实现，`/ready` 的数据库依赖从 `not_configured` 变为真实探测。

**阶段 6 — 真实 Provider 与前端**
在评测证明 Mock 闭环正确之后，逐个替换为真实 API；再启动 React + TypeScript 前端。

---

## 已知限制与未验证项

如实记录，避免误判完成度：

- **无数据库连接。** SQLAlchemy / Alembic 已装但未被任何代码引用，`migrations/` 不存在。Compose 栈里的 PostgreSQL 17.11 能正常启动并接受连接，但**应用不会连接它**——`/ready` 在有 DSN 时也只会报告「已配置但未连接」。
- **镜像只在 arm64 上验证过。** 本机为 Apple Silicon；CI 目前不构建镜像，因此 x86_64 与其他基础镜像变体未验证。
- **Compose 是开发用途。** 其中的数据库口令是本地用的临时值，不能用于任何真实环境。
- **无鉴权。** 所有端点公开，无认证、无速率限制。
- **业务端点为 0 个。** 目前只有运维探针。
- **Alembic 迁移缺失**（预期内，见上文差异说明）。
- **日志未接入追踪后端。** traceId 只在进程内生效，尚未导出到 OpenTelemetry / LangSmith 等。
- **未测并发场景。** 测试均为单请求顺序执行。

---

## 文档索引

| 文档 | 内容 |
| --- | --- |
| [`AGENTS.md`](AGENTS.md) | 工程规约：分层、Agent 设计原则、AI Native 工作流、完成定义 |
| [`CLAUDE.md`](CLAUDE.md) | Claude Code 专用：命令与跨文件架构约定 |
| [`docs/product/PRD.md`](docs/product/PRD.md) | 目标用户、核心场景、MVP 范围、非目标 |
| [`docs/product/user-flows.md`](docs/product/user-flows.md) | 关键用户流程与系统交互时序 |
| [`docs/architecture/overview.md`](docs/architecture/overview.md) | 分层职责、数据流、真实 Provider 接入方式 |
| [`docs/architecture/state-model.md`](docs/architecture/state-model.md) | 需求状态、槽位增量更新、冲突澄清、三类状态的区分 |
| [`docs/architecture/decisions/`](docs/architecture/decisions/README.md) | 架构决策记录（ADR） |
| [`docs/contracts/tool-contracts.md`](docs/contracts/tool-contracts.md) | 外部工具统一契约 |
| [`docs/quality/test-strategy.md`](docs/quality/test-strategy.md) | 单元 / 集成 / 端到端 / CI 的职责边界 |
| [`docs/quality/evaluation-plan.md`](docs/quality/evaluation-plan.md) | Agent 评测方案与指标定义 |

## 许可证

尚未指定。
