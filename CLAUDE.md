# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

@AGENTS.md

`AGENTS.md` 是**唯一的工程规约来源**，通过上面的导入整份进入上下文——分层规则、Agent 设计原则、状态与持久化、配置与安全、AI Native 工作流、完成定义都在那里。本文件**只补充 `AGENTS.md` 没有的东西**：当前阶段状态，以及需要读多个文件才能拼出来的实现陷阱。两者冲突时一律**以 `AGENTS.md` 为准**。

> 维护提示：上方那行 `@AGENTS.md` 是 Claude Code 的导入指令，**不是普通的文字提及**。删掉它 Claude Code 就读不到规约了；不要把它挪进代码块（代码块里的 `@` 不会被解析）。

---

## 当前阶段

最小工程骨架。已实现：应用工厂与生命周期、`/health`、`/ready`、统一响应信封与异常处理、结构化日志（traceId）、配置加载与启动校验、旅行需求领域模型、测试/Ruff/mypy/CI/Docker Compose。

未实现：LLM 调用、LangGraph 工作流、外部 Provider、数据库读写、Alembic 迁移、应用服务层。`services/`、`agent/`、`tools/`、`infrastructure/` 目前**只有 docstring 占位**。不要假设这些能力存在。目标结构与本仓库实际内容的逐项对照见 `AGENTS.md` §13。

---

## 命令

命令清单见 `AGENTS.md` §1，此处不重复。三点补充：

- CI（`.github/workflows/ci.yml`）跑的就是 `make check` 与 `make cov`，**本地绿即 CI 绿**。Python 矩阵 3.12 / 3.13，3.12 是 `requires-python` 下限。
- 仓库里还有 `make up` / `down` / `logs` / `ps`（Compose 栈）。`make help` 列出全部目标。
- 迁移相关目标（`migrate` 等）**目前不存在**——按路线图属于阶段 5，等第一个 repository 落地时再加。

---

## 架构

依赖方向见 `AGENTS.md` §5（唯一权威）。最容易违反的三条：

```
        api
         |
         v
      services ────────> domain/ports
         |
         v
       agent
         |
         v
       tools
         |
         v
  infrastructure

  domain <───────── infrastructure 实现 domain 定义的接口
  main.py：创建具体实现并组装依赖
```

1. `tools/` 不得反向调用 `agent/`，也不得依赖 `api/`。
2. `domain/` 不得 import `fastapi` / `langgraph` / `sqlalchemy` / `httpx`。Pydantic 允许。
3. Repository 接口在 `domain/ports/`，实现在 `infrastructure/persistence/`，内层不得导入具体实现。

`schemas/` 是 API 对外契约，与 `domain/` 相互独立——两边可以各自改形状而互不影响，**不默认把 Schema 当领域模型**。

一次请求的完整链路（**当前**只有运维探针走这条）：

```
TraceIdMiddleware → ExceptionMiddleware → 路由 → RuntimeDep → 阶段函数
        │                                      │
        └── 绑定 traceId 到 contextvar           └── 返回 ApiResponse[T] 信封
            并镜像到 scope["state"]
```

---

## 需要读多个文件才能看懂的地方

**traceId 为什么同时存在 contextvar 和 `scope["state"]` 里。**
`core/logging.py` 把 trace id 放在 ContextVar，日志 formatter 直接读它，所以深层代码无需接收参数就能打出关联日志。但 `TraceIdMiddleware` 在 `finally` 里重置了 ContextVar，而**未处理异常**由 Starlette 最外层的 `ServerErrorMiddleware` 处理——那时 ContextVar 已经清空。因此中间件额外把 trace id 写进 `scope["state"]`，`api/errors.py` 的 handler 从 `request.state.trace_id` 读取。改动中间件时两者都要维护，`tests/integration/test_health_endpoints.py::TestTracePropagation` 与 `TestErrorEnvelope` 覆盖了这两条路径。

