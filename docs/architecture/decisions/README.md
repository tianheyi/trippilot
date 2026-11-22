# 架构决策记录（ADR）

本目录记录**已经做出的、有约束力的技术决策**及其理由。

## 格式约定

单个决策未来拆分为独立文件时，使用 `NNNN-短标题.md`，包含四个部分：

```markdown
# ADR-NNNN 决策标题

状态：提议 | 已接受 | 已废弃 | 被 ADR-XXXX 取代
日期：YYYY-MM-DD

## 背景
是什么问题迫使我们做决定。

## 决策
我们决定做什么。

## 理由
为什么这样选，以及**放弃了什么**。

## 后果
正面影响、负面影响、以及未来在什么条件下应该重新审视。
```

当前阶段决策数量有限，先集中记录在本文件；超过约 10 条或出现争议记录时再拆分。

---

## ADR-0001：分层架构与单向依赖

**状态**：已接受（**2026-10-13 修订**：层清单与依赖方向按新规约重写，见下方"修订"）

**背景**：Agent 类项目容易演变成"什么都塞进一个 handler"或"领域逻辑与 LLM 调用缠绕在一起"，导致业务规则无法独立测试、无法脱离框架复用。

**决策**：采用 `api / services / agent / tools / domain / schemas / infrastructure / core` 分层，核心调用链为 `api → services → agent → tools → infrastructure`，并由 `domain/ports/` 定义接口、`infrastructure/` 提供实现（依赖倒置）。`domain/` 禁止 import FastAPI、LangGraph、SQLAlchemy、HTTP 客户端。

**理由**：
- `domain/` 纯净 → 业务规则可用纯单元测试覆盖，不需要起服务、不需要 mock LLM。
- 未来 CLI、批处理评测、前端可直接复用领域模型。
- 依赖方向可被 CI 与代码审查机械检查。

**放弃**：少量样板代码（例如 `schemas/` 与 `domain/` 需要各自定义相似模型）。

**修订（2026-10-13）**：原始决策把层写成一个扁平集合
（`api / domain / schemas / agent / tools / repositories / core / observability`），
隐含"任意上层可直接依赖任意下层"。新规约引入了两个变化：

1. **新增 `services/` 应用服务层**，插在 `api` 与 `agent` 之间。接口层不再直接编排 Agent。
2. **`repositories/` 与 `observability/` 两个顶层包被移除**：Repository 抽象归入 `domain/ports/`、
   实现归入 `infrastructure/persistence/`；可观测性归入 `infrastructure/observability/`。
   `core/` 仍是跨模块能力层，但不再承载持久化。

依赖方向因此从"扁平集合内的单向流动"变成"一条明确的调用链 + 一条依赖倒置回路"。
完整规则见 `AGENTS.md` 第 5 节。

**重新审视条件**：若出现大量"同一模型在两个层之间逐字段搬运"的重复代码，考虑引入显式映射层而不是合并两层。

---

## ADR-0002：统一响应信封 + camelCase

**状态**：已接受

**背景**：前端（未来为 React + TypeScript）需要处理多种端点的响应；若每个端点形状不同，客户端要为每个端点写一套解析与错误处理。

**决策**：所有端点返回同一信封。成功 `{"code","message","data","traceId"}`，失败 `{"code","message","details","traceId"}`。JSON 字段用 camelCase，通过 Pydantic 的 `alias_generator=to_camel` + `populate_by_name=True` 实现——Python 侧写 snake_case，JSON 侧输出 camelCase。

**理由**：
- 客户端只需一个泛型 `ApiResponse<T>` 和一个 `ErrorResponse`。
- `code` 稳定、可断言；`message` 可自由改动。
- camelCase 符合 TS 习惯，省掉一层转换。

**放弃**：与 Python 生态常见的 snake_case JSON 惯例不一致；需要团队记住"Python 写 snake，接口是 camel"。

**重新审视条件**：若接入的第三方（如内部网关）强制要求 snake_case。

