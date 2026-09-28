# Klavis Terminal-Bench local workspace

原创 Terminal-Bench 任务与本地评测工作区，包含账本恢复、持久化修复和在线订单迁移三个候选。WSL、Docker、Harbor 及模型试做均已实际运行；`recoverable-event-bridge` 的最终冻结快照已完成 Codex 与 DeepSeek 的同校验和标准矩阵及对抗试验。

**第一版被 Codex 和 DeepSeek 各成功解出；第二版、第三版也均被 Codex 正常解出。三版均不满足所需难度，保留全部真实成功结果，当前作业尚未完成。**

当前继续校准的候选是 `tasks/recoverable-event-bridge`。它已加入公开可读的迁移 cutover 控制记录：cutover 会验证摘要并推进租户/流的序列前沿，和普通事务按提交号排序，隐藏用例覆盖重复、冲突、混合事务、断点恢复及坏摘要。最终冻结快照 `83b25d3b...` 上，Codex `gpt-6-sol/xhigh` 和允许的 DeepSeek 替代均完成 3/3 有效 `reward=0`，每次都有 verifier 结果且无 exception；两个标准矩阵可以作为同校验和双模型门槛证据。详细记录见[候选试做报告](docs/research/recoverable-event-bridge-pilot-2026-09-27.md)。

为修复上述环境错误，当前候选的 Dockerfile 已在镜像构建阶段预装 Debian `tmux` 和 `asciinema`，避免 Terminus-2 在每个 trial 中联网安装并回退到超时的源码编译。修复验证快照 checksum 为 `b2dc1d34aea3d0c8a47240f210cb5232f3c7d7228b35dd9c02bea6f95679ac64`；DeepSeek 单次验证为 CTRF 9/10，随后两次矩阵试验各为 5/10，三次均 `reward=0`、`exception_info=null`，汇总在 `artifacts/validation/recoverable-event-bridge-repaired-matrix.json`。最终含 `longhangyu` 元数据的提交快照为 `artifacts/local/frozen/recoverable-event-bridge-20260928T073442757886Z/recoverable-event-bridge`，Harbor checksum 为 `83b25d3bc0a07cb5088410aff5f1a402986bfd936004e68cd809325853f3dc94`。两个 checksum 分开统计。

最终元数据快照上的 Codex / GPT-6 Sol / xhigh 标准矩阵为 3/3 有效 `reward=0`、无异常（CTRF 7/3、7/3、8/2），记录在 `artifacts/jobs/standard-codex-20260928T074308072872Z`；同一快照上的 DeepSeek 标准矩阵也是 3/3 有效 `reward=0`、无异常（运行约 2 小时 40 分钟），记录在 `artifacts/jobs/standard-deepseek-20260928T082943222878Z`，机器报告为 `artifacts/validation/recoverable-event-bridge-final-deepseek-standard.json`。Codex `/cheat` 和 DeepSeek `/cheat` 均为 1/1、无异常、`reward=0`，记录在 `artifacts/jobs/cheat-codex-20260928T080703548218Z` 与 `artifacts/jobs/cheat-deepseek-20260928T081223953392Z`。早期 `b2dc...` 快照的 DeepSeek 结果仍单独保留，未与最终快照混算。

第三版在线订单服务迁移的 Codex / GPT-6 Astra / xhigh 普通试做 **23/23、reward 1、无异常**，整个 trial 18 分 40 秒。真实经历了阻塞回填、晚提交、两个 COMMIT 回执丢失及跨切换旧连接，未依赖已知观察窗口漏洞。35 项 rubric 为 25 pass、9 fail、1 N/A；另有需要修复的验收器问题。已停止该候选的完整失败矩阵，详见[试做分析](docs/online-cutover-pilot-analysis.md)、[过滤后的实测证据](artifacts/validation/cutover-codex-pilot.json)和[进度与限制](docs/online-cutover-progress.md)。

最新选题研究已核对官方 Astra / xhigh 的六道题、共三十次公开结果。已区分缺交付、语义不一致、目标不足及最终答案准确性；不把 0/5 当作新题必败的证明。[Operations 逐次分析](docs/research/operations-failure-mechanisms.md)、[Software 逐次分析](docs/research/software-failure-mechanisms.md)、[Science 证据边界](docs/research/science-failure-mechanisms.md)。研究没有搬用现成 benchmark 的实现、输入或答案。

第二版 `tasks/durable-ledger-repair` 修复持久化账本的修订依赖和缓存恢复。冻结版本的参考解 26/26 通过，初始代码有 6 项语义错误，控制试验均无执行异常。随后 Codex / GPT-6 Astra / xhigh 获得真实 reward 1，26/26 通过，无异常；整个 job 约 8 分 3 秒，stream 中位数 0.365 秒，低于公开的 3 秒上限。它保留正确的源存储层，修复两处索引错误，并合法丢弃可选缓存。该候选的难度假设已被否证，不再为它继续六次失败和两次对抗的完整评测。首次安装网络错误仍保留为基础设施失败。见 [试做分析](docs/durable-pilot-analysis.md)、[过滤后的证据](artifacts/validation/durable-codex-pilot.json)和[第二版记录](docs/durable-progress.md)。

