# 架构概览

> **状态**：本文档同时描述**已实现的结构**和**尚未实现的层级**。
> 每个小节都标注了当前状态，请以标注为准。

---

## 1. 分层与依赖方向

**完整规约见 `AGENTS.md` 第 5 节，本节只做落地说明。**

```
        api
         |
         v
      services --------> domain ports
         |
         v
       agent
         |
         v
       tools
         |
         v
  infrastructure clients

  domain <--------- infrastructure implements domain ports

  main.py：创建具体实现并组装依赖
```

> 图示表示**逻辑关系**，不代表所有模块必须直接导入图中下一层。

### 当前状态

| 层 | 状态 | 说明 |
| --- | --- | --- |
| `api/` | ✅ 已实现 | 仅运维端点（`/health`、`/ready`）；`api/v1/` 业务端点尚未创建 |
| `core/` | ✅ 已实现 | 配置、日志、异常、运行时状态 |
| `domain/` | ⚠️ 部分 | 需求模型 `TripRequest` 已实现；行程模型与 `domain/ports/` 尚未创建 |
| `schemas/` | ✅ 已实现 | 信封 + 探针模型 |
| `services/` | ❌ 仅 docstring | 应用服务层，等第一条业务用例 |
| `agent/` | ❌ 仅 docstring | LangGraph 编排层 |
| `tools/` | ❌ 仅 docstring | Agent 工具层 |
| `infrastructure/` | ❌ 仅 docstring | LLM / 持久化 / 搜索 / 可观测性适配器 |

### 依赖规则（强制）

以 `AGENTS.md` 第 5 节为准。其中最容易违反、也最需要审查时盯住的三条：

1. **`tools/` 不得反向调用 `agent/`，也不得依赖 `api/`。**
2. **`domain/` 不依赖任何框架。** 禁止 `fastapi` / `langgraph` / `sqlalchemy` / `httpx` 出现在 `domain/` 的 import 中。Pydantic 允许——它是校验库，不是 Web 框架。
3. **Repository 接口由内层（`domain/ports/`）定义，具体实现由 `infrastructure/` 提供。** 内层不得导入具体实现。

第 2 条是整套设计的关键：只要 `domain/` 保持纯净，业务规则就能脱离 HTTP 与 LLM 独立测试，也能在未来被 CLI、批处理评测或前端直接复用。

**业务代码抛 `AppError` 子类，不抛 `HTTPException`**；异常到 HTTP 的映射集中在 `api/errors.py`（ADR-0003）。

### 为什么 `schemas/` 与 `domain/` 分开

| | `domain/` | `schemas/` |
| --- | --- | --- |
| 面向 | 业务规则 | API 消费者 |
| 命名 | snake_case | camelCase（前端是 TS） |
| 变更原因 | 业务规则变化 | 接口形态变化 |
| 谁依赖 | services、agent | api |

两者独立演化。例如给前端加一个 `totalCost` 汇总字段，不需要动 `domain/`；反之调整领域校验规则，也不改变 API 形状。

**不默认把 API Schema 当作领域模型**（`AGENTS.md` §4.6）——两者之间的转换在接口边界显式完成。

---

## 2. 已实现的核心数据流

### 请求处理链路

```
                         ┌──────────────────────────────────────────┐
   HTTP 请求 ───────────> │ ServerErrorMiddleware（Starlette 最外层）   │
                         ├──────────────────────────────────────────┤
                         │ TraceIdMiddleware                        │
                         │  1. 复用入站 X-Trace-Id，否则生成         │
                         │  2. 绑定 ContextVar（供日志 formatter 读） │
                         │  3. 镜像到 scope["state"]（供异常处理器读）│
                         │  4. 回写响应头（已存在则不重复）           │
                         ├──────────────────────────────────────────┤
                         │ ExceptionMiddleware（FastAPI）            │
                         │  AppError / RequestValidationError /      │
                         │  HTTPException / Exception → ErrorResponse│
                         ├──────────────────────────────────────────┤
                         │ 路由 → RuntimeDep → 阶段函数               │
                         │  返回 ApiResponse[T]（camelCase 信封）     │
                         └──────────────────────────────────────────┘
```

