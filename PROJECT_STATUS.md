# Patch Tournament 项目现状

> 更新时间：2026-08-31
> 证据来源：当前仓库、Git 历史、与本项目相关的 Codex 会话、本次 fresh test

## 一句话结论

Patch Tournament 已经从一个“多 Agent 竞赛选最小补丁”的实验，收缩成一个更可靠的默认产品：在任务开始时记录 Git 工作树，任务结束时只报告本次任务实际改了什么。

当前阶段是**已公开、可使用的 0.2 Alpha**。核心实现已经推送，Python 3.11、3.12、3.13 的持续集成已经通过；真实任务验证和正式 release 仍未形成闭环。

## 这个库在解决什么问题

它最初要解决的问题是 Codex 容易在一个本来很小的任务中增加不必要的抽象、文件、依赖或相邻重构。

早期方案是同时生成多个补丁，用独立测试淘汰错误方案，再从正确方案中选择改动较小者。真实 Harness 历史问题证明，这个方法有时确实能从多个正确候选中选出更小的实现，但它也带来更多 token、运行时间和评分系统复杂度。

后来发现，更危险的问题是让一个通用程序用固定文件数、行数、文件名分类和 profile 判断“是否过度设计”。这些硬编码会误伤合理修改，并可能驱使 Agent 为了通过指标而删除必要代码。J-Space 的历史进一步说明，模式、阈值、配置和例外表一旦增长快于真实执行与测试，系统会越来越难维护。

因此 0.2 的产品边界改成了下面这样：

```text
默认路径

任务开始快照 -> 一个主 Agent 实现 -> 项目测试 -> 本任务 Diff Facts

显式高级路径

用户主动批准 -> 多候选 Tournament -> 独立检查 -> 最小合格补丁报告
```

外部程序负责可证明的事实，Agent 和用户负责语义判断。

## 来龙去脉

| 阶段 | 发生了什么 | 得到的结论 |
|---|---|---|
| 全局规则实验 | 为 Codex 增加防过度设计的 `AGENTS.md` 规则，并做规划与真实代码 A/B | 规则能被加载，但没有稳定证明它能减少过度设计 |
| Harness 真实回放 | 用历史 Codex 解析故障运行多个隔离候选 | 外部测试能淘汰错误补丁；多个正确补丁之间确实存在明显大小差异 |
| Tournament 原型 | 三候选并行、干净 grader、隐藏测试、确定性排序 | 技术路线可行，但成本较高，而且结果高度依赖外部需求和测试是否真实 |
| 公共 Alpha 0.1 | 抽成独立 Python 仓库，支持 Codex 和通用命令适配器 | 已成为可运行工具，但定位仍偏重“多 Agent 竞赛” |
| Guard-first 草案 | 尝试用 profile、文件预算和自动简化判断补丁范围 | 实测出现误报、空补丁假成功和脏工作树归因错误，设计过于 hardcode |
| 0.2 收缩 | 删除通用阈值和语义裁决，增加任务开始快照和事实报告 | 默认能力稳定为“任务级改动归因”；Tournament 只保留为显式可选模式 |
| 0.2 公开验证 | 推送 Guard-first 实现并增加最小 GitHub Actions 测试矩阵 | 公开 main 已与当前设计一致，三组受支持 Python 测试通过 |

对应的两个提交是：

- `01c7465 feat: add evidence-driven patch tournament`
- `1df44f7 feat: add factual task-diff guard`
- `1cfcbd9 ci: add supported Python test matrix`

设计收缩的详细原因见 [DESIGN.md](DESIGN.md)，使用方式见 [README.md](README.md)。

## 现在已经做成什么样

### 默认的 Patch Guard

已经实现：

- 在 Agent 修改前记录完整任务起点，包括已跟踪和未跟踪改动。
- 在任务结束后排除起点之前已有的脏工作树内容。
- 报告新增、修改、删除文件，以及逐文件行数和二进制标记。
- 空改动明确返回 `empty`，不会伪装成通过。
- 只有调用方明确提供的 `--protect` 路径或 glob 才能产生 `constraint_violation`。
- 快照不能跨仓库误用，也不能被静默覆盖。
- 不修改 Git index。
- 提供可供 Codex 使用的 `patch-guard` Skill。

默认结果只有：

- `observed`：成功观察到本任务改动，不代表代码正确。
- `empty`：没有本任务改动，不代表任务完成。
- `constraint_violation`：碰到了调用方明确保护的边界。
- `error`：快照、仓库或 Git 操作无效。

### 可选的 Tournament

已经实现：

- 从同一 Git revision 创建多个隔离候选工作区。
- 支持 Codex CLI 和参数数组形式的通用命令适配器。
- 将可见 issue 提供给候选，将 approved-hidden 测试只提供给 grader。
- 先做基线自证，再运行候选，避免用无效测试产生伪结论。
- 只让 `existing`、`reproduction` 和 `approved-hidden` 检查决定资格；`speculative` 不能淘汰候选。
- 在合格候选中按依赖清单、生产文件数、生产改动行数、总补丁大小确定性排序。
- 默认只输出报告和 `winner.patch`，不会自动应用。

这个模式仍然是实验/评测能力，不是默认日常工作流。

### 工程状态

本次 fresh verification 结果：

```text
PYTHONPATH=src python3 -m unittest discover -v
Ran 38 tests
OK
```

