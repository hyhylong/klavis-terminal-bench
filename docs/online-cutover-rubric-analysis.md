# 在线订单迁移：第一份冻结包的实施审查

2026-09-27。35 项审查结果为 **25 pass、9 fail、1 not_applicable**，未通过。
审查任务的 reward 1 只表示交付了 verdict 文件。实际审查器为 Codex /
GPT-6 Astra / xhigh，与上游默认 Claude Sonnet 5 的差异已记录。

被审查候选的 Harbor checksum 为
`96461fe05ddf2c6b2aac03e9cbcf440aa94a61e08d90900590b857dc92c5ce3a`；
外层 review task 为
`4971971077042feef9471533aef9b6cd8f9af5660836fdd16c7dc75e97137e62`。
两者不可混用。导出时重新核对了冻结包 35 个文件的哈希、固定 rubric 的
35 个名称、JSON 重复键及 outcome。原始 verdict 保留，没有改写为通过。

证据：[原始判定](../artifacts/validation/cutover-rubric-v1/verdicts.json)、
[结果摘要](../artifacts/validation/cutover-rubric-v1/summary.json)、
[准备记录](../artifacts/validation/cutover-rubric-v1/manifest.json)、
[选取的实际工具输出](../artifacts/validation/cutover-rubric-v1/trajectory-evidence.json)。

## 已确认的三个技术问题

1. **错误响应被误报为环境故障。** `verifiable` 判为 fail。审查者只在临时
   副本令指定请求返回 JSON 数组；并发测试随后对数组调用 `.get()`，抛出
   `AttributeError`。两项测试失败，`test.sh` 退出 70 且没有 reward。
   非法答案应被明确判为语义错误，不能与可信环境缺失混为一谈；也不能
   为了得到零分，把所有未知异常直接吞掉。
2. **固定观察窗口可绕过在线进展检查。** `anti_cheat_robustness` 判为 fail。
   审查者在临时参考解中加入 4 秒启动延迟，并在整个快照复制期间持有
   源库独占栅栏。该错误方案获得 **23/23、reward 1，188.09 秒**。测试只
   观察 2 秒就释放目标锁，日志明确记录 `observation_expired`、未观测到
   阻塞回填和在线源库修改。该代码在实际阻塞回填时不能维持服务，短暂
   等待却避开了相关故障。它没有伪造奖励或突破容器隔离；这是验收覆盖
   缺口。不能简单禁止延迟启动，或把所有未观察到私有阶段的合法方案判错。
3. **并发终止的场景未真正重叠。** `test_instruction_alignment` 判为 fail。
   合同写明在并发迁移中终止一个并由另一个继续，但当前测试先终止第一
   个，再启动第二、第三个。已有重启检查不能代替这个明确的并发场景。

以上两个运行反例发生在 review 容器的临时副本；并非独立的正式模型
cheat job。审查轨迹中的原任务哈希检查确认 35 个文件未改。参考解在
同一审查环境通过 23 项测试，也不抵消这些误接收或误分类问题。

## 其余六项 fail

| 分类 | 项目 | 处理 |
| --- | --- | --- |
| 人工 README 未完成 | `reviewable`、`difficulty_explanation_quality`、`solution_explanation_quality`、`verification_explanation_quality`、`task_readme` | 四个人工章节均为明确占位，不能声称达标，也不冒写作者经历或人工创作。 |
| 上游 schema 版本冲突 | `task_toml_schema` | rubric 的旧字段列表遗漏 `network_mode`。固定 Harbor runtime 和同一上游模板支持 `network_mode = "public"`；静态检查分别拒绝 `allow_internet=true` 和 `false`，因此保留当前有效配置并记录分歧。 |

schema 证据已见[上游合同审计](upstream-contract.md)和[第二版的同一问题
复核](durable-rubric-analysis.md)。这只是对冲突的说明，不是把原始 9 项
fail 擅自减为 8 项。

## 后续处理

保留第一份冻结包和正在运行的普通模型试验。修复只能进入新的工作版本，
重新执行正确参考解、合法替代方案、已知错误解和环境故障控制，再冻结。
独立的[观察窗口分析](cutover-phase-observation-review.md)说明了持续业务
请求、公开状态释放屏障以及故障暂停预算的设计；它本身还不是修复通过
的证据。若普通模型成功，还要分析其实际解法，不能因测试存在漏洞就把
一个合法成功改称作弊，也不能继续声称该候选达到了难度门槛。
