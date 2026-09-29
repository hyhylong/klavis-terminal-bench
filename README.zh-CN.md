# Klavis Terminal-Bench 任务

[English](README.md) | [简体中文](README.zh-CN.md)

这是 Klavis AI coding assignment 的本地提交仓库。最终提交的任务是 `tasks/recoverable-event-bridge`：一个在迁移过程中处理分段二进制事件流的可恢复事件桥接器任务。

任务要求 agent 同时满足以下约束：

- 增量扫描、坏帧恢复，以及跨 segment 的绝对偏移
- 事务提交、重复投递、abort、cutover 记录和序列前沿校验
- 私有 durable journal、checkpoint，以及停止或 failpoint 中断后的恢复
- 精确的 NDJSON、摘要、计数和进度输出
- 在独立、非特权 verifier 和 160 MiB 地址空间限制下执行

## 最终状态

最终冻结 Harbor task checksum：

`510db0ac8c1a0b656b88a578143684c2045ebf295a470613d2eeb6910eb4c92f`

与该 checksum 对应的任务树已推送到 GitHub 的 `main` 分支。它通过了 25/25 项固定静态检查，oracle reward 为 `1.0`（17/17 个 verifier 测试通过），nop reward 为 `0.0`。

Implementation rubric 使用本地 Codex `gpt-6-sol/xhigh` 作为明确标注的 reviewer 替代配置：34 项通过、1 项 `not_applicable`（`artifact_efficiency`）、0 项失败。该结果是本地替代评审，不冒充上游 hosted review。

## 模型试验

本提交采用允许的 Codex + DeepSeek 替代组合。下面的所有结果都绑定到同一个 checksum；基础设施异常不计为模型失败。

| 配置 | 标准 `/run` | 对抗 `/cheat` |
| --- | --- | --- |
| Codex `openai/gpt-6-sol`，`xhigh` | 3/3，reward `0.0`，无异常 | 1/1，reward `0.0`，无异常 |
| DeepSeek `deepseek/deepseek-flash`，`max` | 3/3，reward `0.0`，无异常 | 1/1，reward `0.0`，无异常 |

DeepSeek 是允许的 Claude slot 替代，不能解释为与上游 Claude 配置完全相同。完整 job 名称、checksum 和失败分析见 `docs/research/recoverable-event-bridge-rubric-review-2026-09-29.md`。

## 仓库结构

- `tasks/recoverable-event-bridge/README.md`：任务背景、难点、参考解和 verifier 设计。
- `tasks/recoverable-event-bridge/instruction.md`：agent 看到的任务说明。
- `tasks/recoverable-event-bridge/environment/CONTRACT.md`：协议、输出格式和恢复语义。
- `tasks/recoverable-event-bridge/solution/`：用于 oracle 验证的参考实现。
- `tasks/recoverable-event-bridge/tests/`：独立 verifier、fixture 和 replay model。
- `docs/evaluation.md`：固定 Harbor 版本、配置、运行命令和凭据边界。
- `docs/research/recoverable-event-bridge-rubric-review-2026-09-29.md`：最终 checksum 的静态、rubric、standard 和 cheat 证据摘要。

## 本地验证

以下命令只运行本地静态检查，不调用模型：

```bash
cd /mnt/e/JOB/klavis-terminal-bench
source artifacts/environment/runtime-env.sh
python scripts/check_static.py --task tasks/recoverable-event-bridge
```

要运行 Harbor 模型试验，请先按 `docs/evaluation.md` 配置本地 Codex 或 DeepSeek 凭据，再使用 `evaluation/run.sh`。凭据只保存在被 Git 忽略的本地配置中，不应写入提交或日志。

## 设计说明

1. 输出指标恢复正常不足以证明数据恢复正确；verifier 还会独立重放并比较字节、摘要和进度。
2. 不强制私有 journal 的具体格式，只强制可验证的恢复行为和完整输出契约。
3. 标准试验与对抗试验必须在同一个冻结 checksum 上解释，不能混用不同候选的历史结果。

本仓库不需要向 Terminal-Bench 创建 PR；GitHub 仓库本身就是作业交付物。
