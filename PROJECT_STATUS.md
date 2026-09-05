# Patch Tournament 项目现状

> 更新时间：2026-09-05
> 本节证据来源：远端 main 审计、临时 Git 仓库复现、当前修复和 fresh test。

## 一句话结论

Patch Tournament 已恢复“三个隔离 Agent 竞赛、独立验证、选择最小合格补丁”为主工作流；事实型 Patch Guard 保留为低成本的任务级改动归因工具。

**0.3.0a1 Alpha 已发布到 GitHub Release**，发布提交为 `9e539221dd2bc95f99eb39adc2348eebfa5482a9`。本次处理修复了五类已复现的问题：零有效验收门槛仍产生胜者、候选修改验收测试、文件重命名导致统计中断、Git export 属性破坏任务起点、Python 导入缓存污染胜者补丁。

每项 gating check 现在必须声明 `evidence_paths`，列出验收脚本、fixture、helper 和配置文件。缺失文件在生成前报错；候选修改声明的文件或替换其父路径会失去资格。隐藏文件仍由 overlay 提供。调用方负责声明完整验收输入，工具不推断依赖，也不把可执行候选代码当作安全沙箱。

Git 快照改为读取原始提交 blob，保留 export-ignore/export-subst 文件、二进制、执行权限及仓库内软链接；明确拒绝 submodule 和越界链接。重命名按删除加新增统一统计。

安装说明已改为可验证的 Git 源码安装路径；PyPI 发布状态以发布工作流及包索引的实际结果为准。版本仍为 Alpha，不承诺已经证明降低过度设计或具备自动 PR 生命周期管理能力。

