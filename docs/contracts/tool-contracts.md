# 工具契约

> **状态**：**本文档定义契约，尚未有任何实现。**
> `src/trippilot/tools/` 目前只有 docstring。第一个实现将是 Mock。

---

## 1. 为什么需要统一契约

工具是 Agent 与外部世界的唯一接口，也是**事实的唯一来源**。如果每个工具各写各的输入输出、各自处理超时与错误、各自决定要不要标来源，会直接导致三类事故：

1. **模型编造**——工具没返回的字段，模型会自己补一个看起来合理的值。
2. **过期数据被当最新用**——没有获取时间，就无法判断。
3. **一个工具的故障拖垮整个工作流**——没有统一的错误分类与降级策略。

因此：**所有工具，无论 Mock 还是真实，都必须实现同一个 Protocol，并遵守同一套元数据与错误规则。**

---

## 2. 统一接口

```python
from typing import Protocol, runtime_checkable


@runtime_checkable
class Tool[InputT, OutputT](Protocol):
    """所有外部能力适配器的统一接口（尚未实现）。"""

    name: str
    """稳定标识，用于日志、评测与缓存键。例如 "poi_search"。

    一旦发布不得随意更改——评测用例与缓存键都依赖它。
    """

    timeout_seconds: float
    """单次调用超时。必须显式设置，不允许无限等待。"""

    max_attempts: int
    """总尝试次数上限（含首次）。必须有限，且通常不超过 3。"""

    async def run(self, payload: InputT) -> "ToolResult[OutputT]":
        """执行调用。

        成功返回 ToolResult；失败抛 ToolError 的子类（见第 5 节）。
        实现方负责超时、有限重试与错误分类，调用方不需要重复这些逻辑。
        """
        ...
```

**为什么用 `Protocol` 而不是抽象基类**：Mock 与真实实现之间没有代码复用需求，`Protocol` 让两者结构上兼容即可，不强制继承关系。

---

## 3. 输入契约

每个工具有自己的输入模型，但都必须满足：

| 要求 | 理由 |
| --- | --- |
| 是 Pydantic 模型 | 参数错误要在校验层暴露，而不是透传到 Provider 变成 400 |
| `extra="forbid"` | 拼错的参数必须报错，不能静默忽略 |
| 字段带 `description` | 该描述会被转换成 LLM 的函数调用 schema，是工具被正确调用的前提 |
| 不包含平台凭证 | 凭证属于 `core/config.py`，不属于调用参数 |
| 参数可规范化 | 用于构造缓存键与幂等键（如城市名归一、日期归一） |

### 示例：POI 查询

```python
class PoiSearchInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    city: str = Field(min_length=1, max_length=64, description="城市名，例如「长沙」")
    keywords: list[str] = Field(default_factory=list, description="关键词，例如['博物馆','美食街']")
    categories: list[PoiCategory] = Field(default_factory=list, description="类别过滤")
    limit: int = Field(default=10, ge=1, le=50, description="返回条数上限")
```

---

## 4. 输出契约

**所有工具结果都必须被 `ToolResult` 包裹。** 这是不可协商的。

```python
class SourceRef(BaseModel):
    """数据的出处。用户有权知道信息从哪来。"""

    provider: str          # 例如 "mock-poi" / "amap"
    url: str | None = None # 可回溯的原始地址
    license: str | None = None


class ToolResult[DataT](BaseModel):
    data: DataT
    source: SourceRef
    fetched_at: datetime            # UTC
    expires_at: datetime | None     # None 表示不失效
    is_stale: bool = False          # 已过期但无替代数据时为 True


class PoiCandidate(BaseModel):
    """单个景点候选。注意每个事实字段的"可空"语义。"""

    poi_id: str
    name: str
    category: PoiCategory
    address: str | None = None
    location: GeoPoint | None = None
    opening_hours: str | None = None   # None = 未知，不代表"全天开放"
    ticket_price: Money | None = None  # None = 未知，不代表"免费"
    visit_duration_minutes: int | None = None
    indoor: bool | None = None         # None = 未知，不参与"雨天室内"筛选
```

### 四条硬性要求

1. **不确定的字段是 `None`，不是编造的值。**
   `ticket_price=None` 表示"不知道"；`ticket_price=Money(0)` 表示"确认免费"。二者绝不能混。
   下游必须显式处理 `None`（在输出中标注"建议出行前确认"），而不是填入猜测值。

2. **`source` 必须真实。** Mock 的 `provider` 必须是 `"mock-poi"` 这类明确的名字，**不能伪装成真实数据源**。否则评测会得出错误结论。

3. **`fetched_at` 必须是实际获取时刻，不是请求时刻。** 命中缓存时 `fetched_at` 应反映原始获取时间。

4. **`expires_at` 按数据类型设定，不能一律为 `None`。** 参考 `state-model.md` 第 6 节的建议有效期。

---

## 5. 错误分类

**工具不抛 Provider 的原始异常。** 必须归类后抛出，调用方据此决定是否重试。

```python
class ToolError(AppError):
    """工具失败的基类。code 稳定，供调用方与评测断言。"""

    tool_name: str
    is_retryable: bool
    attempts_made: int


class ToolTimeoutError(ToolError):        # is_retryable = True
class ToolRateLimitedError(ToolError):    # is_retryable = True（需尊重 retry-after）
class ToolUpstreamError(ToolError):       # is_retryable = True（5xx）
class ToolInvalidInputError(ToolError):   # is_retryable = False
class ToolNotFoundError(ToolError):       # is_retryable = False
class ToolUnavailableError(ToolError):    # is_retryable = True（服务下线/熔断）
```