**为什么 trace id 存两份**：ContextVar 服务于日志（深层代码无需传参即可打出关联日志）；`scope["state"]` 服务于异常处理器——`TraceIdMiddleware` 在 `finally` 中重置了 ContextVar，而**未处理异常**由位于更外层的 `ServerErrorMiddleware` 处理，那一刻 ContextVar 已清空。`api/errors.py` 因此从 `request.state.trace_id` 读取。

### 配置流

```
环境变量 / .env
      │  唯一入口
      v
core/config.py :: Settings（Pydantic 校验）
      │
      ├─ 字段级错误 → get_settings() 翻译成环境变量名 → ConfigurationError
      │
      v
Settings.check_startup_requirements()   跨字段一致性校验
      │
      v
main.create_app(settings)
      ├─ configure_logging(settings)
      ├─ app.state.runtime = Runtime(settings, version, started_at)
      └─ 注册中间件与异常处理器
```

启动期校验失败即抛 `ConfigurationError`，**进程不会带着错误配置开始服务**。

### 就绪检查流

```
GET /ready
   │
   v
_dependency_statuses(settings)
   │
   ├─ database: state=not_configured, required=False
   │             （无 engine、无连接，因此没有"检查通过"这回事）
   v
is_ready = all(state == ok for dep in deps if dep.required)
   │
   ├─ True  → 200 {status: ready}
   └─ False → 503 {status: not_ready}
```

**设计原则：探针只报告真实观测到的状态。** `not_configured` 与 `down` 是两种不同的事实，混为一谈会让运维误判。

---

## 3. 尚未实现层级的规划形态

### 3.1 `agent/` —— 单一 LangGraph 工作流

```
parse_request ──> check_slots ──┬──> clarify ──(等待用户)──┐
                                │                          │
                                └──> gather_context <──────┘
                                          │
                                          v
                                    plan_itinerary
                                          │
                                          v
                                   validate_constraints ──(不合格)──┐
                                          │                        │
                                          v                        │
                                       respond <──────────────────┘
```

约束（详见 `AGENTS.md` 第 3 节）：

- 单一工作流，**不引入多 Agent 协作**。
- `gather_context` **必须**在 `plan_itinerary` 之前——先有事实再排程，避免模型用记忆填空。
- 每个节点的输出都必须过 Pydantic 校验才能进入下一个节点。
- `validate_constraints` 是确定性代码，不是 LLM 调用。

### 3.2 `tools/` —— 统一契约的外部适配

```
agent/ ──> ToolProtocol（统一契约）
                 │
                 ├─ MockPoiTool       ← 先做，用于打通闭环与评测
                 ├─ MockWeatherTool
                 ├─ MockRouteTool
                 ├─ 真实 POI Provider  ← 评测证明闭环正确后再接
                 ├─ 真实天气 Provider
                 └─ 真实路线 Provider
```

**接入真实 Provider 的步骤**（必须按顺序）：

1. 契约先行：在 `docs/contracts/tool-contracts.md` 定义输入输出模型。
2. 实现 Mock，返回结构完整的假数据（含 `source` / `fetchedAt` / `expiresAt`）。
3. 用 Mock 跑通工作流与评测，确认闭环正确。
4. 实现真实适配器，**实现同一个 Protocol**。
5. 契约测试对 Mock 与真实实现跑同一套断言。
6. 逐层切换（先本地 → 再 staging），保留 Mock 用于离线测试与评测复现。

Mock 不是临时脚手架，而是**长期保留的测试资产**：评测需要可复现的确定性输入，真实 API 无法提供。

### 3.3 持久化 —— `domain/ports/` 定义接口，`infrastructure/persistence/` 提供实现

