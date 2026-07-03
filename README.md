# QuantSkills 仓库审计 Skill

**简体中文** | [English](README.en.md)

> 扫描 `quantskills` 组织仓库，检查仓库命名、更新测试决策、GitHub 组织首页、registry / quantskills 索引和技能/Agent 结构是否齐全。

![type](https://img.shields.io/badge/type-skill-blue)
![license](https://img.shields.io/badge/license-GPL--3.0--only-blue)

## 这是什么

这个 Skill 面向 QuantSkills 社区治理和仓库发布前检查。它会读取 GitHub 组织仓库列表，默认把 `.github`、`demo-repository`、`join`、`quantskills` 和 `registry` 作为例外，其余仓库都应根据项目类型使用 `skill-` 或 `agent-` 前缀。

它还会检查仓库根目录是否有 `README.md`。如果本地存在对应 checkout，并且显式传入 `--fix-local-readme`，脚本可以把已有的嵌套 README 复制到根目录，或者生成一个最小中文优先 README 模板。

新增的更新检查模式会维护一个本地 JSON 状态文件：新上传项目必须测试；已经通过首次测试/复核的项目如果后续更新，会先判断变更文件。代码、脚本、依赖、运行时入口、声明文件、工作流或无法判断的变更会标记为 `test-required`；仅文档、许可证、示例或静态资源的低风险更新会标记为 `review-only`，复核无问题后可以跳过测试。

本 Skill 包发布目标是个人仓库 `abgyjaguo/skill-quantskills-repo-auditor`；它审计和同步的目标仍然是 `quantskills` 组织。

当本地 checkout 存在时，它还会扫描 README、声明文件和 manifest 文本，提示可能的密钥、收益承诺、官方背书、缺少 `GPL-3.0-only` 元数据和投资工作流风险声明问题。`quantskills` 导航分类只自动采用 registry 的正式 `category` 枚举；关键词命中只作为待维护者确认的建议，不直接写入 `categoryOverride`。

## 快速开始

```bash
python scripts/audit_quantskills_repos.py --org quantskills
```

包含私有仓库时：

```bash
python scripts/audit_quantskills_repos.py --org quantskills --token %GITHUB_TOKEN% --include-private
```

同时检查本地 checkout，并只在明确需要时修复缺失的根 README：

```bash
python scripts/audit_quantskills_repos.py --org quantskills --local-root D:/quantskill --fix-local-readme
```

输出 JSON 和 Markdown：

```bash
python scripts/audit_quantskills_repos.py --org quantskills --markdown report.md --json-output report.json
```

扫描组织内当前 token 可见的全部仓库，并把可安全执行的治理动作写入报告：

```bash
python scripts/audit_quantskills_repos.py --org quantskills --include-private --plan-governance-actions --markdown report.md --json-output report.json
```

补充恢复 public、失效仓库和三处索引同步计划：

```bash
python scripts/audit_quantskills_repos.py --org quantskills --include-private --plan-governance-actions --plan-public-restore --report-stale-repos --plan-index-updates --local-root D:/quantskill --markdown report.md --json-output report.json
```

在明确需要同步索引时，更新 GitHub 组织首页源文件并运行 registry / quantskills 生成器：

```bash
python scripts/audit_quantskills_repos.py --org quantskills --include-private --apply-index-updates --local-root D:/quantskill --markdown report.md --json-output report.json
```

规划新上传或更新项目是否需要测试：

```bash
python scripts/audit_quantskills_repos.py --org quantskills --include-private --plan-update-tests --state-file outputs/update-check-state.json --local-root D:/quantskill --markdown report.md --json-output report.json
```

对需要测试的本地仓库运行可识别的测试或 smoke test：

```bash
python scripts/audit_quantskills_repos.py --org quantskills --include-private --plan-update-tests --run-update-tests --test-repo skill-example --state-file outputs/update-check-state.json --local-root D:/quantskill --markdown report.md --json-output report.json
```

测试通过或低风险更新复核通过后，显式写入验收基线：

```bash
python scripts/audit_quantskills_repos.py --org quantskills --include-private --plan-update-tests --write-state --mark-tested skill-example --state-file outputs/update-check-state.json --local-root D:/quantskill
```

在明确需要远端治理修复时执行动作：

```bash
python scripts/audit_quantskills_repos.py --org quantskills --include-private --apply-governance-actions --markdown report.md --json-output report.json
```

显式恢复已修复仓库为 public：

```bash
python scripts/audit_quantskills_repos.py --org quantskills --include-private --apply-public-restore --markdown report.md --json-output report.json
```

## 最终工作流

这个 Skill 的完整工作流分为七段：

1. **检查今日社区更新**：按 Asia/Shanghai 今日窗口检查 `quantskills` 组织中新建或更新的 `skill-*`、`agent-*`、`join`、`registry`、`.github` 等仓库，记录重要提交、Issue/PR、失败 Actions、需要维护者响应的事项，并检查 `D:/quantskill` 本地嵌套仓库与远端的明显不同步状态。
2. **规划和运行更新测试**：对新仓库输出 `test-required`；对已验收后更新的仓库先比较 commit/文件范围，运行时代码和结构变更继续测试，低风险文档/许可证/示例/静态资源变更进入 `review-only`。显式传入 `--run-update-tests` 时，会对本地 checkout 运行 `scripts/validate.py`、`python -m unittest discover -s tests`、`npm test` 或 Python 编译 smoke test；找不到 checkout 或测试命令会标记为 blocked。
3. **识别需要注意的风险**：重点看新仓库命名、skill 包结构、`SKILL.md`、`GPL-3.0-only`、`LICENSE`、中文优先 `README.md`、`README.en.md`、五运行时入口、过度承诺、投资建议风险、敏感信息迹象、发布阻塞 PR/Issue 和本地脏工作区。命名不符合规范、`skill-*` 缺 `SKILL.md`、`agent-*` 缺 `AGENTS.md` 时，仓库应设为 private，并留言中英文整改 Issue 和社区规则链接；修复、无 fail 级问题且仍有打开的整改 Issue 后，再规划或执行恢复 public。
4. **停在确认点**：巡查后只输出候选动作和影响范围，等待维护者选择。没有维护者确认前，不执行 `--apply-governance-actions`、`--apply-public-restore`、`--apply-index-updates`、`--write-state`、测试执行、提交或推送。每次必须列出所有会被设为 private 的仓库和具体原因。
5. **同步组织主页 / registry / quantskills**：维护者确认后，必要时更新 `D:/quantskill/.github/profile/README.md`，也就是 [github.com/quantskills](https://github.com/quantskills) 组织首页显示的源文件，使中文 `## 🗂️ 社区技能仓库一览` 和英文 `## 🗂️ Community Skill Repositories` 表格匹配 GitHub org 当前公开 `skill-*` 清单；同时检查 public `skill-*` / `agent-*` 是否需要进入 `registry` 和 `quantskills/quantskills`。不把非 `skill-*` 仓库放入技能表，描述保持简洁、诚实、不夸大；生成型文件优先运行各仓库脚本，不手工编辑生成产物。导航分类只自动同步 registry 正式分类，关键词猜测只输出建议。维护者要求远端索引同步时，必须把 `.github`、`registry`、`quantskills` 三个目标一起提交、推送并验证远端 HEAD，一处无变化也要说明。
6. **安全提交和推送**：维护者确认发布后，主页有变化时，先检查 `.github` 工作区、远端 URL、Markdown/链接/差异，再用 `abgyjaguo <213890245+abgyjaguo@users.noreply.github.com>` 提交并推送 `main`；任何不确定、脏工作区、远端不匹配、凭据或验证失败都停止并写入简报。
7. **输出中文简报**：固定包含 `今日社区更新`、`需要我注意`、`主页技能仓库一览更新结果`、`验证/推送状态`、`下一步建议`，并列出具体仓库名、链接、Issue/PR 编号或提交哈希。

## 检查内容

| 检查 | 规则 |
| --- | --- |
| 仓库命名 | 除 `.github`、`demo-repository`、`join`、`quantskills`、`registry` 外，应以 `skill-` 或 `agent-` 开头 |
| 类型推断 | 根据 `SKILL.md`、`AGENTS.md`、仓库描述和 topic 推断 skill/agent |
| 首页 README | 根目录应有标准 `README.md` |
| 声明文件 | skill 仓库应有 `SKILL.md`，agent 仓库应有 `AGENTS.md` |
| 双语文档 | 发布型 skill 仓库应有中文优先 `README.md` 和 `README.en.md` |
| 运行时入口 | Codex / Claude Code 使用根 `SKILL.md`；Cursor 使用 `agents/cursor-rule.mdc`；Hermes 使用 `agents/portable-loader.md`；OpenClaw 使用 `agents/openai.yaml` 或 portable loader |
| 内容合规 | 本地 checkout 存在时扫描密钥形态、收益承诺、官方背书、`GPL-3.0-only` 元数据和投资风险声明 |
| 更新测试 | 新项目和高风险更新为 `test-required`，低风险文档/资产变更为 `review-only`，未变化为 `skip` |
| 索引同步 | GitHub 组织首页来自 `.github/profile/README.md`；`registry` 按生成器规则忽略模板和 quarantined 项；`quantskills` 只应展示公开仓库 |

## 安全边界

默认扫描不会自动重命名 GitHub 仓库，不会 push，不会删除仓库，也不会更改仓库可见性。远端治理修复必须显式使用 `--apply-governance-actions` 或 `--apply-public-restore`。

每次巡查后都必须先列出候选动作并等待维护者确认。候选动作需要说明会影响哪些仓库、是否写 GitHub Issue、是否改变可见性、是否写本地索引、是否跑测试、是否写更新验收基线；确认前不实施。会设为 private 的仓库必须逐项列出原因。

状态文件默认只在显式传入 `--write-state` 时写入；不要在测试未通过或低风险复核未完成前使用 `--mark-tested`。

`--run-update-tests` 只收集测试证据，不会自动写入验收基线。只有测试通过或 `review-only` 复核通过后，才使用 `--write-state --mark-tested`。

GitHub 组织首页、`registry` 与 `quantskills` 都是索引目标。`--apply-index-updates` 会更新 `.github/profile/README.md`，并运行 registry / quantskills 的本地生成脚本；维护者要求远端索引同步时，提交和推送也属于该动作的一部分，必须分别验证 `.github`、`registry`、`quantskills` 工作区、远端 URL、生成结果、凭据和远端 HEAD。

`registry` 与 `quantskills` 是生成型索引。同步时先运行各自仓库脚本，不手工编辑生成产物；`registry` 可排除 `skill-template`、`agent-template` 和最新扫描报告中 `quarantined` 的仓库，`quantskills` 生成器应只读取公开仓库。

`--apply-governance-actions` 只处理当前已经明确安全的动作：

- 仓库命名错误：设为 private，并创建或更新中英文社区规则整改 Issue。
- `skill-*` 仓库缺 `SKILL.md`：设为 private，并创建或更新中英文整改 Issue。
- `agent-*` 仓库缺 `AGENTS.md`：设为 private，并创建或更新中英文整改 Issue。
- 缺 `README.en.md`、缺 `LICENSE`、缺运行时 adapter：不改可见性，只创建或更新中英文社区规则整改 Issue。

`--apply-public-restore` 只处理修复后、无 fail 级问题且存在打开整改 Issue 的 private `skill-*` / `agent-*` 仓库：恢复 public，并在已有整改 Issue 中留言后关闭。仓库重命名、删除、转移、registry 或主页收录仍然需要维护者人工确认。

## 目录结构

```text
skill-quantskills-repo-auditor/
|-- SKILL.md
|-- skill.yml
|-- README.md
|-- README.en.md
|-- LICENSE
|-- agents/
|   |-- openai.yaml
|   |-- cursor-rule.mdc
|   `-- portable-loader.md
`-- scripts/
    `-- audit_quantskills_repos.py
```

## 维护者

Creator / maintainer: `abgyjaguo`

## License

This project is licensed under the GNU General Public License v3.0. See [LICENSE](LICENSE).