另外已经确认：

- 当前版本号为 `0.2.0`。
- 本机 `patch-tournament` CLI 可运行。
- 本机 `patch-guard` Skill 已链接到这个仓库。
- GitHub `main` 已包含 `1df44f7` 的 0.2 Guard-first 实现。
- 仓库已有最小 CI，对 push 和 pull request 运行 Python 3.11、3.12、3.13 测试矩阵。
- 首次远端 CI 三组全部通过，运行记录为 [GitHub Actions #33322071708](https://github.com/majiayu000/patch-tournament/actions/runs/33322071708)。
- 当前仍没有 Git tag、GitHub Release 或 Python 包发布闭环。

## 完成度判断

| 维度 | 当前状态 | 判断 |
|---|---|---|
| 产品问题和边界 | 已明确 | 默认不再声称判断“是否过度设计” |
| Patch Guard 核心实现 | 已完成 | 可在本机真实使用 |
| 自动化测试 | 已建立 | 38 个单元、集成和安全路径测试在 Python 3.11–3.13 持续通过 |
| Tournament 原型 | 已完成 | 可显式运行，但成本和风险高于默认路径 |
| 真实日常价值验证 | 未完成 | 尚无 Guard-first 在多类真实任务上的 TP/FP、漏报、token 和耗时数据 |
| 公共发布 | 部分完成 | 0.2 和 CI 已公开，无 tag、release 和包发布闭环 |
| 稳定版承诺 | 不应给出 | 目前应继续标为 Alpha |

所以更准确的说法是：**核心代码、产品方向和最小公共 CI 已经完成，但还没有证明它在多类真实任务中持续有用，也还不是稳定 release。**

## 还差什么

### 现在必须做

1. **用真实任务验证 Patch Guard，而不是继续增加规则**

   选择 5 到 10 个不同类型的实际任务，在任务开始前自动记录快照，结束后保存 Guard JSON，并记录：

   - 是否准确排除了任务前已有改动。
   - 是否漏掉了本任务修改。
   - Agent 能否根据事实发现无关改动。
   - 是否产生误导或为了缩小 diff 而过度修复。
   - 额外 token 和耗时。

   在这些数据出来之前，不应再加入 profile、阈值、语言分类表或自动重试。

2. **完成验证后的发布决策**

   当前 0.2 和 CI 已经公开，但还不应仅凭单元测试创建稳定版承诺。积累真实任务数据后，再决定是只创建 Alpha tag/GitHub Release，还是同时发布 Python 包。

### 有证据后再决定

1. **是否需要输出任务专属 patch/hunk**

   当前 Guard 能准确给出任务拥有的文件状态和行数，但 `capture_task_inspection` 不输出任务专属 patch 内容。对于同一个脏文件中既有用户修改又有 Agent 修改的情况，它能证明文件和改动量，却不能直接展示本任务的具体 hunk。

   如果真实使用表明 Agent 需要逐 hunk 解释范围，再增加这一项；不要提前扩成语义审查器。

2. **Tournament 的环境隔离**

   当前命令执行会继承父进程环境。即使 Codex 使用临时 `CODEX_HOME`，候选和检查命令仍可能看到调用进程中的其他环境变量。Tournament 只应运行可信命令；若要面向更广泛用户，应该改成默认最小环境加显式 allowlist。

3. **快照的敏感内容与清理策略**

   为了重建任务起点，快照会保存完整 worktree patch，其中可能包含未提交的敏感内容。当前建议放在 `.git/patch-tournament/`，但还没有过期清理、加密或脱敏机制。先在文档中明确边界，再根据真实使用决定是否实现清理命令。

4. **更多仓库与平台验证**

   当前测试覆盖临时 Git 仓库和 Python 示例，但还没有形成 Rust、TypeScript、Go、大型单仓和 submodule 场景的公开兼容矩阵。

## 现在应该怎么做

建议只执行下面三步，不扩建新系统：

1. 在接下来的 5 到 10 个真实代码任务中使用现有 `patch-guard` Skill，保存结果和人工判断。
2. 汇总任务归因错误、无关改动发现率、误导情况、额外 token 和耗时。
3. 根据真实失败决定下一项改动和发布方式。若没有明确失败，不增加 profile、dashboard、自动 reducer、自动 Tournament 或新的语义规则。

达到下面的条件后，再考虑从 Alpha 升级：

- 公开 main 与本地一致，并有 CI 持续验证。此项已经完成。
- 多类真实任务中没有任务归因错误或用户改动损坏。
- Guard 的报告确实帮助发现范围问题，而不是只增加流程和 token。
- Tournament 的安全边界被清楚记录，或环境继承问题得到修复。
- README 中每一项公开承诺都有当前代码和 fresh test 支撑。

## 明确不做什么

为了避免重走 J-Space 的路线，当前主线不应加入：

- 通用文件数和行数预算。
- `local`、`standard`、`broad` 等内置 scope profile。
- 基于文件名猜测语义并自动阻止 Agent。
- Guard 触发后的自动简化或反复修复循环。
- 默认启动额外模型。
- 自动应用 Tournament 胜者。
- 在没有真实用例前增加配置层、dashboard 或 reviewer 协议。

这个项目下一阶段的工作重点不是“继续写更多代码”，而是先证明当前这个小工具在真实任务中确实有用。