---

## ADR-0003：业务异常用 `AppError`，不用 `HTTPException`

**状态**：已接受

**背景**：FastAPI 的惯例是在业务代码里 `raise HTTPException(404, ...)`，但 `HTTPException` 来自 FastAPI。

**决策**：`core/exceptions.py` 定义 `AppError` 及子类，自带稳定的 `code` 与 `http_status`，**不依赖任何框架**。HTTP 映射集中在 `api/errors.py`。

**理由**：让 ADR-0001 的依赖规则在异常路径上也成立。若业务代码抛 `HTTPException`，`domain/` 就被 FastAPI 绑死了。

**代价**：需要在 `api/errors.py` 维护一份状态码映射表。

---

## ADR-0004：traceId 使用 ContextVar，并镜像到 `scope["state"]`

**状态**：已接受

**背景**：需要让任意深度的代码（未来的 LangGraph 节点、工具适配器）都能输出关联日志，而不必逐层传递 trace id 参数。同时，**未处理异常**必须仍能携带 trace id 返回给客户端。

**决策**：
- trace id 存在 ContextVar 中，日志 formatter 直接读取 → 深层代码零成本获得关联能力。
- 同时写入 `scope["state"]`，因为 `TraceIdMiddleware` 在 `finally` 中重置 ContextVar，而未处理异常由更外层的 `ServerErrorMiddleware` 处理——那时 ContextVar 已清空。异常处理器从 `request.state.trace_id` 读取。

**理由**：单用 ContextVar 会导致 500 响应丢失 trace id；单用 `scope["state"]` 会让日志组件侵入请求对象。

**代价**：两个存储点必须同步维护。已由 `tests/integration/test_health_endpoints.py::TestTracePropagation` 与 `TestErrorEnvelope` 覆盖。

**重新审视条件**：接入 OpenTelemetry 时，可直接用其 `trace_id` 取代自建机制，届时删除 `core/logging.py` 中的 ContextVar 部分。

---

## ADR-0005：探针如实上报，`not_configured` ≠ `ok`

**状态**：已接受

**背景**：很多项目在数据库尚未接入时，健康检查直接返回 `{"database": "ok"}`，或干脆不报告该依赖。两者都会让运维基于错误信息做判断。

**决策**：`/ready` 无条件把数据库报为 `state="not_configured"`、`required=false`，并在 `detail` 中说明具体原因。`/health` 不做任何 I/O。

**理由**：`not_configured`（尚未接入）、`down`（接了但挂了）、`ok`（接了且正常）是三种不同事实，混同会让值班人员误判。同时 `/health` 保持零依赖，避免数据库抖动引发容器被反复重启。

**后果**：`/ready` 目前恒返回 200。这是**正确**的——当前 API 暴露的所有端点确实不需要存储。等第一个 repository 落地时，必须同步把 `required` 改为 `True` 并接入真实探测（见 `docs/architecture/overview.md` 3.3）。

**风险**：这条约定容易被后来者忽略。修改 `_dependency_statuses` 时必须连带改 lifespan 与 Alembic，已在代码注释中标注。

---

## ADR-0006：单一 LangGraph 工作流，不做多 Agent

**状态**：已接受（约束未来实现）

**背景**：多 Agent 协作、消息总线、分布式编排是常见的技术吸引力陷阱，在需求尚未验证时会显著增加复杂度与调试难度。

**决策**：初期只做**一个** LangGraph 工作流，节点线性为主，最多带条件分支（澄清回路）。

**理由**：单工作流的状态可完整观察、可确定性重放、可单元测试每个节点。多 Agent 引入的非确定性对评测极为不利。

**重新审视条件**：当出现**已被评测证明**的、单一工作流无法满足的需求时（例如并行的多城市独立规划），再评估拆分。届时应先写 ADR。

---

## ADR-0007：先 Mock 打通闭环，再接真实 Provider

