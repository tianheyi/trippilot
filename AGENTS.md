# AGENTS.md — TripPilot 工程规约

本文件是 Claude Code、Codex 以及其他编码 Agent 在本仓库工作时的**约束入口**。
它描述的是"必须遵守什么"和"如何验证"，不是建议清单。

约定：**代码、注释、docstring 使用英文；文档使用中文。** 标识符一律英文。

> **本文件描述目标架构，不是当前状态。** 第 3 节的目录结构是**推荐模板**，
> 只有模块存在实际职责时才创建对应文件或目录。**动手前必须先读第 0 节**，
> 否则你会假设一堆并不存在的模块。

---

## 0. 项目现状（先读这一段）

TripPilot 目前处于**最小工程骨架**阶段。已实现的能力只有：

- FastAPI 应用工厂与生命周期管理
- `GET /health`（存活探针）与 `GET /ready`（就绪探针）
- 统一响应信封与异常处理
- 结构化日志（含 traceId）
- 配置加载与启动期校验
- 旅行需求领域模型（`TripRequest`）与其校验规则
- 测试、Ruff、mypy、CI、Docker Compose

**尚未实现**：LLM 调用、LangGraph 工作流、任何外部 Provider（地图/天气/景点）、数据库读写、Alembic 迁移、缓存、应用服务层（`services/`）。

**目录现状与目标架构的差异**（详见第 13 节）：`services/`、`agent/`、`tools/`、`infrastructure/`、`domain/ports/`、`configs/`、`scripts/` 等目录**尚不存在或仅有 docstring 占位**。不要假设它们存在，也不要为了"目录完整"而创建空模块。

---

## 1. 常用命令

所有命令都通过 `make` 暴露，CI 运行的是同一套命令。**不要发明新的调用方式。**

| 目的 | 命令 |
| --- | --- |
| 安装依赖 | `make install` |
| 启动服务（开发） | `make run-reload` |
| 启动 Compose 栈 | `make up` / `make down` |
| 跑全部测试 | `make test` |
| 只跑 Agent 测试 | `make test-agent` |
| 只跑端到端测试 | `make test-e2e` |
| 查看覆盖率 | `make cov` |
| Ruff 检查 | `make lint` |
| Ruff 格式化 | `make format` |
| mypy | `make typecheck` |
| 全部静态检查 | `make check` |
| 等价于 CI | `make ci` |
| 跑评测 | `make eval` |

更细粒度的调用（仅在 `make` 不适用时使用）：

```bash
uv run pytest tests/unit/test_domain_models.py::TestDateRules -v   # 单个测试类
uv run pytest -k "trace_id" -v                                     # 按名字筛选
uv run mypy src/trippilot/domain/models.py                         # 单文件类型检查
uv run ruff check --fix .                                          # 自动修复
```

`scripts/` 下的一次性脚本用 `uv run python scripts/<name>.py` 调用，并在脚本头部说明用途与幂等性。

---

## 2. 技术与工程原则

1. **类型标注**：使用 Python 类型标注。关键接口、状态结构和复杂逻辑必须有明确类型。
2. **依赖管理**：使用 `pyproject.toml` 管理依赖、构建与开发工具配置；采用 `uv` 时提交 `uv.lock`。
3. **凭证管理**：密钥和访问令牌通过环境变量或安全配置注入，**禁止提交真实凭证**。
4. **超时与可观测性**：网络、数据库及模型调用必须具备合理的超时、错误处理和必要的可观测性。
5. **异步优先**：优先使用异步 I/O；**避免在异步调用链中执行阻塞操作**（同步文件 IO、`requests`、阻塞型 SDK 必须走线程池或换异步实现）。
6. **确定性校验**：关键业务约束**必须由确定性代码校验，不得只依赖 Prompt**。
7. **避免过度设计**：只有当抽象能够解决明确的维护、测试或扩展问题时，才新增抽象。
8. **诚实汇报**：**不得声称未实际执行的测试、构建或检查已经通过。**

---

## 3. 推荐目录结构