## 已验证与待完成

| 验收项 | 当前证据 |
| --- | --- |
| 第一版本地环境 | 已使用 WSL2、Docker、Python 3.12.12、Harbor 0.23.1.dev202609170426 完成下列实测；当前状态另见第二版记录 |
| 第一版开发测试 | 47 项通过；含 8 个种子的独立算法交叉验证、错误产物拒绝和证据分类测试 |
| Docker 构建 | agent 与独立 verifier 镜像均构建成功 |
| Harbor oracle | oracle-v2-lf：reward 1，22 项容器验证通过，无执行异常 |
| Harbor nop | nop-v3-lf：reward 0，无执行异常，验证器独立运行 |
| 上游静态检查 | 25/25 通过；任务元数据中的 `author_github` 为 `longhangyu` |
| 作者信息与人工说明 | GitHub 用户名已补全；作者姓名和邮箱仍按提交要求另行填写 |
| Implementation rubric | 第二版 Codex 本地审查已完成：23 pass、11 fail、1 N/A；未通过。存在已证明的 WAL 写入格式漏验，另有作者占位及上游 schema 版本冲突，见[逐项分析](docs/durable-rubric-analysis.md)。审查 reward 1 仅表示产出 verdict 文件 |
| Codex + DeepSeek 正常试验 | 最终 checksum `83b25d3b...` 上两模型均为 3/3 有效 reward 0、无异常；Codex CTRF 为 7/3、8/2、7/3，DeepSeek 三次均有 verifier 结果 |
| 对抗试验与轨迹分析 | 最终 checksum 的 Codex 与 DeepSeek cheat 均为 reward 0；实现 rubric review 仍有 13 项 fail，需要修订或人工说明 |
| GitHub 交付 | 当前为本地 Git 仓库，尚未发布 |

上一版正式 DeepSeek 结果使用 Harbor task checksum `257be989e53b17c06dd1b13da45bb5bb6606ae35c37184edeb0ba3ea96084116`，与当前 Codex 快照不同，不能直接合并。当前 Codex 快照 checksum 为 `3c356502739a722070f771af8ba0ed7dc7be0b5442cf6db0b738814bd3a6070b`。跨平台生成器现统一写入 LF，之后已重跑控制验证。首次 nop-v1 因 Harbor 相对路径处理报 FileNotFoundError，已保留为基础设施失败；这次失败不计作题目难度证据。后续运行使用绝对任务路径和 jobs 路径，并在每次调用前重新进入项目目录。

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

静态检查当前已通过 25/25。`author_github` 使用用户提供的 `longhangyu`；本地静态 CI、Docker 构建和 Harbor 运行都不需要登录 GitHub。只有推送仓库、创建 PR 或上传到需要权限的远端时才需要相应的 GitHub 认证。

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

固定上游：`harbor-framework/terminal-bench` 提交 `4def1f367467b34b18e0dbdc086400ba71c3e037`。附件的旧仓库链接重定向到该项目；本次正式 Codex 试验固定使用 `openai/gpt-6-sol` 与 `xhigh`，不使用 Astra。用户已选择 Codex 加附件允许的 DeepSeek V4.1 Flash 替代组合；配置、启动命令与已核对的请求参数见 [评测说明](docs/evaluation.md)。离线凭据存在检查不代表服务端认证或额度验证。

正常试验需要每个模型 3 次真正未通过验证器，对抗试验每个模型 1 次零奖励。超时、鉴权、限流、容器或接口错误都不能当成模型失败。即使 reward 为 0，也要检查轨迹和验证器证据后才能归类。

作者身份、人工说明、全部 rubric/轨迹审查和真实试验结果都属于剩余门槛。Codex 本地审查可按相同标准生成证据，但应明确它与未修改的上游 hosted review 使用了不同模型；附件没有单独指定审查模型。凭据仅存于本地忽略配置，没有把未运行的检查标为通过。

最终快照的本地 Codex implementation-rubric review 已运行 35 项：21 pass、13 fail、1 N/A，结果保存在 `artifacts/jobs/implementation-review-codex-20260928T081435304511Z`。失败集中在 README 四个章节仍是作者占位、verifier 隔离/完整 checkpoint 断言、fixture builder 维护方式和多余的 `network_mode` 字段；该 review 的 reward 1 只表示 verdict 文件生成，不代表 35 项全部通过。

第一版成功解题记录：DeepSeek `temporal-ledger-repair__SAk7yaT`、Codex `temporal-ledger-repair__eJReGSd`。前者的 22 项验证全部通过。安装超时、DNS 错误以及主动取消的后续试验分别保留，均不计作模型失败。后续方向和资料依据见 [难度研究](docs/research/task-difficulty-2026-09-27.md)。
