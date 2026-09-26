# durable-ledger-repair：35 项本地实施评审分析

2026-09-27。实际评审已完成，结果是 **23 pass、11 fail、1 not_applicable**，不能报告 rubric 通过。评审 meta-task 的 reward=1 仅表示成功交付非空 verdict 文件。本文是对评审证据的人工式 AI 复核，不替代上游默认 Claude reviewer、维护者审批或正常/对抗试验。

## 证据范围

- 试验：`implementation-review-codex-20260926T200212311524Z/review-task__qQXgwB6`；实际 reviewer 为 `codex / openai/gpt-6-astra / xhigh`，CLI `0.157.1`，Harbor `0.23.1.dev202609170426`。2026-09-26 20:03:22 至 20:11:55 UTC 完成，Harbor 无 exception。
- 使用固定上游 commit `4def1f367467b34b18e0dbdc086400ba71c3e037` 的全部 35 条 rubric。逐项验证了名称集合、无重复 JSON key、合法 outcome 和非空 explanation；没有改写评审者 verdict。
- 被评审的是 frozen `durable-ledger-repair-20260926T200157076022Z`，其 39 个文件与 preparation manifest 及原生 Linux staging 均逐字节对应。被评审 task 的 Harbor checksum 为 `52200606da8644eb9d948784f20b1369bafcaea4702d0190f0e03f1a4708b957`；外层 review meta-task 为 `20eac021577a9de913478e60980751a88f728706351251133bbf514024d0b319`，不要混用。
- [精简结果](../artifacts/validation/durable-rubric-v3/summary.json)、[原样 verdicts](../artifacts/validation/durable-rubric-v3/verdicts.json)、[来源和文件 manifest](../artifacts/validation/durable-rubric-v3/manifest.json)、[选取的工具实证](../artifacts/validation/durable-rubric-v3/trajectory-evidence.json)、[导出文件校验值](../artifacts/validation/durable-rubric-v3/sha256s.json)。导出没有复制配置、环境变量、凭据、完整轨迹或原始 agent 文本。

## 哪些问题已被证明

**实际的格式兼容性漏验，对应 `verifiable` 和 `test_instruction_alignment` 两项 fail。** 轨迹第 18 步在临时副本修改 oracle：每个新 WAL 帧前添加 `PRIV`，同时让自己的读取器接受该前缀并保留旧格式读取能力。第 19 步对应工具输出确为退出码 0、`26 passed in 25.02s`。本次复核也确认两处替换在 frozen 源码各匹配一次。独立检查旧格式能否读取、检查压缩后 WAL 是否为空，不能证明实现产生的非空 WAL 仍遵守公开格式；用提交者自己的 reader 读自己的 writer，会遗漏这种互相配合的偏差。

这是违反公开存储 ABI 的实际误接收，**不是已证明的隔离逃逸、答案泄漏或 reward 文件伪造**。评审者在 review 容器中安装固定版本 pytest 后运行临时复制的测试，并未另起一轮完整 Harbor benchmark trial；临时 mutant 和其 CTRF 未作为独立文件收集。本次导出保存了精确替换及对应输出，但没有重新运行该 mutant，不能将其描述为新增的正式对抗试验。

**难度问题，对应 `difficult` fail。** 轨迹直接比较发现 starter 的 `domain.py` 与 oracle 相同，持久化实现只差 docstring，修复集中在保留 amendment 候选和使原实体缓存失效。评审者据此给出“经验要求不足”的判断；这是结构证据加专家判断，不是可机械证明的人类耗时结论。随后[正常 Codex pilot](../artifacts/validation/durable-codex-pilot.json) 的 26/26、reward=1 为本地难度假设提供了独立反证；该提交的 `storage.py` 和 `domain.py` 与 frozen starter 字节相同，成功没有依赖上述 WAL 漏验。它不属于本次 rubric 运行，也不能把未运行的其余试验算成成功或失败；详见[独立 pilot 分析](durable-pilot-analysis.md)。