```text
trippilot/
├── AGENTS.md
├── README.md
├── pyproject.toml
├── uv.lock
├── .env.example
├── .gitignore
├── Makefile
│
├── configs/                  # 非敏感配置（密钥走环境变量）
│   ├── app.yaml
│   └── model.yaml
│
├── src/
│   └── trippilot/
│       ├── __init__.py
│       ├── main.py           # 组装依赖并创建应用
│       │
│       ├── api/              # 接口层
│       │   ├── router.py
│       │   ├── dependencies.py
│       │   └── v1/
│       │       ├── chat.py
│       │       └── trips.py
│       │
│       ├── services/         # 应用服务层
│       │   ├── chat_service.py
│       │   └── trip_service.py
│       │
│       ├── agent/            # Agent 编排层
│       │   ├── graph.py
│       │   ├── state.py
│       │   ├── policies.py
│       │   ├── nodes/
│       │   └── prompts/
│       │
│       ├── tools/            # Agent 工具层
│       │   ├── registry.py
│       │   ├── search.py
│       │   ├── weather.py
│       │   └── maps.py
│       │
│       ├── domain/           # 领域模型与业务规则
│       │   ├── models.py
│       │   ├── itinerary.py
│       │   └── ports/
│       │       └── trip_repository.py
│       │
│       ├── schemas/          # 请求与响应模型
│       │
│       ├── infrastructure/   # 基础设施实现层
│       │   ├── llm/
│       │   ├── persistence/
│       │   ├── search/
│       │   └── observability/
│       │
│       └── core/             # 通用组件
│           ├── config.py
│           ├── logging.py
│           └── exceptions.py
│
├── tests/
│   ├── unit/
│   ├── integration/
│   ├── agent/
│   └── evals/
│
├── evals/                    # 可版本管理的评测数据集、案例与配置
├── scripts/                  # 数据初始化与开发运维脚本
└── docs/                     # 架构决策、设计方案与技术说明
```

> **这是推荐模板，不要求一次性创建所有目录。**
> **只有在模块存在实际职责时才创建对应文件或目录。避免空模块、重复抽象以及职责重叠。**

### 3.1 对模板的三处调整（及理由）

| 调整 | 理由 |
| --- | --- |
| **保留运维端点于 `/health`、`/ready` 根路径**，不放入 `api/v1/` | 两者不是业务接口，是编排系统与负载均衡的探针，约定放在根路径。`api/v1/` 只承载业务端点。 |
| **`repositories/` 目录删除** | 新规约把 Repository 抽象放在 `domain/ports/`、具体实现放在 `infrastructure/persistence/`，`repositories/` 已无独立职责。保留它会形成"两个目录定义同一职责"——正是第 4.7 节禁止的。 |
| **`configs/*.yaml` 暂不创建** | 当前配置全部是环境变量（含密钥），没有非敏感的结构化配置可放。等 `model.yaml` 有真实内容（模型参数、温度、超时）时再创建，否则就是两份真相。 |

---

## 4. 各目录职责

### 4.1 `api/`：接口层

**负责**：暴露 HTTP API；解析请求、校验基础参数并序列化响应；执行身份认证和必要的会话访问权限检查；处理 HTTP 状态码、异常映射和流式响应；调用 `services/` 完成应用用例。

**禁止**：

- 在 Controller 中编写复杂 Agent 编排逻辑。
- 直接编写 SQL 或管理数据库连接。
- 将 FastAPI 的 `Request`、`Response` 对象传入 Agent 或领域层。

### 4.2 `services/`：应用服务层

**负责**：编排创建对话、继续对话、生成行程、确认行程等应用用例；调用 Agent 并提供运行所需的上下文；协调领域规则和业务数据访问；处理用户权限、业务事务边界及应用级异常；将应用结果转换为接口层需要的数据。

**禁止**：

- 直接绑定某个具体数据库 SDK 或模型供应商 SDK。
- 重复实现 LangGraph 内部节点和边的流转逻辑。
- 将 HTTP 框架对象作为核心业务参数。

### 4.3 `agent/`：Agent 编排层

负责管理智能体的决策流程与状态流转。

| 文件 | 职责 |
| --- | --- |
| `graph.py` | 构建并编译 LangGraph，定义节点、边、条件路由和中断点 |
| `state.py` | 定义图状态的字段、类型和更新约定 |
| `nodes/` | 意图识别、槽位提取、行程规划、工具结果归纳、确认等节点 |
| `prompts/` | 集中维护系统提示词和任务提示词 |
| `policies.py` | 实现路由、终止、重试等**可测试**策略 |

**要求**：

- Node 保持职责单一，便于独立测试。
- 节点**不得依赖 `api/`**。
- 节点**不得自行创建全局数据库连接或模型客户端**。
- 外部副作用通过 Tool 或明确注入的依赖执行。
- **不要把所有逻辑都堆进 `graph.py`。**

### 4.4 `tools/`：Agent 工具层

