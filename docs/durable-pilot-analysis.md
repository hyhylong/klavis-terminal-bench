# 第二版 Codex 成功试做分析

第二版 `durable-ledger-repair` 的难度假设已被一次真实正常试做否证。Codex / GPT-6 Astra / xhigh 修复后获得 reward 1，独立验证器 26/26 通过，无执行异常。保留该成功作为反证，停止为这个候选追求六次正常失败和两次对抗零奖励；不把安装错误或此次成功重新归类为失败。单次试做不估计模型总体成功概率，但足以否定把当前候选当作已达到所需难度的判断。

## 已核验的证据

| 项目 | 记录 |
| --- | --- |
| Job | `standard-codex-20260926T200419294708Z` |
| Trial | `durable-ledger-repair__Z3p4gpg` |
| 模型与代理 | `openai/gpt-6-astra`，xhigh，Codex CLI 0.157.1 |
| 冻结版本 | `durable-ledger-repair-20260926T200157076022Z` |
| Harbor task checksum | `52200606da8644eb9d948784f20b1369bafcaea4702d0190f0e03f1a4708b957` |
| 控制对应关系 | 与 `durable-oracle-v3` / `durable-nop-v3` 相同 checksum |
| 独立验证 | reward 1；`exception_info=null`；preflight passed；26 passed、0 failed、0 skipped |
| 整个 job 耗时 | 483.338 秒，约 8 分 3 秒 |
| agent 执行耗时 | 410.030 秒，约 6 分 50 秒；任务允许 7200 秒 |
| 私有性能种子 | `1657691945` |
| 三次 stream 秒数 | 0.344291、0.369361、0.364649 |
| stream 中位数 / 上限 | 0.364649 / 3.0 秒，约有 8.2 倍余量 |

紧凑记录见 [durable-codex-pilot.json](../artifacts/validation/durable-codex-pilot.json)。它按字段白名单保存结果、计数、时间和来源 SHA-256，没有复制原始 config、环境变量、凭据或轨迹正文。原始 trial、CTRF、性能报告、preflight、完整轨迹及提交文件仍保留在本地被忽略的 `artifacts/jobs/` 下。

## 轨迹显示它如何完成

ATIF 有 19 条记录，其中 14 条来自 agent，包含 13 个外层 `exec` 工具调用。外层调用会批量执行多个内部工具，这些数字不能当作模型轮数或 shell 命令总数。

| ATIF 步骤 | 可观察动作和结果 |
| --- | --- |
| 6–9 | 读取公开接口、存储规范、全部实现以及公共测试/基准工具 |
| 10 | 运行 smoke，直接复现 null amendment 后缓存未清除、撤回最新 amendment 后旧 winner 丢失两项错误 |
| 11 | 明确选择保留所有 eligible amendment、同时失效修改前后的实体，并从 durable source 重建内存索引；修复 projection。一次 `store.py` patch 格式错误在下一步恢复 |
| 12 | 将 `store.py` 简化为源存储加内存索引，四项 smoke 全部通过，距离 agent 开始约 101 秒 |
| 14 | 新增八个回归测试全部通过，包含随机交付前缀、历史读取及逐文件操作崩溃点 |
| 15–16 | 用自行编写的独立逐点 replay 比较两个种子的 4320 次 streaming lookup 和最终 snapshot，全部匹配 |
| 18 | 第二个公开种子的 benchmark 中位数 0.361804 秒；第一个是 0.376169 秒 |
| 19 之后 | agent 完成；随后独立 verifier 在其私有种子和全部用例上通过 |

测试通过来自工具观察和独立 CTRF，不只来自 agent 的最终自述。轨迹中的 patch 语法错误及一次非 Git 目录查询失败均已恢复，没有成为 trial exception，也不构成模型失败证据。

## 实际修复范围为何很小

把提交与运行所用的冻结 starter 按字节比较，只有 `projection.py`、`store.py`、`FORMAT.md` 改动，并新增 `tests/test_regression.py`。`domain.py`、`storage.py` 和 `__init__.py` 完全相同。两份执行代码的文本 diff 合计增加 24 行、删除 102 行，计数包含注释；新增测试独立计算。

1. **困难的基础层已经正确。** 200 行领域实现和 185 行 durable source 实现保持原样，继续承担历史重放、格式兼容、WAL、fsync 和 generation 发布。大量 crash tests 验证的是 agent 没有破坏已有能力，未要求它重新解决这些算法。
2. **实时索引只需两处局部修复。** 提交在 `projection.py` 保存每个 target 的全部 amendment candidates，移除 winner 时重新取最大候选；刷新前先记录旧有效动作所属实体并标脏，刷新后处理新有效动作。逐实体重放及大部分依赖框架原本已经存在。
3. **跨重启的缓存问题可以合法删除。** 公开 SPEC 第 28 行与 FORMAT 开头明确允许丢弃 derived cache；全部 source history 又始终完整。提交把 `store.py` 从 73 行减到 30 行：每次 open 由源事件重新建立 `ProjectionIndex`，继承正确的 source `compact()`，删除 cache 序列化/恢复路径。
4. **性能合同没有重新耦合启动与实时路径。** SPEC 第 178 行明确将 prefix loading、compaction、reopen 排除在计时区间外。这是公开合法合同，agent 据此保留启动时重建和增量实时查询。它不是每个查询全量 replay；现成的逐实体脏标记已足以留下约 8.2 倍性能余量。
5. **故障定位成本很低。** 公共 smoke 精确揭示两项失效模式；完整源码和明确接口使 agent 在约一分钟后即可给出修复策略。公开复现是任务公平性的优点，不能用隐藏它来补救难度不足；根本问题是暴露出的修复仍然局部、可删除且有成熟支撑代码。

这与 starter 提案预先列出的风险一致：候选可能成为“保留候选集合、失效旧实体、丢弃可选缓存”的小修复。理论上的 lineage/cache/durability 相互作用没有变成必须同时修改和验证三个独立子系统的工作。

## 验证边界和后续决定

本分析确认的是这个冻结任务上一次真实成功。26/26 不证明验证器覆盖一切，也不替代 implementation rubric；独立审查确认为 **23 pass、11 fail、1 N/A**，发现和逐项结论见 [rubric 分析](durable-rubric-analysis.md)。审查实际演示了存储写入格式的覆盖不足，但不能据此取消本次成功：提交的 `storage.py` 与冻结 starter 完全相同，成功路径没有通过改变存储编码来利用该缺口。审查 meta-task 的 reward 1 仅表示有 verdict 文件，不表示题目通过 35 项规则。

当前候选不再投入正式六次失败、两次对抗的完整评测预算，保留所有控制、失败的基础设施运行和成功轨迹。第一版两模型成功与第二版本次成功都进入任务筛选证据，不擦除、不包装成“验证完成”。

后续若另选原创工程任务，应先确认最简单的合法实现仍需解决目标业务中的实质耦合。不能事后禁止重建缓存、压低 3 秒门槛、隐藏复现或植入无关存储错误来推翻这次合法解法。当前官方任务级研究也显示 WAL/KV 类任务可被 Astra 稳定完成；参见 [当前失败证据补充](research/current-failure-evidence-2026-09-27.md)。
