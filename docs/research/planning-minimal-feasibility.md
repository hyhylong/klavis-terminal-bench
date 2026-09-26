# 物料短缺后生产重排：最小联合问题的只读可行性判断

2026-09-27。AI 辅助研究备忘录，承接 [candidate-contingency.md](candidate-contingency.md) 的方案 B。**目前建议不把下述最小版本直接开发成第四个完整难题。** 它有真实业务含义，但列出的约束都能直接映射到普通 CP-SAT 模型，尚未找到足以支持本地难度预期的额外编码障碍。第三版迁移任务已经正常得到 Codex 23/23；这次先做廉价反证，不继续投入完整环境和评测矩阵。

本文只阅读了官方通用求解器文档和制造产品文档，未访问或复制现成 benchmark 的实现、测试数据或解答；下方数字为本次自行构造的说明例。没有实现求解器、生成任务、运行 Docker 或调用模型 API。**仍等待用户确认真实领域偏好与业务语义。已有类别的 0/5 不是这个原创问题的本地失败证据。**

## 1．先找捷径，再决定是否值得做

Google 的普通 job-shop 教程已覆盖工序先后关系、机器互斥和整数时间区间。设备备选、条件约束、绝对偏差和最大值也有公开 API。这使本问题可用少量变量族与约束循环表述，无需自写搜索算法。[官方 job-shop 教程](https://developers.google.com/optimization/scheduling/job_shop)、[CP-SAT Python API](https://or-tools.github.io/docs/pdoc/ortools/sat/python/cp_model.html)。

| 业务要求 | 通用建模捷径 |
| --- | --- |
| 每道工序选一台合格设备 | 每个备选设备一个布尔变量和 optional interval；`add_exactly_one` |
| 同设备不能重叠、两道工序按序完成 | 每台设备一个 `add_no_overlap`；`end(prep) <= start(finish)` |
| 已开工不可挪动 | 直接固定设备、开始和结束；把其区间加入同一机器约束 |
| 剩余物料批次分配 | 整数 `x[operation,lot]`；需求等式、批次数量上界 |
| 有分配才须等该批到货 | `x>0` 对应布尔量；仅在该布尔量成立时约束 `start >= available_at` |
| 交付延误与原计划扰动 | `max(0,end-due)`、`abs(start-baseline_start)`；设备改派由布尔量计数 |

这些映射是对下述原创合同的建模推导，不是已经运行过的解法。最容易遗漏的是正分配与可用时间的连接；它仍然只是普通条件约束。分三次求解即可处理字典序目标：先求第一项目标的最优值并固定，再处理第二、第三项。若前一阶段只找到可行值，不能把固定该值后的结果称为全局字典序最优。任意选一个“大权重”也不能保证目标等价。

三条可选路线：

1. **推荐的低成本核验路线：** 若用户最终确认这个领域，优先尝试最朴素的 CP-SAT 联合模型与独立检查器；先观察它是否迅速覆盖全部小例。本轮仅完成可行性筛查，未实现。
2. 先按交期分料，再分别排设备：实现更简单，但会把“谁值得拿早到批次”提前决定，可能牺牲交付目标；适合作为弱基线，不适合作为正确性标准。
3. 时间展开 MILP：也能表达同样合同；通常变量更多，但同样是合法解法。不能禁止它、禁止 CP-SAT 或要求复现作者内部算法来制造难度。

**当前判断：通用例程加少量约束已经覆盖这个最小版本的建模结构，建议放弃它作为“必然比前三版更难”的候选。** 这不等于证明任何规模都求解很快；本轮没有测运行时间。若后续只能通过扩大实例、压低时间上限或追加几十条无关规则使模型失败，应停止。真实用户工作流若确有新的核心耦合，应先确认事实，再重新判断，不从困难类别名称倒推需求。

## 2．最小而真实的业务切片

一个小型按单装配单元：每单先加工专属半成品 `prep`，再做最终装配 `finish`。供应到货短缺后，早到批次不够原计划使用；新计划必须同时决定剩余料分给谁、在哪台设备何时加工，并尊重已开工的实际工作。

材料和产能必须同时可用才开工，是制造排程中的实际问题；库存不足时给竞争订单确定优先分配也有产品支持。[Microsoft 有限材料与产能排程说明](https://learn.microsoft.com/en-us/dynamics365/supply-chain/production-control/operations-scheduling)、[Odoo 物料/产出分配说明](https://www.odoo.com/documentation/18.0/applications/inventory_and_mrp/manufacturing/reporting/allocation.html)。这些来源支持业务背景，不证明本题困难，也不意味着下列冻结和目标偏好是所有工厂的统一规则。

此最小切片只保留三个相互作用：

- **物料：** 同种物料可以从多个剩余批次取整数数量，某批次不能重复分配；所取全部批次须在工序开始时已可用。
- **工序和设备：** 每单两道非抢占工序；半成品在 `prep` 结束时才可供该单 `finish` 使用；合格设备可能有不同处理时长。这里的半成品归该订单专用，**没有跨订单半成品池或可替代 BOM**。
- **冻结和代价：** 实际已经开始的工序保留完整区间及设备；未开工的工序可重新分配。优先减少加权延误，再减少原计划移动和改机。

输入是扰动发生后经过确认的单次快照，不要求同时实现 ERP/MES 数据清洗、事件消费或线上服务。没有模糊 CSV 匹配、隐含时区、设备故障后的续作、随机加工时长、班次、换型、保质期、外协或拆单。省略这些是为了定位最小问题；它也显著降低了任务的工程难度。

## 3．可公开的精确候选输入输出

以下是**可讨论的完整小问题合同**，尚未实现或经过实测，也不是资源校准结果。暂定接口为 `python -m replan INPUT.json OUTPUT.json`，成功返回 0 并写一个 UTF-8 JSON 对象。有效输入保证在给定 horizon 内可行，且能达到公开质量上限；不会要求提交者用不可核验的字符串声称 `INFEASIBLE`。输入不满足这项保证是作者/设施问题。

时间为从同一班次原点起的整数时间格，每格 5 分钟；不存在四舍五入。区间均为 `[start,end)`，结束与下一道开始相等合法。整数必须是真正 JSON 整数，布尔值不算整数。对象不接受未声明字段；JSON 重复键拒绝；数组顺序仅在每单的两道工序中有含义。

为使这个草案的输入范围明确，限定 1–16 单、1–8 台机器、0–32 个剩余料批、最多 8 种物料；`1 <= horizon <= 10000`，`0 <= now < horizon`。数量和权重为 1–1000，剩余批次数量也允许 0；这些是小问题边界，不是通过性能试验得到的难度设置。所有 ID 是 1–32 个 ASCII 字母、数字、`_` 或 `-`；不同实体集合分别唯一，工序 ID 在全输入唯一。

| 字段 | 精确定义 |
| --- | --- |
| `schema_version` | 整数 `1` |
| `instance_id` | 输入身份；输出必须相同 |
| `now`, `horizon` | 快照时间和最后允许完工时间；所有历史/计划时间在 `0..horizon` |
| `machines` | 机器 ID 数组；每台机器同时最多加工一道工序 |
| `lots` | `{id, material, available_at, free_quantity}` 数组；`free_quantity` 已扣除所有已开工工序的领料，并反映短缺后的真实剩余量；未开工旧预留全部可重分 |
| `orders` | `{id, due, weight, operations}` 数组；全部订单必须完成，不可丢弃，`due` 在 `0..horizon` |
| `operations` | 每单恰好两项，先 `prep` 后 `finish`；每项 `{id, requirements, modes, baseline, actual}` |
| `requirements` | `{material, quantity}` 数组，同一工序不重复物料；固定数量在工序开始时一次消耗，无损耗、退料、替代料；空数组合法 |
| `modes` | `{machine, duration}` 非空数组；每台合格机器至多一项，`1 <= duration <= horizon`；处理时长已包含该固定工序的全部工作 |
| `baseline` | `{machine,start}`，机器属于 `modes`，开始时间在 `0..horizon`；只是扰动前计划及扰动代价基准，可因当前缺料失效 |
| `actual` | 未开工为 `null`；已开工为 `{machine,start,end}`，与一个 mode 时长一致，`start <= now`；已完工或正在加工都必须原样保留 |
| `accept_at_most` | 三个非负整数 `[L_max,D_max,S_max]`；按下述字典序比较的公开质量上限，不是三个独立上限，也不是自动成立的最优性声明 |

有效输入中的历史实际区间本身不冲突，符合工序先后关系。一个订单的 `finish` 已开工时，其 `prep` 必已完成。历史领料由快照确认，不让求解者恢复或重新扣减；对 `actual != null` 的工序，输出不得再创建新的物料分配。对每个未开工工序 `o`，必须 `start_o >= now`。

输出的确切形状：

```json
{
  "schema_version": 1,
  "instance_id": "shortage-example",
  "operations": [
    {"id": "W-prep", "machine": "P1", "start": 8, "end": 12},
    {"id": "W-finish", "machine": "F", "start": 12, "end": 14},
    {"id": "A-prep", "machine": "P1", "start": 12, "end": 14},
    {"id": "A-finish", "machine": "F", "start": 14, "end": 16},
    {"id": "B-prep", "machine": "P1", "start": 16, "end": 18},
    {"id": "B-finish", "machine": "F", "start": 18, "end": 20}
  ],
  "allocations": [
    {"operation": "A-prep", "lot": "early", "quantity": 2},
    {"operation": "B-prep", "lot": "late", "quantity": 2}
  ],
  "objective": {"weighted_tardiness": 2, "start_shift": 8, "machine_changes": 1}
}
```

`operations` 必须精确覆盖输入的每道工序一次，包含历史实际工序；数组可任意排列。每个 `(operation,lot)` 最多一个分配项，数量为正整数；只允许给未开工工序分配其需求物料。允许一需求拆到多个批次，允许同一批次分给多个工序，但总量不能超过剩余量；不要求 FIFO，也不要求“整批只能给一单”。不存在未输出的默认分配。

设 `U` 是输入中未开工工序集合，`C_j` 是订单 `finish` 的结束时间，`b_o`、`m_o^0` 来自 baseline。独立重算：

\[
L=\sum_j w_j\max(0,C_j-d_j),\qquad
D=\sum_{o\in U}|s_o-b_o|,\qquad
S=\sum_{o\in U}[m_o\ne m_o^0].
\]

质量按 `(L,D,S)` 字典序越小越好；通过条件是可行且 `(L,D,S) <= accept_at_most`。提交的 `objective` 必须与重算值完全一致。更好的合法计划总应通过，不比较作者计划的设备选择或排序。三个优先级是本稿假设，真实用户可能更在意换线成本、交付承诺或总产出，尚未确认。

## 4．一个原创手算例：确有耦合，但不构成困难证明

下面是上方输出的完整输入，既可表达短缺，也包含一个不可挪动的在制工序。它只用于定义和手算，不是从任何 benchmark 提取的数据。

```json
{
  "schema_version": 1,
  "instance_id": "shortage-example",
  "now": 10,
  "horizon": 30,
  "machines": ["P1", "P2", "F"],
  "lots": [
    {"id": "early", "material": "R", "available_at": 10, "free_quantity": 2},
    {"id": "late", "material": "R", "available_at": 16, "free_quantity": 2}
  ],
  "orders": [
    {"id": "W", "due": 14, "weight": 3, "operations": [
      {"id": "W-prep", "requirements": [{"material": "R", "quantity": 2}], "modes": [{"machine": "P1", "duration": 4}], "baseline": {"machine": "P1", "start": 8}, "actual": {"machine": "P1", "start": 8, "end": 12}},
      {"id": "W-finish", "requirements": [], "modes": [{"machine": "F", "duration": 2}], "baseline": {"machine": "F", "start": 12}, "actual": null}
    ]},
    {"id": "A", "due": 16, "weight": 5, "operations": [
      {"id": "A-prep", "requirements": [{"material": "R", "quantity": 2}], "modes": [{"machine": "P1", "duration": 2}, {"machine": "P2", "duration": 3}], "baseline": {"machine": "P1", "start": 12}, "actual": null},
      {"id": "A-finish", "requirements": [], "modes": [{"machine": "F", "duration": 2}], "baseline": {"machine": "F", "start": 14}, "actual": null}
    ]},
    {"id": "B", "due": 18, "weight": 1, "operations": [
      {"id": "B-prep", "requirements": [{"material": "R", "quantity": 2}], "modes": [{"machine": "P1", "duration": 2}, {"machine": "P2", "duration": 3}], "baseline": {"machine": "P2", "start": 10}, "actual": null},
      {"id": "B-finish", "requirements": [], "modes": [{"machine": "F", "duration": 2}], "baseline": {"machine": "F", "start": 16}, "actual": null}
    ]}
  ],
  "accept_at_most": [2, 8, 1]
}
```

已经领走的 `W-prep` 两单位料不在两批 `free_quantity` 内，不能再扣一次。`W-prep` 占用 P1 到 12；W 的装配随后占用 F 到 14。把早到料给 A、晚到料给 B，就得到上方计划：仅 B 延误 2，未开工开始时间位移为 `6+2=8`，B 的加工从 P2 改派 P1，故目标 `(2,8,1)`。

一个不依赖求解器的下界证书如下：

1. 若 A 使用任何晚到料，其加工最早 16 开始，至少还需 `2+2` 时间，A 的加权延误至少 `5×(20−16)=20`。
2. 因而任何 `L<20` 的解都必须将 early 的两单位全部给 A。B 必须使用 late，完工不早于 20，所以 `L>=2`。这一步也覆盖“early 拆给 A/B”的情况：只要 A 不足两单位早料，它仍须等晚料。
3. 在 `L=2` 下，B 必须于 20 完工，且只能用时长 2 的 P1；其两个开始时间只能是 16 和 18。相对 baseline 的位移至少 `|16−10|+|18−16|=8`，且至少有一次改机。其余工序位移非负。
4. 已给计划同时达到这三个下界，因此本小例的字典序最优值确为 `(2,8,1)`。

这说明先随手分料再排程可能浪费紧缺早料，冻结区间也不能删掉；同时，下界只有几步算术，**恰好说明最小真实例可以很容易**。

## 5．独立可行性检查与目标证书

检查器只读可信输入及提交 JSON，用独立的整数算术验证，不导入提交者或参考求解器的 Python，不复用它的 CP-SAT 建模函数，也不执行提交者声称的证明代码。

依次检查：严格 JSON 类型/ID/覆盖关系；每道工序的 mode 与 `end=start+duration`；历史 actual 完全不变；未开工不能早于 now；两阶段先后关系；每台机器按开始时间排序后相邻区间不重叠；每个需求的分配数量恰好满足；每批总分配不超量；每个正分配的料种正确且 `available_at <= operation.start`；最后重算 `(L,D,S)` 并和公开上限比较。因为本合同只在开始时一次领料，每批只有一个可用时间、没有回流或中途新增生产，**不需要每个时间格重放库存**；逐分配就绪检查与批次总量检查已足够。若后来增加半成品共享池，这个简化便不能原样沿用。

要区分三种证据：

- **可行性与目标值证书：** 输出的完整排程和分配就是可检查见证，独立算术证明它达到所报目标；它仅给出最优目标的一个可行上界。
- **严格最优性证书：** 需要独立下界与该上界相等。小例可用上面的分情况不等式，或由另一种实现枚举所有有限机器选择、分配和整数开始时间。枚举昂贵，所以只能用于刻意保留的小例；不能把“大模型自称最优”替换成独立证书。
- **正式质量阈值：** 若将来确要做任务，每个实例的公开 `accept_at_most` 都须有独立核验过的可行见证；若声称它是最优，还须提供匹配的下界依据。若下界做不到，可明确只要求可检查质量阈值，或放弃该实例，不能暗中比较作者唯一答案。

CP-SAT 的 `OPTIMAL` 状态也可能表示达到了配置的 gap limit；整数目标需结合实际 bound 和参数检查，不能信任提交 JSON 中自报的 status/bound。三个字典序层级的最优性也必须逐级建立。[官方响应定义](https://raw.githubusercontent.com/google/or-tools/stable/ortools/sat/cp_model.proto)、[官方 gap 参数说明](https://raw.githubusercontent.com/google/or-tools/stable/ortools/sat/sat_parameters.proto)。同一份模型交给同一求解器再跑一次，可以交叉核对，不能声称是不同实现的独立证明。

官方当前 LRAT/DRAT 参数文档对证明输出/检查注明了纯 SAT 等适用限制；本稿的整数和区间模型不能直接被宣称已有通用、独立可检查的求解证明。另做 SAT 编码与证明检查会成为新的工程项目，不能悄悄塞给生产计划任务。[官方证明参数说明](https://raw.githubusercontent.com/google/or-tools/stable/ortools/sat/sat_parameters.proto)。

检查器自身的低成本审核可先手工构造四个反例：把 B 的一单位 late 料安排在 16 前消耗、复用 early 的容量、挪动 W 的实际区间、伪报目标值；还要接受同目标的不同合法设备/排序。正式阶段再考虑 ID 重命名、整体时间平移、输入数组重排、放宽交期等不应破坏语义的变换。此处仅提出检查思路，没有实现或跑测试。

## 6．继续与停止的条件

用户尚未确认：是否关心按单装配还是共享半成品批产；开工后哪些承诺不可变；短缺时优先保交期、保产量还是减少改计划；是否需要解释为什么某单被延后。这些真实选择会影响模型，不能由排行榜失败类别替用户决定。

基于当前的通用建模捷径风险，暂不开发这个最小版本。即使用户选择制造领域，也先给通用 CP-SAT 路线充分机会；若标准建模即可覆盖，应接受它作为合法解，并放弃把这个最小版本包装成高难度 benchmark。只有真实业务需要且无法被当前小模型表达的核心问题，才值得另作范围明确的设计。**本轮没有本地模型失败、求解性能测量或新任务完成声明。**