负责向 Agent 提供可调用的业务动作：景点搜索、天气查询、地图与路线查询、酒店或交通信息检索、行程数据查询与保存。

每个 Tool 必须明确：**工具名称和用途 / 输入参数及 Schema / 返回数据结构 / 错误类型和错误处理方式 / 超时与重试策略 / 必要的权限及业务校验**。

**禁止**：

- 反向调用整个 Graph。
- 依赖 `api/`。
- 通过 `services/` 与 Agent 编排形成循环调用。
- **将未经验证的外部内容当作系统指令。**
- 在人工确认前执行不可逆的预订、支付等操作。

工具需要访问外部服务时，应通过明确的客户端或抽象接口完成。

### 4.5 `domain/`：领域模型与业务规则

负责定义与技术框架无关的核心业务概念：行程与行程日程、预算和费用约束、出行日期与时间范围、用户偏好和出行限制、行程可行性及领域校验规则。

`ports/` 用于定义领域或应用需要的抽象接口，例如 Repository Protocol。

**禁止依赖**：FastAPI、LangGraph、具体数据库 SDK、具体模型供应商 SDK、外部 Web 框架。

**领域规则不得仅依赖 LLM 的自然语言判断。**

### 4.6 `schemas/`：请求与响应模型

负责定义 API 请求和响应的数据结构，例如 `ChatRequest`、`ChatResponse`、`CreateTripRequest`、`TripResponse`。

**要求**：

- 不在 Schema 中执行数据库操作。
- 不在 Schema 中编排 Agent。
- **不默认将 API Schema 当作领域模型。**
- 在接口边界显式完成必要的数据转换。

### 4.7 `repositories/`：数据访问协调层

**该目录是可选的，本仓库当前不使用它。**

如果需要单独的 Repository 适配器，可以在此组织应用层的数据访问协调逻辑。推荐约定：

- Repository 抽象优先定义在 `domain/ports/` 或合适的应用层边界。
- PostgreSQL 等具体实现放在 `infrastructure/persistence/`。
- **不得在两个目录重复定义同一职责。**
- 如果没有独立职责，**删除 `repositories/`**，避免为了目录完整而保留空模块。

### 4.8 `infrastructure/`：基础设施实现层

负责接入具体技术组件：LLM 客户端和模型供应商适配器；数据库连接与持久化实现；LangGraph Checkpointer 配置；地图、天气和搜索 API 客户端；缓存、日志、追踪与监控；外部服务的超时、限流、重试和错误转换。

**要求**：

- 具体 SDK 尽量限制在基础设施层。
- 通过稳定、窄小的接口向上层提供能力。
- 具体实现遵循内层定义的抽象。
- **不得将业务流程编排放入基础设施层。**

LangGraph Checkpointer 可以由启动模块独立注入 Graph，不必强行经过业务 Repository。

### 4.9 `core/`：通用组件

负责真正跨模块的基础能力：配置加载、日志初始化、统一异常类型、追踪标识、通用安全辅助逻辑。

**禁止**将业务逻辑随意放入 `core/` 或不断扩张 `utils.py`。`core/` **不应反向依赖具体业务模块**。

### 4.10 `tests/` 与 `evals/`

| 目录 | 职责 |
| --- | --- |
| `tests/unit/` | 测试纯业务逻辑、参数校验和策略 |
| `tests/integration/` | 测试数据库、外部客户端和 API 集成 |
| `tests/agent/` | 测试 Graph 分支、状态更新、Checkpoint 恢复和人工确认 |
| `tests/evals/` | 存放评测执行代码 |
| `evals/` | 存放可版本管理的评测数据集、案例和配置 |
| `scripts/` | 存放数据初始化和开发运维脚本 |
| `docs/` | 存放架构决策、设计方案和技术说明 |

**不要在多个目录重复维护同一份评测数据。**

---

## 5. 模块依赖方向

