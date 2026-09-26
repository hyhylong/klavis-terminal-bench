# 当前前沿模型的任务级失败证据补充

研究日期：2026-09-27（Asia/Shanghai）。这是公开结果的只读提取和设计判断；没有运行模型，没有复制现成任务的实现、数据或答案，也没有改动本地候选。

截至本次核验，官方当前版本已是 **Terminal-Bench 4.0**。因此不能用 TB2/TB3 的历史低分预测当前 Astra。当前官方数据确实包含 Astra 的任务级结果：Codex / GPT-6 Astra 的 max 行有 **19 个任务 0/5**，xhigh 行有 **20 个任务 0/5**。但与本地候选最接近的 WAL 恢复和 KV 修复均为 **5/5**，MVCC 压缩为 **4/5**。这些结果反对“加入持久化、重启、压缩就必然足够难”的假设。[当前官方排行榜](https://www.tbench.ai/)、[官方任务级图表数据](https://www.tbench.ai/api/waffle?version=4.0)。

## 版本、模型和预算

| 项目 | 本次核验的范围 |
| --- | --- |
| 数据集 | `terminal-bench/terminal-bench/4-0-0`，66 个任务 |
| max 行 | `5c537be4-7fc3-449b-8bfc-ceb9061c2535`，Codex / GPT-6 Astra / max |
| xhigh 行 | `16db8ad5-84aa-4588-b660-1ce68c0d45e2`，Codex / GPT-6 Astra / xhigh |
| 行元数据日期 | 2026-09-03；两行最后更新于 2026-09-10 |
| 重复数 | 每行每题 5 次，共 330 次；两行合计 660 次 |
| max 结果 | 192/330，58.18%；19 题 0/5 |
| xhigh 结果 | 191/330，57.88%；20 题 0/5 |
| 失败标签 | 两行的 660 次记录只有 `p`/`f`；没有 timeout/error 标签 |
| 官方任务执行上限 | 8 小时；不等于实际每次耗时 |
| 本地候选执行上限 | 2 小时；仍需自己的正常试跑 |

TB4 将执行上限统一为 8 小时，修复了 19 个任务，并移除了 8 个任务；移除原因包括饱和、拒绝、公开解答和质量/平台问题。版本变化涉及任务和资源，官方要求重新运行。**8 小时结果不能直接替代本题 2 小时评测。** 未核验出可与本地完全对齐的逐次工具调用、上下文或 token 上限，也不能假设 Codex CLI 版本和运行环境相同。普通 `f` 标签只证明计分失败，不能证明轨迹内没有环境问题或验证器问题。[TB4 官方发布说明](https://www.tbench.ai/news/terminal-bench-4-0)。

## 哪些类别在这两行更常失败

下表沿用官方 `doms[].name` 分类，不根据标题猜测新类别。数字是成功 trial 数/总 trial 数；括号内是该类别 0/5 的任务数。

| 官方类别 | Astra max | Astra xhigh |
| --- | --- | --- |
| Security | 22/25（0） | 20/25（1） |
| ML | 37/55（2） | 38/55（2） |
| Hardware | 16/25（1） | 18/25（1） |
| Software | 55/90（4） | 51/90（5） |
| Media | 13/20（1） | 14/20（0） |
| Science | 30/70（7） | 31/70（6） |
| Operations | 19/45（4） | 19/45（5） |

两行共同 0/5 的任务如下。它们是检索线索，不是已经完成的失败原因分析。

| 官方类别 | 两行共同 0/5 的任务名 |
| --- | --- |
| ML | `sglang-qwen-burst`、`vllm-deepseek-streaming` |
| Hardware | `freecad-impeller` |
| Software | `react-lead-form`、`bun-sourcemap-leak`、`data-anonymization`、`ontology-kg-querying` |
| Science | `atrx-vep-crispr`、`gsea-proteomics`、`roy-polymorph-cn`、`protein-autointerp-disulfide`、`foodstuff-beta-activity`、`glycan-ms2-elucidation` |
| Operations | `production-planning`、`medical-claims-processing`、`cargo-flight-dispatch`、`freight-dispatch-shift` |

另外，max 的 0/5 包含 `music-harmony`、`lake-temp-glm`；xhigh 的 0/5 包含 `html-js-filter`、`vba-userform-port`、`intrastat-meldung`。不能把 Science/Operations 的较低通过率解释为这些行业本身“普遍难”：这是经过选择、规模有限的 benchmark，而非真实工作抽样。[以上分类和计数均直接来自官方任务级数据](https://www.tbench.ai/api/waffle?version=4.0)。

## 存储、数据库、长期状态一致性：反证应优先

| 对照任务 | max | xhigh | 能支持的有限结论 |
| --- | --- | --- | --- |
| `wal-recovery-ordering` | 5/5 | 5/5 | WAL 恢复题名本身不足以预测失败 |
| `kv-live-surgery` | 5/5 | 5/5 | KV 修复同样不能直接当作困难类别 |
| `pretrain-shard-corruption` | 5/5 | 5/5 | 数据损坏/恢复题也存在稳定成功样本 |
| `mvcc-lsm-compaction` | 4/5 | 4/5 | 有失败，但远非三次必败的证据 |
| `distributed-dedup` | 3/5 | 3/5 | 有重复失败，也有多次成功 |
| `session-window-debug` | 3/5 | 2/5 | 状态相关调试并未稳定阻止求解 |
| `live-database-cutover` | 1/5 | 1/5 | 相关系统工程中较强的失败信号；不是 0/5 |
| `production-planning` | 0/5 | 0/5 | 跨系统业务一致性和全局计划，不能归类为崩溃恢复 |

上述存储相关名称只是选取对照的依据；除下述两题外，本研究没有查看其任务实现来推断内部机制。**未找到两行均 0/5、且经本次作者描述核实为 WAL/持久化/历史重放修复的样本。** `data-anonymization`、`ontology-kg-querying` 虽与数据有关，也不能仅凭标题改标为长期存储一致性失败。[对照分数来源](https://www.tbench.ai/api/waffle?version=4.0)。

`production-planning` 的作者难度说明明确涉及 ERP/MES/WMS 之间的订单、物料、库存批次、产线能力、在制品、班次及时间约束。我的机制推断是：局部可行的选择合在一起可能无法满足资源和交付要求，需要全局一致的计划。**0/5 是实测结果；“全局约束耦合导致失败”目前只是作者难度说明支持的假设，未经 Astra 轨迹验证。** [作者难度说明，固定 v4.0.0](https://github.com/harbor-framework/terminal-bench/blob/v4.0.0/tasks/production-planning/README.md)。

`live-database-cutover` 的作者说明涉及持续读写期间的跨数据库切换，外键关系，以及查询语义和延迟同时保持。我的机制推断是：它要求协调系统仍在变化时的数据一致性、服务行为和跨引擎语义，区别于有限输入的离线 replay。**1/5 并不证明其中任何单一约束就是失败原因。** 两个 README 页首仍有旧 timeout 数字，但 changelog 均写明升至 8 小时；本研究采用 TB4 统一预算。[作者难度说明，固定 v4.0.0](https://github.com/harbor-framework/terminal-bench/blob/v4.0.0/tasks/live-database-cutover/README.md)。

## 对当前原创候选的影响

当前 durable-ledger-repair 的难度仍未证明。它有真实的状态一致性问题，但公开结果更支持谨慎校准，而不是继续堆规则、增加数据量或缩短时间。已有候选应先完成自己的正常试跑；简单合法重写若通过，就是难度假设的反证。

如果当前候选再次被稳定解出，值得另行设计的是“需要同时满足多组件约束的可验证工程交付”，而不是复制上面任何任务：例如原创、有限状态的持续写入升级演练，要求所有允许的故障切点保持可观察行为；或有可独立验证证书的跨系统全局计划。前者与 cutover 的低成功信号相关，后者与 planning 的 0/5 相关；二者都只是待实验假设。必须先证明独立参考方案、资源余量和公开合同清楚，不能凭相关性声称能让目标模型三次失败。

## 可复现提取记录

本次只读取官方页面元数据、公开计分数据及作者 README 的难度说明，不抓取任务实现、解答或轨迹内容。

| 字段 | 值 |
| --- | --- |
| 最后实际读取时间（UTC） | `2026-09-26T20:09:13.754243+00:00` |
| 最后实际读取时间（Asia/Shanghai） | `2026-09-27T04:09:13.754243+08:00` |
| API 自报 `source.fetched_at` | `2026-09-26T20:06:00.738Z` |
| HTTP 响应体 SHA-256 | `bdeae9cc6bef16803240ed0ebd8aeb244705c9c2a152ff2529c20f00289065b1` |
| 完整响应记录量 | 27 行，66 题，8910 次 trial |
| 计分规则 | API 的 `score_policy`：`reward > 0` 与 Harbor Hub accuracy 一致 |
| 轨迹字段 | `source.include_trajectories = false` |
| max job ID | `0f01715e-2f98-40e3-836f-1ac4fdce39a4` |
| xhigh job ID | `caf6e433-9fff-4475-b0bc-977f14ac7052` |

从官方首页的服务器渲染数据读取完整 row ID、模型、effort 和日期；官方首页图表引用的 `/api/waffle?version=4.0` 提供每次结果。下面只解析 JSON，不执行页面脚本。短 `r` 是完整 row ID 的前八位；用两个独立行筛选，避免把 max 和 xhigh 混合。端点为动态快照，后续 hash 变化应记录新版本，不能强行当作本次原始字节。

实际执行了下面的文档内代码，132 个任务/模型组合均满足五次记录与模型名称断言，计数与本文一致。前次读取于 `2026-09-26T20:05:57.979623Z`，API 自报时间为 `2026-09-26T19:58:06.965Z`，响应 hash 为 `6121b67352bc4ba874a37fbf0b8e53243021663bfeb1c56ca8d592e37fe7a47a`；此次刷新后字节 hash 改变，本文所用的两行逐题计数和标签未变。

```python
from collections import Counter
from datetime import datetime, timezone
import hashlib
import json
import urllib.request

url = "https://www.tbench.ai/api/waffle?version=4.0"
with urllib.request.urlopen(url, timeout=30) as response:
    raw = response.read()
data = json.loads(raw)
print("retrieved_at", datetime.now(timezone.utc).isoformat())
print("source", data["source"])
print("sha256", hashlib.sha256(raw).hexdigest())
print("counts", {k: data[k] for k in ("row_count", "task_count", "trial_count")})
print("score_policy", data["score_policy"])

for row, label in [("5c537be4", "Astra max"), ("16db8ad5", "Astra xhigh")]:
    total, zero = Counter(), []
    for domain in data["doms"]:
        domain_counts = Counter()
        for task in domain["tasks"]:
            trials = [t for t in task["ts"] if t["r"] == row]
            assert len(trials) == 5, (label, task["task"], len(trials))
            assert all(t["m"] == "GPT-6 Astra / Codex" for t in trials)
            counts = Counter(t["o"] for t in trials)
            domain_counts.update(counts)
            print(label, domain["name"], task["task"], dict(counts))
            if counts["p"] == 0:
                zero.append((domain["name"], task["task"]))
        total.update(domain_counts)
        print("domain", label, domain["name"], dict(domain_counts))
    print("total", label, dict(total), "zero", len(zero), zero)
```

任务级结果证据已经找到，**当前 Astra 的因果轨迹分析尚未完成**。公开 Hub trial 页有试验元数据和轨迹路径，但本次未提取轨迹正文；不能把 `include_trajectories=false` 说成“轨迹不公开”。0/5 也只是五次观察，不代表未来必败；这里的观察既不能替代本地两小时重复试验，也不能将环境/模型/预算不一致的运行合并计数。