[远端 CI #33935340849](https://github.com/majiayu000/patch-tournament/actions/runs/33935340849) 的 Python 三版本测试和 wheel 安装均通过。[GitHub Release](https://github.com/majiayu000/patch-tournament/releases/tag/v0.3.0a1) 已附上由发布工作流构建的源码包和 wheel；从远端提交安装、从 Release 下载 wheel 安装均已验证。

[PyPI 上传 #33935399282](https://github.com/majiayu000/patch-tournament/actions/runs/33935399282) 在身份交换阶段返回 `invalid-publisher`，构建和测试已通过。PyPI 未匹配到 Trusted Publisher，需要账户所有者在 [Publishing](https://pypi.org/manage/account/publishing/) 登记或核对以下配置：项目 `patch-tournament`、GitHub owner `majiayu000`、repository `patch-tournament`、workflow `publish.yml`、environment `pypi`。首次发布使用 pending publisher；参见 [PyPI 官方说明](https://docs.pypi.org/trusted-publishers/creating-a-project-through-oidc/)。配置完成后可执行 `gh run rerun 33935399282 --repo majiayu000/patch-tournament --failed`。当前不声称 PyPI 发布成功。

本次 fresh verification：Python 3.11、3.12、3.13、3.14 分别通过 54 项测试；源码包和 wheel 构建成功，wheel 在独立环境安装后 CLI 返回 `0.3.0a1`。新增回归覆盖验收篡改、零门禁、缺失验收文件、父目录软链接、重命名、export 属性、二进制和执行权限。

### 2026-09-05 真实模型对照

用 Codex CLI 0.153.2 在本库历史提交 `0f608365362dfbe82d9e91ed63c9291b9fab860b` 上修复重命名故障。单候选和三候选分别使用相同需求、原有测试和外部隐藏回归；隐藏回归验证旧路径仍出现在改动列表、统计对应完整以及补丁能应用到新 grader。所有既有测试文件均列为受保护验收输入。模型采用 CLI 默认值，保存的 JSONL 尾部没有有效模型标识，因此不声称固定模型的可重复基准。

| 运行 | 合格候选 | 墙钟耗时 | 胜者生产改动行 | 胜者总改动行 | 合计输入 token | 其中缓存输入 | 合计输出 token |
|---|---|---|---|---|---|---|---|
| 单候选 | 1/1 | 115.63 秒 | 9 | 68 | 226,750 | 200,320 | 1,950 |
| 三候选 | 3/3 | 125.25 秒 | 8 | 8 | 765,940 | 686,336 | 5,747 |

人工查看胜者补丁确认，两者都通过禁用 Git 重命名折叠修复问题；单候选另加了 59 行回归测试，三候选胜者未增加测试。总行数减少主要来自测试差异，不能据此称为“减少过度设计”。三候选未缓存输入为 79,604，单候选为 26,430，约为三倍；并行使墙钟耗时只增加约 8%。这是一次真实故障回放，不构成跨任务收益结论，也未自动应用任何实验胜者。

## 历史记录（截至 2026-09-02）

下面保留此前的实验过程和当时判断。其中测试数量、待办和发布状态是历史数据；当前状态以上面的 2026-09-05 更新为准。

## 这个库在解决什么问题

它最初要解决的问题是 Codex 容易在一个本来很小的任务中增加不必要的抽象、文件、依赖或相邻重构。

早期方案是同时生成多个补丁，用独立测试淘汰错误方案，再从正确方案中选择改动较小者。真实 Harness 历史问题证明，这个方法有时确实能从多个正确候选中选出更小的实现，但它也带来更多 token、运行时间和评分系统复杂度。

后来发现，更危险的问题是让一个通用程序用固定文件数、行数、文件名分类和 profile 判断“是否过度设计”。这些硬编码会误伤合理修改，并可能驱使 Agent 为了通过指标而删除必要代码。J-Space 的历史进一步说明，模式、阈值、配置和例外表一旦增长快于真实执行与测试，系统会越来越难维护。

因此 0.2 的产品边界改成了下面这样：

```text
主工作流

用户显式运行 -> 三个隔离候选 -> 独立检查 -> 最小合格补丁报告

低成本辅助路径

任务开始快照 -> 一个主 Agent 实现 -> 项目测试 -> 本任务 Diff Facts
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

### 辅助的 Patch Guard

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

### 主工作流 Tournament

已经实现：

- 从同一 Git revision 创建多个隔离候选工作区。
- 支持 Codex CLI 和参数数组形式的通用命令适配器。
- 将可见 issue 提供给候选，将 approved-hidden 测试只提供给 grader。
- 先做基线自证，再运行候选，避免用无效测试产生伪结论。
- 只让 `existing`、`reproduction` 和 `approved-hidden` 检查决定资格；`speculative` 不能淘汰候选。
- 在合格候选中按依赖清单、生产文件数、生产改动行数、总补丁大小确定性排序。
- 默认只输出报告和 `winner.patch`，不会自动应用。

这个模式现在是仓库的主工作流，但仍必须由用户或调用方显式启动，且只输出报告，不自动应用胜者。

### 工程状态

本次插件评估后的 fresh verification 结果：

```text
PYTHONPATH=src python3 -m unittest discover -v
Ran 47 tests
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

## Codex 插件完整实测

测试日期为 2026-08-31。测试目标不是证明目录结构正确，而是分别验证 Codex 是否能安装插件、Hook 是否真的介入一次普通任务、任务前脏改动是否会被正确排除，以及 Tournament 是否能用真实 Codex 候选完成生成、隐藏测试和选优。

### 测试方案与结果

| 层级 | 用例 | 验收标准 | 结果 |
|---|---|---|---|
| 包结构 | 官方插件校验器和 Skill 校验器 | manifest、默认 Hook 和 Skill 均可被 Codex 识别 | 通过 |
| Hook 单元测试 | PreToolUse、Stop、并发首次快照、空改动、第二次 Stop、非 Git、错误输入 | 快照幂等；无改动静默；错误明确；不形成 Stop 循环 | 6/6 通过 |
| 整库回归 | Guard、Tournament、CLI、Git、安全和选择逻辑 | 新插件不能破坏已有能力 | 47/47 通过 |
| 真实安装 | 一次性本地 Marketplace 安装 `patch-guard@patch-guard-eval` | `codex plugin list` 显示 installed、enabled、版本 0.2.0 | 通过 |
| Hook 黑盒 | 仓库在任务前已修改 `legacy.py`，新 Codex 会话只允许改 `app.py`，禁止手动调用 Skill/CLI | 自动建立一份快照；只认领 `app.py`；保留 `legacy.py`；结束时输出 Hook Warning 且不产生续轮 | 通过 |
| Git 配置故障 | 用户全局启用 commit signing，但沙箱不能访问 GPG | 临时比较仓库仍能建立基线 | 首次真实测试失败；增加 `git commit --no-gpg-sign` 后回归通过 |
| 真实 Tournament | 两个并行 Codex 候选、一个候选不可见的 approved-hidden 测试、report-only 输出 | 两个候选隔离生成；隐藏测试判定资格；选出胜者；不改源仓库 | 主链路通过，产物卫生失败 |

### 自动 Hook 的真实结果

决定性黑盒用例没有调用 `patch-tournament snapshot`、`patch-tournament guard` 或 `$patch-guard`。Codex 只执行普通查看、修改和 diff 命令。插件在数据目录新增了恰好一份任务起点快照，快照记录任务前的 changed files 只有 `legacy.py`；Codex 完成后，Stop Hook 通过 `systemMessage` 输出范围报告，只把 `app.py` 认领为本任务改动。

最后一次无续轮回归使用 47,291 input tokens，其中 37,120 为 cached input，216 output tokens。Token 数包含当前 Codex 会话的全局上下文，不能全部归因于插件。整个任务只有一次 `turn.started` 和一次 `turn.completed`；`systemMessage` 被记录为 Hook Warning，不会作为 continuation prompt 再次调用模型。`codex exec --json` 当前也不会把这条 Warning 作为普通 JSONL 消息输出。

另一次安装测试中，本机已有的同名全局 Skill 也被触发，导致“手动 Skill + 自动 Hook”重复执行。它没有破坏结果，但说明正式安装说明必须收敛入口：安装插件后不应再同时保留旧的手动 Skill 链接。

### 真实 Tournament 的结果

两个 `gpt-5.4` 候选并行运行，分别用了 98,122 和 115,706 input tokens，输出 1,361 和 1,826 tokens。两个候选都修改了 `clamp.py`，都通过了候选不可见的隐藏回归测试，`c01` 被确定性选为胜者；源仓库中的 `clamp.py` 始终保持原样，证明 report-only 和隔离 grader 生效。

当时两个候选自测时都生成了未忽略的 `__pycache__/clamp.cpython-314.pyc`，导致 `winner.patch` 被污染。2026-09-02 的三候选自举任务为候选进程设置 `PYTHONDONTWRITEBYTECODE=1`，三个候选独立得出同一生产修复；独立隐藏回归和完整 47 项测试均通过。该已知 Python 字节码污染路径现已修复。

### 能力结论

Codex 插件可以替代 Guard 辅助工作流里的人工 snapshot/guard 命令，用户只需要正常让 Codex 改代码。它不会在 Stop Hook 中启动 Tournament；三候选主工作流由用户或调用方显式运行，并需要可见需求、独立检查和输出目录。

所以准确结论是：**Tournament 是主工作流，插件是低成本归因辅助，两者不是互相替代关系。** 当前仍为 Alpha，胜者补丁必须经过用户或 Reviewer 审查后再应用。

## 完成度判断

| 维度 | 当前状态 | 判断 |
|---|---|---|
| 产品问题和边界 | 已明确 | 通过正确候选之间的相对选优降低过度设计风险，不声称通用语义裁决 |
| Patch Guard 核心实现 | 已完成 | 可在本机真实使用 |
| 自动化测试 | 已建立 | 38 个单元、集成和安全路径测试在 Python 3.11–3.13 持续通过 |
| Tournament 主流程 | 已完成 | 三候选可显式运行，独立 grader 和最小合格补丁选择已验证 |
| 真实日常价值验证 | 未完成 | 尚无 Guard-first 在多类真实任务上的 TP/FP、漏报、token 和耗时数据 |
| 公共发布 | 部分完成 | 0.2 和 CI 已公开，无 tag、release 和包发布闭环 |
| 稳定版承诺 | 不应给出 | 目前应继续标为 Alpha |

所以更准确的说法是：**核心代码、产品方向和最小公共 CI 已经完成，但还没有证明它在多类真实任务中持续有用，也还不是稳定 release。**

## 还差什么

### 现在必须做

1. **已完成：修复 Tournament 的候选产物污染**

   Python 候选自测生成的 `__pycache__`、`.pyc` 已不会进入候选补丁和规模排序。实现只设置候选进程环境，不增加通用文件名过滤或规则引擎，并有端到端回归覆盖。

2. **用真实任务继续验证三候选 Tournament，而不是继续增加规则**

   选择不同类型的实际任务，对比单 Agent 与三候选 Tournament，并记录：

   - 独立检查通过率和人工正确性判断。
   - 胜者是否减少了无关文件、依赖和不必要抽象。
   - 较大补丁是否包含必要复杂度，避免把“更小”等同于“更好”。
   - 三候选相对单 Agent 的额外 token 和耗时。

   在这些数据出来之前，不应再加入 profile、阈值、语言分类表或自动重试。

3. **收敛 Codex 安装入口并完成发布决策**

   插件安装后不要再保留同名的全局手动 Skill，否则同一任务会重复快照和复核。当前 0.2 和 CI 已经公开，但还不应仅凭单元测试创建稳定版承诺。修复 Tournament 产物污染并积累真实任务数据后，再决定是只创建 Alpha tag/GitHub Release，还是同时发布 Python 包和插件。

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

1. 在接下来的真实高风险代码任务中显式运行三候选 Tournament，保存三份补丁、grader 结果和人工判断。
2. 汇总正确率、无关改动、必要复杂度、额外 token 和耗时；普通小任务仍可只用 Patch Guard。
3. 根据真实失败决定下一项改动和发布方式。若没有明确失败，不增加 profile、dashboard、自动 reducer 或新的语义规则。

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