**状态**：已接受（约束未来实现）

**背景**：直接接真实 API 会导致：评测不可复现（数据每天变）、开发受配额与网络限制、成本在闭环跑通前就开始累积。

**决策**：为每个工具先实现 Mock，返回结构完整（含 `source` / `fetchedAt` / `expiresAt`）的确定性数据。用 Mock 跑通工作流与评测后，再实现同契约的真实适配器。

**理由**：**Mock 是长期测试资产，不是临时脚手架。** 评测需要可复现的输入，真实 API 无法提供。

**代价**：Mock 与真实实现的契约可能漂移 → 用同一套契约测试跑两者来防止。

---

## ADR-0008：mypy strict + PEP 695 泛型

**状态**：已接受

**背景**：类型检查的严格程度需要在"有价值"与"噪音过多导致被绕过"之间取平衡。

**决策**：mypy 开启 `strict = true` 与 `warn_unreachable`，启用 `pydantic.mypy` 插件，`warn_unused_ignores = true`。仅对 `langgraph.*` / `langchain_core.*` 豁免缺失类型（我们控制不了的 stub）。泛型使用 PEP 695 语法（`class ApiResponse[DataT]`）而非 `Generic[DataT]`。

**理由**：
- strict 且**禁止无用的 ignore**，可防止"靠 ignore 制造通过假象"。
- 不用 `disallow_untyped_defs` 的白名单式放宽——那会让严格度随时间腐化。
- PEP 695 更简洁，且项目下限是 3.12，可以放心用（Ruff 的 UP046 也会强制）。

**代价**：测试代码也需要完整类型注解，写起来略啰嗦。

---

## ADR-0009：不创建空壳目录

**状态**：已接受（**2026-10-13 修订**：占位包策略调整，见下方"修订"）

**背景**：初始目录规划中包含 `migrations/` 与 `tests/e2e/` 下的测试。

**决策**：
- **不创建** `migrations/`。当前没有任何 SQLAlchemy 模型，`alembic init` 会产生一个迁移不出任何东西的空目录。
- `tests/e2e/` 只放 README，**不写测试**。端到端链路尚不存在，写了只能断言 stub。
- `evals/cases.jsonl` 只定义数据格式，**不含任何编造的指标**。
- `agent/` / `tools/` 等尚未实现的分层，其包只放 docstring，说明该层承载什么、受什么约束。

**理由**：空实现会让人误以为能力存在，也会在后续重构中成为需要维护的噪音。docstring 占位保留了"边界已划定"的信息，同时明确"这里还没有代码"。

**修订（2026-10-13）**：新规约（`AGENTS.md` 第 3、4 节）引入了新的分层
（`api / services / agent / tools / domain / schemas / infrastructure / core`），因此：

1. **`repositories/` 与 `observability/` 两个占位包被删除**，不是改名——新规约把它们
   降级为 `domain/ports/` 与 `infrastructure/` 的子目录，顶层包不再有独立职责。
   保留它们会形成"两个目录定义同一职责"，正是新规约 §4.7 明令禁止的。
2. **`services/` 与 `infrastructure/` 新增为占位包**，`domain/ports/` 同理。
3. **保留原决策中"不创建 `migrations/`"与"`tests/e2e/` 只放 README"两条**，理由不变。
4. **源码根从 `app/` 迁移到 `src/`**（新规约第 3 节的推荐结构）。
5. **判据收紧为**：包的存废取决于"它现在有没有职责"，而不是"它未来会不会有"。
   只放 docstring 的包是可接受的；**但一个包若在新架构里已被别的目录取代，就删除**。

新规约同时要求"避免空模块"，因此 `api/v1/`、`configs/`、`scripts/`、
`infrastructure/{llm,persistence,search,observability}/`、`agent/{graph,state,policies}.py`
等**均未创建**——等各自有真实内容时再建。

**重新审视条件**：对应层的第一个真实实现落地时；或分层再次调整时。