```
services/ ──依赖抽象──> domain/ports/TripRepository（Protocol）
                                  ^
                                  │ 实现
                     infrastructure/persistence/
                       ├─ PostgresTripRepository（SQLAlchemy 2.x async）
                       └─ InMemoryTripRepository（测试用）
```

依赖倒置的意图：`services/` 只认识 Protocol，换数据库或换内存实现都不需要改上层。
完整示例见 `AGENTS.md` 第 6 节。

**注意**：`repositories/` 目录**已被删除**。旧规约把它当独立层，新规约把抽象放 `domain/ports/`、实现放 `infrastructure/persistence/`，该目录不再有独立职责（`AGENTS.md` §4.7）。

落地时需要**同时**完成：

1. `core/config.py` 中 `database_url` 从可选变为必填（在非 local 环境）。
2. `main.py` 的 lifespan 中创建/释放 engine 与 session factory。
3. `alembic init` 生成 `migrations/`，并提交第一个迁移。
4. `api/health.py::_dependency_statuses` 中数据库的 `required` 改为 `True`，`state` 改为真实探测结果。

这四处必须一起改，否则 `/ready` 会撒谎。

### 3.4 `infrastructure/observability/` —— 追踪与成本

已有地基：`core/logging.py` 的 trace id 已贯穿每个请求、每条日志。
待建：节点级耗时、模型调用记录、Token 用量与成本聚合。

接入方式应是**包裹式**（装饰器 / 上下文管理器），而不是在每个节点里手写埋点——前者不会随业务代码演进而失效。

具体后端选型（LangSmith / 自托管 Langfuse / 通用 OTel）**尚未决定**，评估见
`docs/quality/evaluation-plan.md`。届时按 OTel GenAI Semantic Conventions 埋点，
后端可替换。

---

## 4. 关键设计决策

完整清单见 [`decisions/`](decisions/README.md)。要点：

| 决策 | 理由 |
| --- | --- |
| 应用工厂 + 模块级 `app` | 测试可注入配置；uvicorn 仍能直接引用 `trippilot.main:app` |
| 统一响应信封（camelCase） | 前端只需一个泛型 + 一条错误路径 |
| `AppError` 而非 `HTTPException` | 保持 `domain/` 与 `core/` 不依赖 FastAPI |
| trace id 用 ContextVar | 深层代码无需传参即可输出关联日志 |
| 探针如实上报 `not_configured` | 运维判断不能被"假装通过"污染 |
| 配置只在 `core/config.py` 读取 | 让"无散落密钥"成为可 grep 验证的事实 |
| 包只放 docstring，无职责则删除 | 把边界钉在代码里，但不保留没有用途的包（ADR-0009 已修订） |

---

## 5. 与前端（未来）的接口约定

本阶段不实现前端，但 API 契约已按 React + TypeScript 的需要设计：

- **camelCase JSON**：与 TS 习惯一致，无需转换层。
- **统一信封**：一个泛型 `ApiResponse<T>` + 一个 `ErrorResponse` 即可覆盖全部端点。
- **稳定 `code`**：前端按 `code` 分支（`NEEDS_CLARIFICATION`、`BUDGET_EXCEEDED`…），不解析 `message`。
- **`traceId` 双向**：前端可自带 `X-Trace-Id`，出问题时把 id 报给后端即可定位。
- **规划中的业务前缀**：`/api/v1/...`。运维端点（`/health`、`/ready`）保持在根路径——负载均衡与编排系统期望在那里找到它们。

预期端点形态（**均未实现**）：

```
POST   /api/v1/trips                     创建会话，提交自然语言需求
GET    /api/v1/trips/{tripId}            读取行程
PATCH  /api/v1/trips/{tripId}            增量修改（携带 version 做并发校验）
POST   /api/v1/trips/{tripId}/messages   追加对话轮次（澄清回答）
```
