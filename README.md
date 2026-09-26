# Klavis Terminal-Bench local workspace

原创任务实现工作区。题目从乱序 CDC 事件恢复双时间账本，处理原子事务、重复冲突、schema 延迟、历史修正、半开区间、删除和字段来源。输入为合成数据：1,010 条事件、21 个交付检查点。

**第一版被 Codex 和 DeepSeek 各成功解出；第二版也已被 Codex 正常试做成功解出。两版均不满足所需难度，保留全部真实结果作为反证，当前任务尚未完成。**

第三版在线订单服务迁移已冻结：真实 PostgreSQL 原型 68 项检查通过；正式 Harbor 参考解 23/23、初始代码 9/23，两次均无执行异常。更简单的合法双次复制方案也通过了完整的 23 项验收。35 项 rubric 为 25 pass、9 fail、1 N/A，发现非法响应误分类和并发故障覆盖缺口，尚未通过；Codex 普通试做仍在运行，详见[当前进度](docs/online-cutover-progress.md)。

第二版 `tasks/durable-ledger-repair` 修复持久化账本的修订依赖和缓存恢复。冻结版本的参考解 26/26 通过，初始代码有 6 项语义错误，控制试验均无执行异常。随后 Codex / GPT-6 Astra / xhigh 获得真实 reward 1，26/26 通过，无异常；整个 job 约 8 分 3 秒，stream 中位数 0.365 秒，低于公开的 3 秒上限。它保留正确的源存储层，修复两处索引错误，并合法丢弃可选缓存。该候选的难度假设已被否证，不再为它继续六次失败和两次对抗的完整评测。首次安装网络错误仍保留为基础设施失败。见 [试做分析](docs/durable-pilot-analysis.md)、[过滤后的证据](artifacts/validation/durable-codex-pilot.json)和[第二版记录](docs/durable-progress.md)。

## 已验证与待完成

| 验收项 | 当前证据 |
| --- | --- |
| 第一版本地环境 | 已使用 WSL2、Docker、Python 3.12.12、Harbor 0.23.1.dev202609170426 完成下列实测；当前状态另见第二版记录 |
| 第一版开发测试 | 47 项通过；含 8 个种子的独立算法交叉验证、错误产物拒绝和证据分类测试 |
| Docker 构建 | agent 与独立 verifier 镜像均构建成功 |
| Harbor oracle | oracle-v2-lf：reward 1，22 项容器验证通过，无执行异常 |
| Harbor nop | nop-v3-lf：reward 0，无执行异常，验证器独立运行 |
| 上游静态检查 | 24/25 通过；作者 GitHub 用户名尚未提供 |
| 作者信息与人工说明 | 待作者补充，详见 [中文作者指南](docs/author-guide.zh-CN.md) |
| Implementation rubric | 第二版 Codex 本地审查已完成：23 pass、11 fail、1 N/A；未通过。存在已证明的 WAL 写入格式漏验，另有作者占位及上游 schema 版本冲突，见[逐项分析](docs/durable-rubric-analysis.md)。审查 reward 1 仅表示产出 verdict 文件 |
| Codex + DeepSeek 正常试验 | 两个模型均有真实 reward 1；第一版不满足难度要求 |
| 对抗试验与轨迹分析 | 第二版成功轨迹已分析；正式对抗尚未运行，当前候选停止完整评测 |
| GitHub 交付 | 当前为本地 Git 仓库，尚未发布 |

最新 oracle 与有效 nop 使用同一 Harbor task checksum：`44dd9c660becb8d373dd1bfbaa5bf42573dd938c31cb02e1411266ba481a2d51`。跨平台生成器现统一写入 LF，之后已重跑两项控制验证。首次 nop-v1 因 Harbor 相对路径处理报 FileNotFoundError，已保留为基础设施失败；这次失败不计作题目难度证据。后续运行使用绝对任务路径和 jobs 路径，并在每次调用前重新进入项目目录。

## 本地运行

在 Windows PowerShell 安装或复核独立运行环境：