| 分类 | 可重试 | 典型原因 |
| --- | --- | --- |
| `ToolTimeoutError` | ✅ | 网络慢、Provider 卡住 |
| `ToolRateLimitedError` | ✅（尊重 `retry-after`） | 超出配额 |
| `ToolUpstreamError` | ✅ | Provider 5xx、网关错误 |
| `ToolUnavailableError` | ✅ | 熔断打开、服务下线 |
| `ToolInvalidInputError` | ❌ | 参数非法、城市名不存在 |
| `ToolNotFoundError` | ❌ | 查询结果为空 |

**`is_retryable=False` 时重试是纯粹的浪费**，必须在实现中短路。

---

## 6. 超时、重试与幂等

### 超时

每个工具必须声明 `timeout_seconds`，且实现中真正生效。建议值：

| 工具类型 | 超时 |
| --- | --- |
| 缓存命中 | 0.1s |
| POI / 静态数据查询 | 3s |
| 天气查询 | 3s |
| 路线规划 | 5s |

### 重试

```
尝试 1 ──失败(可重试)──> 退避 0.5s ──> 尝试 2 ──失败──> 退避 1s ──> 尝试 3 ──失败──> 放弃
```

- **上限固定**（默认 3 次尝试），由 `max_attempts` 声明，**不允许无限重试**。
- 指数退避，建议加入抖动（jitter）避免同时重试造成尖峰。
- **仅对 `is_retryable=True` 的错误重试。**
- 总耗时受预算约束：`max_attempts × (timeout + 退避) ` 不得超过工作流允许的单步预算。

### 幂等

| 工具类型 | 幂等性 | 策略 |
| --- | --- | --- |
| 查询类（POI / 天气 / 路线） | 天然幂等 | 直接重试 |
| 有副作用的操作 | **必须设计** | 幂等键 + 结果记录；执行前查、执行后记 |

当前阶段**不实现任何有副作用的工具**（无预订、无支付）。未来引入时，必须先写 ADR，再写实现。

### 缓存键

```
cache_key = hash(tool_name, normalized_input, 时间窗)
```

- `normalized_input`：城市名归一、日期归一、关键词排序后拼接。
- 时间窗由 `expires_at` 的语义决定（天气 1 小时、景点开放时间 24 小时…）。
- **缓存命中时 `fetched_at` 保持原始值**，这样下游能正确判断时效。

---

## 7. 降级策略

工具重试耗尽后，工作流**不应整体失败**，而应降级：

| 缺失的工具 | 降级行为 |
| --- | --- |
| POI 查询 | 无法生成行程主体 → 明确告知用户"景点信息暂时不可用"，返回不带具体景点的框架性建议 |
| 天气 | 行程照常生成，**不显示天气信息**（而非假装晴天） |
| 路线 | 行程照常生成，通勤时间标注为"待确认"，节奏安排取保守值 |
| 开放时间 | 保留该景点，但标注"请出行前确认开放时间" |
| 票价 | 该项不计入预算合计，并在输出中说明"部分费用未计入" |

**绝对禁止**：工具失败后由 LLM 用记忆补上缺失的事实。

---

## 8. 计划中的工具清单

均为设计草案，尚未实现。

| 工具名 | 输入要点 | 输出要点 | 超时 | 重试 |
| --- | --- | --- | --- | --- |
| `poi_search` | 城市、关键词、类别、条数 | `PoiCandidate[]` | 3s | 3 |
| `poi_detail` | `poi_id` | 开放时间、票价、建议时长、是否室内 | 3s | 3 |
| `weather_forecast` | 城市、日期范围 | 逐日天气、温度区间、降水概率 | 3s | 3 |
| `route_plan` | 起点、终点、交通方式 | 距离、预计时长、备选方案 | 5s | 2 |
| `city_resolve` | 用户写的城市名 | 标准城市名 + 行政区划 | 2s | 2 |

`city_resolve` 单独列出的原因：中文城市名有大量别名与歧义（"星城"→长沙），归一化失败会让后续所有查询失效，值得独立成一个可测试的单元。

---

## 9. 契约测试要求

每个工具实现（Mock 与真实）**都必须**通过同一套契约测试：

```
tests/integration/tools/test_<tool>_contract.py

✓ 输入模型拒绝未知字段
✓ 输入模型拒绝越界值（limit=0、limit=999）
✓ 成功结果携带 source / fetched_at / expires_at
✓ 未知字段为 None 而非编造值
✓ 超时被转换为 ToolTimeoutError 且 is_retryable=True
✓ 400 被转换为 ToolInvalidInputError 且 is_retryable=False
✓ 5xx 被转换为 ToolUpstreamError 且 is_retryable=True
✓ 重试次数不超过 max_attempts（用计数器断言真实调用次数）
✓ 不可重试的错误不发生重试
✓ 缓存命中时 fetched_at 保持原始值
```

这套测试用参数化在 Mock 与真实实现上各跑一遍——这是防止两者契约漂移的唯一可靠手段（见 ADR-0007）。
