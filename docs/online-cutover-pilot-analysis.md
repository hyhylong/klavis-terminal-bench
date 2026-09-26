# Online cutover：首个 Codex pilot 的独立分析

本次是正常实现取得的成功，不能归类为靠延迟规避故障、SQL 影子函数、读取私有答案或伪造奖励的成功。独立静态审阅未发现这份提交中具体、已证实的合同违例。它采用合同允许的两次全量复制和持久化切换围栏，真实通过了本次安排的故障。第三版候选因此已经不满足预定的“三次正常失败”筛选目标，应停止完整失败/cheat 矩阵，保留这次成功作为难度反证。一次成功不估计一般通过率，也不证明所有可能执行序列都正确。

本分析只读取既有产物与冻结合同，未重跑模型、修改任务或追加评测。任务冻结目录为 `artifacts/local/frozen/online-order-cutover-20260926T212539311430Z/online-order-cutover`。唯一分析对象是以下已完成 trial；其他代理正在分析的 rubric 反例不作为本次提交行为的证据。

| 已验证字段 | 结果 |
| --- | --- |
| Job / trial | `standard-codex-20260926T213203660705Z` / `online-order-cutover__DDiSCkf` |
| Agent | Codex `0.157.1`，`gpt-6-astra` |
| 奖励、异常 | `reward=1.0`，`exception_info=null` |
| CTRF | 23 passed，0 failed，0 skipped |
| 私有测试 stdout | `23 passed in 61.03s`，preflight passed |
| CTRF 时间戳跨度 | 57.445 秒；与 pytest stdout 的 61.03 秒采用不同计时口径，分别保留 |
| Agent 执行 | UTC 2026-09-26 21:32:09.935696 至 21:49:04.143839，1014.208 秒；公开预算 7200 秒 |
| 整个 trial | UTC 21:32:05.419072 至 21:50:45.110602，1119.692 秒 |
| ATIF 轨迹 | 24 条 step，含 5 条初始上下文，19 条 agent step；不是 24 次独立模型试验 |

对应原始证据：[result.json](E:/JOB/klavis-terminal-bench/artifacts/jobs/standard-codex-20260926T213203660705Z/online-order-cutover__DDiSCkf/result.json)、[CTRF](E:/JOB/klavis-terminal-bench/artifacts/jobs/standard-codex-20260926T213203660705Z/online-order-cutover__DDiSCkf/verifier/ctrf.json)、[测试输出](E:/JOB/klavis-terminal-bench/artifacts/jobs/standard-codex-20260926T213203660705Z/online-order-cutover__DDiSCkf/verifier/test-stdout.txt)、[trajectory](E:/JOB/klavis-terminal-bench/artifacts/jobs/standard-codex-20260926T213203660705Z/online-order-cutover__DDiSCkf/agent/trajectory.json)。未复制 raw config 或认证信息。

实现的关键简化是完全不维护增量日志。迁移先在目标库取得 session advisory lock，重复检查目标是否已经激活；已激活则在任何源库访问前返回。随后在一个目标事务内复制源库 REPEATABLE READ 快照，此时源库仍可读写，目标 `order_lines` 的写锁等待也发生在围栏之前。完成初次复制后，迁移取得源库排他 advisory lock，排空持有共享锁的源请求，提交单调的 `fenced=true` 标记。然后重新读取完整源快照，覆盖仍未发布的目标数据，并与 `active=true` 一起提交。代码位置：[migrate.py:20](E:/JOB/klavis-terminal-bench/artifacts/jobs/standard-codex-20260926T213203660705Z/online-order-cutover__DDiSCkf/artifacts/app/orderbridge/migrate.py:20)、[migrate.py:49](E:/JOB/klavis-terminal-bench/artifacts/jobs/standard-codex-20260926T213203660705Z/online-order-cutover__DDiSCkf/artifacts/app/orderbridge/migrate.py:49)、[coordination.py:43](E:/JOB/klavis-terminal-bench/artifacts/jobs/standard-codex-20260926T213203660705Z/online-order-cutover__DDiSCkf/artifacts/app/orderbridge/coordination.py:43)。

这个状态机允许“源已围栏、目标未激活”的恢复状态：服务返回无新副作用的 retry，重启迁移重新复制即可；它不重新开放源库。目标激活 COMMIT 的确认丢失后，下一次迁移先读取已提交的 active 标记，所以不会用旧源快照覆盖切换后的目标写入。源数据库退役后，这个同样的入口次序使迁移和服务继续工作。既有服务的每次请求先探测目标，选择源库后再取得共享锁并读取持久化 fence；延迟建立的源连接不能跳过这次检查。[backend.py:145](E:/JOB/klavis-terminal-bench/artifacts/jobs/standard-codex-20260926T213203660705Z/online-order-cutover__DDiSCkf/artifacts/app/orderbridge/backend.py:145)

公开接口没有被缩减为仅处理演示数据。`api.py` 和 `__main__.py` 与冻结 starter 字节一致，保留精确类型、字段、Unicode、整数边界及 CLI。目标读操作以单条 SQL 读取 header 和按 position 排序的 lines；目标写入实际维护规范化公共表。mutation 先竞争完整 request ID 的 receipt，再锁订单和按稳定顺序锁库存，将业务结果和最终 receipt 原子提交；历史结果直接重放，冲突请求不改历史。按订单 ID 的 32-bit 哈希仅用于增加串行化，真实身份仍由完整 key 决定。HTTP 层增加 12-worker 上限、线程栈限制和过长 Content-Length 防护，是对公开进程限制的正常适配。[backend.py:31](E:/JOB/klavis-terminal-bench/artifacts/jobs/standard-codex-20260926T213203660705Z/online-order-cutover__DDiSCkf/artifacts/app/orderbridge/backend.py:31)、[backend.py:111](E:/JOB/klavis-terminal-bench/artifacts/jobs/standard-codex-20260926T213203660705Z/online-order-cutover__DDiSCkf/artifacts/app/orderbridge/backend.py:111)、[service.py:60](E:/JOB/klavis-terminal-bench/artifacts/jobs/standard-codex-20260926T213203660705Z/online-order-cutover__DDiSCkf/artifacts/app/orderbridge/service.py:60)