评审也实际执行了已给参考解：第 16 步为 `26 passed in 24.45s`，公开 smoke 全部通过，流式 workload 中位数约 0.364 秒。它证明该临时复现环境下参考解可解，并未证明长期无随机失败、所有正确实现均有充足余量或所有未测行为都正确。

## 其余 fail 应怎样解释

| 类别 | 原始 fail 项 | 核实与边界 |
| --- | --- | --- |
| 缺少明确的防护层 | `verifier_execution_isolation` | frozen `tests/test.sh:4` 只创建日志目录，没有在任何提交代码执行前 `chmod 700 /logs/verifier`，违反 rubric 的明确要求。评审容器中的同名目录确为 0777，但这不是对实际 benchmark verifier 目录权限的独立测量。Landlock、降权及阻止写入的 hostile fixture 已执行通过；没有展示可利用的 reward 写入路径。仍应在未来 verifier 加上 root-only 日志权限，不能把其他隔离层当作省略理由。 |
| 共享代码与文字合同 | `separate_verifier_configured`、`instruction_concision` | 两份 controller 的差异仅为公开副本多一行 `import unittest`，没有行为差异实证，但违反未说明差异须字节一致的要求。instruction 最后一段的 `Read SPEC.md` 也确为相对、未加反引号的路径；其余“可更简洁”属于评审判断。这两项不能称为已发现的运行时漏洞。 |
| 已知、待本人完成的作者部分 | `difficulty_explanation_quality`、`solution_explanation_quality`、`verification_explanation_quality`、`task_readme` | 四个人工 README 节均刻意保留 pending，占位不满足提交要求，评审判 fail 合理。这不是新发现的程序错误；不能由 AI 冒写个人经历或把 AI 草稿称为人工创作。 |
| 上游合同版本不一致 | `task_toml_schema` | rubric 的旧字段列表遗漏 `network_mode`，因此 reviewer 按字面判 fail。但实际固定 Harbor 的 `EnvironmentConfig` 明确有 `network_mode: NetworkMode`，该 frozen task 完整 schema 验证得到 `NetworkMode.PUBLIC`；同一上游 commit 的模板也使用 `network_mode = "public"`。两份独立静态检查分别拒绝显式 `allow_internet=true` 和 `false`。应记录这个版本冲突，不能为追求该单项 pass 加入静态检查禁用的字段。 |

11 项原始 fail 保持原样；上述分类不是重新给 rubric 加分。上游字段冲突的源码 hash、运行时核验和模板行号已进入精简工具证据，也与[上游合同审计](upstream-contract.md)一致。

## 供下一版沿用的经验

1. **兼容性要双向独立检查。** 除了让提交实现读取可信旧数据，还应由可信解析器读取它新产生的持久状态，覆盖非空增量、删除和切换后状态。数据库迁移中同理：直接查询目标关系和独立业务不变量，不能只相信提交服务自己的 read API。
2. **隔离各层都落实。** 日志和期望数据先设置 root-only；可信父进程决定 reward；提交代码使用独立低权限身份；输出写临时文件并清理进程组。PostgreSQL 服务和提交进程不能共享能读服务器文件的身份，SQL 角色不能获得服务器文件/程序执行权限。前述方案仍需实测，不能仅凭本次 sandbox 项 pass 宣称安全。
3. **字节一致与版本来源可机械核对。** 公共和 verifier 共用组件保持一致或明确记录有意差异；对 rubric 与实际 runtime 的分歧保留证据，不盲目迁就旧示例。
4. **通过 control 不等于足够难。** 正确 oracle 与 starter 的区分、crash suite 和复杂说明都不能替代正常模型试跑。当前 v2 已被合法解决，不继续修补它来伪造既有试验的含义，也不因发现漏验而把合法成功改判作弊。

当前任务与 frozen 文件均未由本次导出修改。此报告保留未通过及已知边界，不主张最终任务、正式对抗试验或 35 项验收已经完成。