```text
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

> 以上图示表示**逻辑关系**，不代表所有模块必须直接导入图中下一层。

**严格遵守以下规则：**

1. `api/` 可以依赖 `services/`、`schemas/` 和 `core/`。
2. `services/` 可以依赖 `agent/`、领域模型及 Repository 抽象。
3. `agent/` 可以依赖 `tools/`、领域模型和通用抽象。
4. `tools/` **不得反向调用 `agent/`**，也不得依赖 `api/`。
5. `domain/` **不得依赖** API、Agent 编排或基础设施框架。
6. Repository 接口由**内层定义**，具体实现由 `infrastructure/` 提供。
7. `infrastructure/` 可以实现内层接口，但**内层不得导入具体基础设施实现**。
8. `core/` **不得依赖** `agent/`、`services/` 等具体业务模块。
9. **禁止循环导入。** 遇到双向依赖时，优先抽取稳定接口或共享领域类型。
10. 具体依赖在 `main.py` 组装，通过构造函数或其他明确的依赖注入方式传递。
11. 业务模块**不得自行创建**难以替换的全局数据库连接、模型客户端或外部服务客户端。
12. **不要为了遵循目录结构而强行让每个请求经过所有层。** 简单逻辑可以保持简洁，但不能破坏核心依赖边界。

---

## 6. 依赖倒置示例

在内层定义 Repository 接口：

```python
# domain/ports/trip_repository.py
from typing import Protocol

from trippilot.domain.models import Trip


class TripRepository(Protocol):
    async def save(self, trip: Trip) -> None: ...

    async def get_by_id(self, trip_id: str) -> Trip | None: ...
```

在基础设施层实现接口：

```python
# infrastructure/persistence/postgres_trip_repository.py
class PostgresTripRepository:
    async def save(self, trip: Trip) -> None:
        """将领域模型持久化到 PostgreSQL。"""
        ...

    async def get_by_id(self, trip_id: str) -> Trip | None:
        """查询数据并转换为领域模型。"""
        ...