**响应信封是 camelCase。**
`schemas/common.py` 的 `CamelModel` 用 `alias_generator=to_camel` + `populate_by_name=True`：Python 侧写 `trace_id`，JSON 侧输出 `traceId`（FastAPI 的 `response_model` 默认 `by_alias=True`）。测试和内部调用可以用 snake_case 构造。`ApiResponse` 用的是 PEP 695 泛型语法（`class ApiResponse[DataT]`），不是 `Generic[DataT]`——Ruff 的 UP046 会强制这一点。

**错误必须抛 `AppError` 子类，不要抛 `HTTPException`。**
`core/exceptions.py` 定义异常分类（每个子类带稳定的 `code` 与 `http_status`），且**不依赖 FastAPI**；HTTP 映射集中在 `api/errors.py`。所有 handler 都从 `core/exceptions.py` 的基类派生，保证客户端永远拿到 `ErrorResponse` 形状，看不到 FastAPI 原生的 `{"detail": ...}`。

**`/ready` 不伪造数据库检查。**
`api/health.py::_dependency_statuses` 无条件把数据库报为 `not_configured` / `required=False`，因为进程里根本没有创建 engine。等持久化落地时需要**同时**改**四处**（`docs/architecture/overview.md` §3.3，少改一处 `/ready` 就开始撒谎）：

1. `core/config.py`：`database_url` 在非 local 环境变必填；
2. `main.py` 的 lifespan：创建/释放 engine 与 session factory；
3. 新增 `migrations/` 与第一个 Alembic 迁移；
4. 该函数：`required` 翻为 `True`，`state` 换成真实探测结果。

`tests/integration/test_health_endpoints.py::TestReady` 断言了当前这个诚实的取值。

**环境变量只有 `core/config.py` 能读。**
变量前缀 `TRIPPILOT_`，`.env` 会被自动加载。`get_settings()` 是 `lru_cache` 单例，且会把 Pydantic 的字段级报错翻译成**环境变量名**（`environment_variable_name()`），因为运维看到 `app_env` 没有意义。测试必须显式传 `_env_file=None` 构造 `Settings`，否则开发机的 `.env` 会污染测试结果（见 `tests/conftest.py`）。

**`import trippilot.main` 有副作用。**
模块底部有 `app = create_app()`，供 `uvicorn trippilot.main:app` 使用。导入即读取配置、**重设 root logger**、并校验配置是否自相矛盾（不合法会直接抛 `ConfigurationError`）。测试里要构造自己的 app，用 `create_app(Settings(...))`。

**`configure_logging` 会清空 root logger 的 handler。**
这是有意为之（避免重复输出），但意味着 `caplog` 在它之后会失效——`tests/integration/test_app_lifecycle.py` 因此改为断言 stdout。同理，在 **fixture 里**创建 `logging.StreamHandler(sys.stdout)` 拿到的可能不是 `capsys` 的替换对象（fixture 早于 capsys 激活），`tests/unit/test_logging.py` 用 `RecordingLogger` + `StringIO` 绕开了这个陷阱。

**mypy 是 strict。**
配置在 `pyproject.toml`，启用 `pydantic.mypy` 插件，`warn_unused_ignores = true`（多余的 ignore 会报错）。`langgraph.*` / `langchain_core.*` 的缺类型被单独豁免，其余一律严格。不要用大范围 ignore 换通过。

**FastAPI 0.143 的 `app.routes` 里包含 `_IncludedRouter` 包装对象**，不是扁平的 `APIRoute` 列表。做路由反射（比如断言 OpenAPI paths）请走 `/openapi.json`，不要遍历 `app.routes`。

---

## 改动前必看

- 新增 API 端点：`api/` 建模块 → 在 `api/router.py` 挂载；业务端点未来挂在 `/api/v1` 前缀下（运维端点保持在根路径）。
- 新增配置项：`core/config.py` → `.env.example` → `docs/architecture/overview.md`。
- 新增错误类型：继承 `core/exceptions.py::AppError`，给出稳定的 `code`。
- 数据库相关改动属于架构变化，先按 `AGENTS.md` 6.1 出方案再动手。