[coverage.jsonl](E:/JOB/klavis-terminal-bench/artifacts/jobs/standard-codex-20260926T213203660705Z/online-order-cutover__DDiSCkf/verifier/coverage.jsonl) 的实际记录如下；这些是观察到的故障，不能降格成“测试名称包含此场景”。

| 场景 | 本次实际覆盖 |
| --- | --- |
| HTTP 响应未知，source / target | 两端都完整发送请求且不读响应；杀服务前公共 receipt 已观察到提交，随后重启并核对重试 |
| Backfill | `phase=blocked`，`backend_at_barrier=source`，`fault_observed=true` |
| Restart | `phase=blocked`，`crash_observed=true` |
| Delayed commit | 初始 `blocked`、backend source；收据屏障因 `migration_waits_on_writer` 释放 |
| COMMIT baseline | 实际观察到 2 个目标 COMMIT，返回 0；初始 blocked，锁内确有 live source changes |
| 丢弃 COMMIT 1 ACK | 实际丢弃，初次退出 1；`selected_ack_lost`，发生在 live-source barrier 前，因此该轮 `live_source_changes=false` |
| 丢弃 COMMIT 2 ACK | 实际丢弃，初次退出 1；初始 blocked，`live_source_changes=true` |
| 延迟源连接 | `coverage=held_across_activation` |

没有把两次失 ACK 虚报为参考解的四次：这份实现只有两个被观察到的目标 COMMIT，本次全部覆盖。第一个是初始化目标标记；第二个发布数据与激活。源库 fence 的 COMMIT 不经过这条目标连接代理，本次记录没有声称覆盖它的确认丢失。

轨迹显示代理先读公开 CONTRACT、starter、schema、smoke、dev_runtime，然后自行实现和测试。step 8 已选定 durable fence + final refresh；step 10 的 patch 格式失败后正常重试。step 13 开始运行自写集成测试，其中延迟连接测试最初因健康检查超时失败，step 18 调整自写代理的 TCP_NODELAY 和健康探测等待，step 19 通过。step 20 还将 SKU 校验移到目标初次探测中，使围栏窗口里的无效请求仍得到 invalid_request。最终 step 22 记录自写 9 个测试全部通过（33.989 秒），step 23 记录公开 smoke 的 86 checks 通过（13.706 秒）。自写测试包含 64 个 seeded orders、128 个 receipts 和切换时两服务并发请求；它们支持“做了正常工程验证”的判断，但不能替代独立私有测试。

私有 verifier 测试未提供给此次 agent。冻结 agent Dockerfile 的第 43–44 行只复制公开 runtime/schema/smoke/CONTRACT 和 starter package；轨迹工具参数没有访问 `/tests`、`test_outputs` 或奖励路径。代理自行编写的 `test_integration.py` 使用公开开发 helper，并未由运行时 CLI 导入。这里的结论是当前镜像与记录所支持的“未见私有测试访问”，不声称能证明记录以外的事件。

已知的覆盖边界仍需保留：冻结测试的短阶段观察窗口对另一些实现可能过早释放 fixture；公共 SQL 检查中的函数解析也存在单独审查的攻击面。这些不是本次成功的原因。本次实际命中了 blocked / delayed / activation schedules；运行时 `backend.py`、`migrate.py`、`coordination.py`、`service.py` 没有 sleep、search_path 修改、row_to_json 替身、CREATE FUNCTION/VIEW、私有路径访问或按 verifier 识别切换行为。包中只有自写测试含 0.02 / 0.15 / 0.03 秒短等待。公共关系由正常 SQL 实际维护，未找到 SQL shadow 伪造结果的代码。不能因为另一个反例能利用测试缺口，就推翻这个实现的合法通过。

难度不足的解释具有具体来源：公开 contract 只要求小规模 fixture、允许最终短暂 retry、未规定 CDC 或固定内部阶段；因此第二次一致快照可以合法替代 commit-order 日志捕获、删除重放和增量追赶。starter 又已提供业务校验、源端事务和 HTTP/CLI，大部分新增工作集中在两数据库的单调状态机与规范化后端。代理约 17 分钟即实现并自行验证这条较短路径。此结果支持淘汰本候选，而不支持事后禁止 full-copy、缩短 deadline 或堆加恢复规则以挽救“难题”标签。静态审阅尚不能证明所有未执行并发历史；截至本分析，没有可指出的真实未覆盖合同违例，足以否认这次正常成功。

复核指纹（SHA-256）：`result.json` = `9e68f055452d32586162ccbc343f62644e238da3751483b7fd6a4a20ab729f03`；`coverage.jsonl` = `84423cd47fd0d0f74b6e3b433e56a317a731d3b1c67cd0a8e0312ca4b6c7ecb5`；`ctrf.json` = `35dbfb060c39d5004bc998817194ff0c7358344e75a17c61b9afcc568ccb16d3`；`trajectory.json` = `18ed8f9eed76d1c9129b367718266b51d91e7fdf48bf6aa71d73e8dd4c2aec7b`。提取方法为 Python 标准库 JSON 读取结果白名单字段、逐行读取 coverage、枚举 trajectory 的 tool_calls，并将导出模块与冻结 starter 做字节比较；未执行提交代码。