```powershell
wsl -d Ubuntu-22.04 -- bash /mnt/e/JOB/klavis-terminal-bench/scripts/setup-local.sh
```

在 WSL shell 中：

```bash
cd /mnt/e/JOB/klavis-terminal-bench
source artifacts/environment/runtime-env.sh
python -m unittest discover -s dev_tests -v
python tools/generate_corpus.py
bash scripts/fetch-upstream.sh
python scripts/check_static.py
```

静态检查目前会因真实作者信息缺失而返回失败；请补全 task.toml 中的三个作者字段，不要填虚构身份来绕过。

用新的 job-name 重跑容器验证，始终使用绝对路径（这些命令不调用模型）：

```bash
root=$(pwd)
cd "$root"
harbor run --path "$root/tasks/temporal-ledger-repair" --agent oracle --env docker --jobs-dir "$root/artifacts/jobs" --job-name oracle-recheck --n-concurrent 1 --yes
cd "$root"
harbor run --path "$root/tasks/temporal-ledger-repair" --agent nop --env docker --jobs-dir "$root/artifacts/jobs" --job-name nop-recheck --n-concurrent 1 --yes
```

不要仅凭 Harbor 进程退出码判断通过；检查每个 trial 的 `exception_info`、`verifier_result`、CTRF 和轨迹。

## 仓库结构

- `tasks/temporal-ledger-repair/environment/`：agent 可见的协议和数据。
- `tasks/temporal-ledger-repair/solution/`：使用区间拆分的参考解法。
- `tasks/temporal-ledger-repair/tests/`：独立镜像；按全部端点划分后逐点重放的验证器，严格解析 JSON。
- `dev_tests/`：手工核算、差分、变形和错误输出测试。
- `tools/generate_corpus.py`：可复现数据生成器，同时更新公开数据和验证器内的可信副本；不生成答案。
- `scripts/`：环境、静态检查和证据工具。
- `docs/upstream-contract.md`：固定版本的 25 项静态检查、35 项 rubric 和评测约定。
- `docs/runtime.md`：实际运行环境和安装证据。
- `docs/local-review.md`：使用 Codex 进行本地 implementation rubric 审查的方式与差异。
- `artifacts/static/`：静态检查日志；完整运行轨迹在被 Git 忽略的 `artifacts/jobs/`。

第一版验证器只解析声明的 JSON 文件。第二版会执行提交的 Python 库，由隔离子进程调用公开 API；可信父进程保管预期答案、模拟磁盘和奖励。

## 评测口径

固定上游：`harbor-framework/terminal-bench` 提交 `4def1f367467b34b18e0dbdc086400ba71c3e037`。附件的旧仓库链接重定向到该项目；当前默认 Codex 模型已是 GPT-6 Astra，与附件示例 GPT-6 Sol 不同。用户已选择 Codex 加附件允许的 DeepSeek V4.1 Flash 替代组合；配置、启动命令与已核对的请求参数见 [评测说明](docs/evaluation.md)。离线凭据存在检查不代表服务端认证或额度验证。

正常试验需要每个模型 3 次真正未通过验证器，对抗试验每个模型 1 次零奖励。超时、鉴权、限流、容器或接口错误都不能当成模型失败。即使 reward 为 0，也要检查轨迹和验证器证据后才能归类。

作者身份、人工说明、全部 rubric/轨迹审查和真实试验结果都属于剩余门槛。Codex 本地审查可按相同标准生成证据，但应明确它与未修改的上游 hosted review 使用了不同模型；附件没有单独指定审查模型。凭据仅存于本地忽略配置，没有把未运行的检查标为通过。

第一版成功解题记录：DeepSeek `temporal-ledger-repair__SAk7yaT`、Codex `temporal-ledger-repair__eJReGSd`。前者的 22 项验证全部通过。安装超时、DNS 错误以及主动取消的后续试验分别保留，均不计作模型失败。后续方向和资料依据见 [难度研究](docs/research/task-difficulty-2026-09-27.md)。