```

在应用启动时注入具体实现：

```python
# main.py
trip_repository = PostgresTripRepository(...)
trip_service = TripService(trip_repository=trip_repository)
```

> 以上代码是**结构示意**。实际实现应补全构造参数、类型和异常处理。

`TripService` 应依赖 `TripRepository` **抽象**，而不是直接依赖 PostgreSQL 实现。这样可以在测试时替换为内存实现，或在未来切换数据库。

---

## 7. LangGraph 状态管理约定

明确区分以下三类状态：

### 7.1 图执行状态

定义在 `agent/state.py`，例如：当前用户意图；已提取的目的地、日期、人数和预算；尚未确定的必填槽位；候选行程；工具执行结果；是否需要用户确认。

**只保存工作流推进所需的数据。**

**禁止**把数据库连接、HTTP Request、客户端实例、密钥等放入 Graph State。

### 7.2 对话执行持久化状态

由 LangGraph Checkpointer 按 `thread_id` 保存和恢复。

**要求**：

- 正确配置 Checkpointer 和运行时依赖。
- 验证恢复后能继续执行中断的工作流。
- 对人工确认、工具调用和失败恢复建立测试。
- **不要把 Checkpoint 等同于业务数据库。**

### 7.3 业务数据

包括已确认行程、用户选择、行程记录等，由领域模型和 Repository 管理。

**要求**：

- 业务数据与临时执行状态分开。
- **`thread_id` 只用于定位对话线程，不是身份凭证。**
- **恢复会话前必须验证当前用户有权访问对应线程。**
- 需要持久化的用户选择和已确认行程**不得只存放在临时 Graph State 中**。

---

## 8. Agent 执行与工具调用规范

1. 为工具定义明确的输入和输出 Schema。
2. 对 LLM 输出进行**解析和校验**，不默认其格式、内容或参数一定正确。
3. 对外部调用设置超时，限制重试次数，并区分可重试与不可重试错误。
4. 对有副作用的操作设计**幂等策略**。
5. 对预订、支付等**不可逆操作**，在执行前要求明确的业务确认和权限检查。
6. 工具执行失败时返回**可诊断的结构化错误**，不要无声吞掉异常。
7. 避免重复查询、无界工具调用和无意义的 Agent 循环。
8. 为关键节点和工具调用记录必要的耗时、结果状态及 Token 用量。
9. **不允许模型自行决定权限、实际计费或其他必须确定性执行的安全规则。**
10. Prompt 和工具描述需要**版本管理**，并对重要变更进行回归评测。

---

## 9. 测试要求

**至少覆盖以下场景**（勾选状态见 `docs/quality/test-strategy.md`）：

- [ ] 用户首次提出旅游需求。
- [ ] 用户分多轮补充目的地、日期、预算或人数。
- [ ] 用户修改已经提供的目的地或日期。
- [ ] 用户需求缺失时，Agent 能询问必要信息。
- [ ] 工具成功、超时、异常和空结果。
- [ ] Checkpoint 保存、恢复及中断后继续执行。
- [ ] 人工确认前暂停，确认后继续。
- [ ] 用户无权访问其他用户的 `thread_id`。
- [ ] 行程预算和日期等关键约束得到代码校验。
- [ ] 同一操作重试时，不会产生重复的业务副作用。

**约定**：

- 单元测试应尽量使用 Mock 或 Fake 隔离 LLM、数据库和第三方 API。
- **涉及 Agent 行为的修改，应增加或更新对应评测案例，而不应只依赖人工聊天验证。**

---

## 10. 开发与修改流程

### 10.1 新增功能时

1. 明确功能归属：接口、应用服务、Agent、工具、领域规则或基础设施。
2. 阅读相关模块和现有测试，**优先遵循已有项目约定**。
3. 确认依赖方向，不引入循环导入。
4. **先定义必要的数据结构、接口和错误语义，再实现具体逻辑。**
5. 为关键业务规则和 Agent 分支补充自动化测试。
6. 如果修改影响 Agent 行为，**更新评测案例**。
7. 更新受影响的 README、配置说明和架构文档。

### 10.2 规格先行

动手前先确认四件事：**需求、业务规则、接口契约、验收标准**。
涉及架构变化（新增层、改依赖方向、换技术选型）时，**先给出方案与影响范围，得到确认后再改代码**。

### 10.3 任务拆分

每个任务必须写成可独立验证的最小单元，包含以下七项：

1. **目标**：一句话说明完成后什么变了。
2. **输入与输出**：函数/接口的签名与语义。
3. **允许修改的文件范围**：明确列出，范围外不改。
4. **依赖与非目标**：依赖哪些前置任务；明确这次**不**做什么。
5. **验收标准**：可判定的完成条件。
6. **验证命令**：直接可执行的命令，例如 `make check && make test`。
7. **潜在风险**：数据、并发、外部依赖、兼容性风险。

任务粒度参考：一次提交能在 30 分钟内被审查完。

### 10.4 完成修改后

1. 运行相关单元测试与集成测试。
2. 运行项目已配置的类型检查、格式化和 lint。
3. 检查依赖变更、循环导入、敏感日志及环境变量配置。
4. 汇报修改内容、实际执行的验证命令、测试结果和未覆盖风险。
5. **无法执行某项检查时，明确说明原因，不得声称通过。**

### 10.5 代码审查清单

- [ ] 代码是否位于职责正确的模块？
- [ ] 是否违反第 5 节的依赖方向？
- [ ] 是否引入了不必要的抽象或依赖？
- [ ] 输入校验、异常处理、资源释放是否完备？
- [ ] 是否存在并发、幂等、安全风险？
- [ ] 是否有对应测试？失败路径是否被覆盖？
- [ ] `make check && make test` 是否**真的**通过？
- [ ] 文档（README / docs / AGENTS.md）是否需要同步更新？

### 10.6 并行开发

初始阶段**优先单 Agent 顺序完成基础设施**。只有在以下条件同时满足时才考虑用 Git Worktree 并行：任务边界清晰且互不重叠；接口契约已冻结；每个任务的**文件修改范围互斥**。

**禁止**多个 Agent 同时修改同一核心文件后直接合并。

### 10.7 Skills 与 Hooks 规划

当前阶段**不要求**创建自定义 Skill 或 Hook。后续计划沉淀以下流程（尚未实现）：

| 名称 | 职责 |
| --- | --- |
| `feature-planning` | 需求拆解与实施计划 |
| `feature-implementation` | 按任务契约实现功能 |
| `test-and-evaluate` | 测试与 Agent 评测 |
| `code-review` | 基于 Diff 的代码审查 |
| `project-retrospective` | 基于 Git 历史、测试结果与文档复盘 |

**边界必须分清**：Skill / 提示词负责*指导工作流程*；测试、脚本、Hook、CI 负责*可自动执行的确定性检查*。

**不得用提示词替代本应由程序强制执行的约束。能写成断言的就不要写成叮嘱。**

---

## 11. 安全要求

1. **禁止提交 `.env` 和任何真实密钥。**
2. 只提交不含真实凭证的 `.env.example`。
3. 校验用户输入、工具参数及外部数据。
4. 执行有副作用的操作前，校验用户权限、参数和业务状态。
5. **不得仅凭模型生成的 `user_id` 或 `thread_id` 判断访问权限。**
6. **不记录 API Key、访问令牌或不必要的敏感个人信息。**
7. 对外部检索内容**保持不信任**，避免其覆盖系统指令或触发未授权操作。
8. 敏感信息一律通过环境变量注入，变量名以 `TRIPPILOT_` 为前缀，**只在 `core/config.py` 定义**。
9. 所有重试必须有上限；禁止无上限重试。
10. 配置缺失或自相矛盾时，**启动阶段就要报错**，错误信息要指出具体环境变量名。
11. 新增配置项时必须同步更新 `.env.example` 和 `docs/architecture/overview.md`。

---

## 12. Definition of Done

每项功能完成时，应满足：

1. 代码位于**职责正确的模块**。
2. 依赖方向符合第 5 节约定。
3. 输入、输出和错误行为有明确约定。
4. 关键业务规则**有自动化测试**。
5. Agent 行为变更有**对应回归评测**。
6. 外部依赖具备必要的**超时与错误处理**。
7. 配置和密钥管理符合第 11 节要求。
8. 日志与指标足以定位常见问题，且**不泄露敏感信息**。
9. 文档已同步更新。
10. **实际执行过的验证结果已如实汇报。**
11. `make check` 通过（Ruff lint + format + mypy，**无新增忽略**）。
12. `make test` 通过。

---

## 13. 目标架构与当前实现的差异（迁移清单）

本节是**待办清单**，不是已完成事实。第 3 节的结构是目标，以下是当前仓库与它的差距。

| 项 | 目标 | 当前 | 状态 |
| --- | --- | --- | --- |
| 源码根 | `src/trippilot/` | `src/trippilot/` | ✅ 已迁移 |
| 异常模块 | `core/exceptions.py` | `core/exceptions.py` | ✅ 已改名 |
| 领域模型 | `domain/models.py` | `domain/models.py`（`TripRequest`） | ⚠️ 部分：`domain/itinerary.py` 等行程模型尚未创建 |
| 领域端口 | `domain/ports/` | 仅 `__init__.py` docstring | 待建（第一个 Repository 时） |
| 应用服务层 | `services/` | 仅 `__init__.py` docstring | 待建（第一条业务用例时） |
| Agent 编排层 | `agent/{graph,state,policies}.py` + `nodes/` + `prompts/` | 仅 `__init__.py` docstring | 待建（阶段 3） |
| 工具层 | `tools/{registry,search,weather,maps}.py` | 仅 `__init__.py` docstring | 待建（阶段 2） |
| 基础设施层 | `infrastructure/{llm,persistence,search,observability}/` | 仅 `infrastructure/__init__.py` docstring | 待建（各有真实适配器时） |
| 业务端点 | `api/v1/{chat,trips}.py` | 不存在 | 待建（第一条业务用例时） |
| `repositories/` | **不保留** | 已删除 | ✅ 已删除（见 ADR-0009 修订） |
| `observability/` | **并入 `infrastructure/`** | 已删除顶层包 | ✅ 已删除 |
| 配置目录 | `configs/{app,model}.yaml` | 不存在 | 推迟到有非敏感结构化配置时 |
| 脚本目录 | `scripts/` | 不存在 | 推迟到有第一个脚本时 |
| 测试目录 | `tests/{unit,integration,agent,evals}/` | `tests/{unit,integration,e2e}/` | 部分：`e2e` 保留；`agent/`、`evals/` 待有内容时 |

**迁移原则**：**只移动、重命名或删除已有实际职责的东西；不创建空模块。**
每个目录的存在都必须能回答"它现在的职责是什么"。

**当前 `src/trippilot/` 的实际内容**（其余皆为待建）：

```
src/trippilot/
├── __init__.py
├── main.py                    # 应用工厂 + lifespan + ASGI 入口
├── api/                       # 接口层
│   ├── __init__.py
│   ├── dependencies.py        # RuntimeDep 等
│   ├── errors.py              # AppError → ErrorResponse 映射
│   ├── health.py              # /health、/ready 运维探针
│   ├── middleware.py          # TraceIdMiddleware
│   └── router.py              # 聚合路由
├── core/                      # 通用组件
│   ├── __init__.py
│   ├── config.py
│   ├── exceptions.py
│   ├── logging.py
│   └── runtime.py
├── domain/
│   ├── __init__.py
│   ├── models.py              # TripRequest 及枚举、Budget
│   └── ports/__init__.py      # 占位
├── schemas/
│   ├── __init__.py
│   └── common.py              # CamelModel、ApiResponse、ErrorResponse、探针模型
├── services/__init__.py       # 占位
├── agent/__init__.py          # 占位
├── tools/__init__.py          # 占位
└── infrastructure/__init__.py # 占位
```
