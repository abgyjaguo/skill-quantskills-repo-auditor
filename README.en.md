# QuantSkills Repo Auditor Skill

[简体中文](README.md) | **English**

> Audit `quantskills` organization repositories for `skill-` / `agent-` naming rules, update-test decisions, GitHub organization homepage sync, registry / quantskills index sync, and skill or agent declaration files.

![type](https://img.shields.io/badge/type-skill-blue)
![license](https://img.shields.io/badge/license-GPL--3.0--only-blue)

## What This Is

This Skill supports QuantSkills community governance and pre-publication repository checks. It reads the GitHub organization repository inventory, treats `.github`, `demo-repository`, `join`, `quantskills`, and `registry` as allowed exceptions, and reports repositories that should be renamed with a `skill-` or `agent-` prefix.

It also checks whether each repository has a root `README.md`. When a local checkout exists and `--fix-local-readme` is explicitly provided, the script can copy an existing nested README to the root or generate a minimal Chinese-first README template.

The update-check mode maintains a local JSON state file: newly uploaded projects require tests; projects that were already tested or accepted are compared against the accepted baseline when they change. Code, script, dependency, runtime adapter, declaration, workflow, or unknown-scope changes are marked `test-required`; documentation, license, example, or static-asset-only changes are marked `review-only`, so tests can be skipped after review.

This skill package is published under the personal repository `abgyjaguo/skill-quantskills-repo-auditor`; the organization it audits and synchronizes remains `quantskills`.

When local checkouts are available, it also scans README, declaration, and manifest text for possible secrets, promised returns, official-endorsement claims, missing `GPL-3.0-only` metadata, and missing risk disclosure for investment workflows.

For `quantskills` navigation, automatic category overrides come from canonical registry `category` enum values and high-confidence business-signal matches. Business-signal matches that pass the score and margin gates are written to `categoryOverride` with rationale kept for audit traceability.

## Quick Start

```bash
python scripts/audit_quantskills_repos.py --org quantskills
```

Include private repositories:

```bash
python scripts/audit_quantskills_repos.py --org quantskills --token %GITHUB_TOKEN% --include-private
```

Check local checkouts and explicitly fix missing root READMEs:

```bash
python scripts/audit_quantskills_repos.py --org quantskills --local-root D:/quantskill --fix-local-readme
```

Write JSON and Markdown reports:

```bash
python scripts/audit_quantskills_repos.py --org quantskills --markdown report.md --json-output report.json
```

Scan all repositories visible to the current token and add safe remediation actions to the report:

```bash
python scripts/audit_quantskills_repos.py --org quantskills --include-private --plan-governance-actions --markdown report.md --json-output report.json
```

Plan public restoration, stale repository reporting, and homepage / registry / quantskills index updates:

```bash
python scripts/audit_quantskills_repos.py --org quantskills --include-private --plan-governance-actions --plan-public-restore --report-stale-repos --plan-index-updates --local-root D:/quantskill --markdown report.md --json-output report.json
```

Apply index synchronization when explicitly approved. This updates the GitHub organization profile source and runs local registry / quantskills generators:

```bash
python scripts/audit_quantskills_repos.py --org quantskills --include-private --apply-index-updates --local-root D:/quantskill --markdown report.md --json-output report.json
```

Plan which new or changed repositories need tests:

```bash
python scripts/audit_quantskills_repos.py --org quantskills --include-private --plan-update-tests --state-file outputs/update-check-state.json --local-root D:/quantskill --markdown report.md --json-output report.json
```

Run detected local tests or smoke tests for selected test-required repositories:

```bash
python scripts/audit_quantskills_repos.py --org quantskills --include-private --plan-update-tests --run-update-tests --test-repo skill-example --state-file outputs/update-check-state.json --local-root D:/quantskill --markdown report.md --json-output report.json
```

After tests pass or a review-only update is accepted, explicitly write the accepted baseline:

```bash
python scripts/audit_quantskills_repos.py --org quantskills --include-private --plan-update-tests --write-state --mark-tested skill-example --state-file outputs/update-check-state.json --local-root D:/quantskill
```

Apply safe remote governance remediation when explicitly requested:

```bash
python scripts/audit_quantskills_repos.py --org quantskills --include-private --apply-governance-actions --markdown report.md --json-output report.json
```

Restore eligible fixed repositories to public when explicitly requested:

```bash
python scripts/audit_quantskills_repos.py --org quantskills --include-private --apply-public-restore --markdown report.md --json-output report.json
```

## Final Workflow

The full Skill workflow has seven phases:

1. **Check today's community updates**: use the Asia/Shanghai day window to inspect newly created or updated `skill-*`, `agent-*`, `join`, `registry`, `.github`, and related repositories; capture important commits, Issues/PRs, failed Actions, maintainer-response items, and obvious local drift under `D:/quantskill`.
2. **Plan and run update testing**: mark new repositories as `test-required`; for repositories changed after an accepted baseline, compare commits and changed files first. Runtime, code, structure, dependency, or unknown changes still require tests; low-risk documentation, license, example, or static asset changes are `review-only` and may skip tests after review. With explicit `--run-update-tests`, local checkouts run detected commands such as `scripts/validate.py`, `python -m unittest discover -s tests`, `npm test`, or Python compile smoke checks; missing checkouts or missing deterministic commands are reported as blocked.
3. **Identify risks needing attention**: prioritize naming violations, missing skill package files, `SKILL.md`, `GPL-3.0-only`, `LICENSE`, Chinese-first `README.md`, `README.en.md`, five-runtime adapters, over-promising descriptions, investment-advice risk, sensitive-information signals, blocked PRs/Issues, and dirty local worktrees. Naming-noncompliant repositories, `skill-*` repositories missing `SKILL.md`, and `agent-*` repositories missing `AGENTS.md` should be kept private with a bilingual remediation Issue and community rules link; after fixes, no fail-level audit issues, and a matching open remediation Issue, plan or apply public restoration.
4. **Stop at a confirmation checkpoint**: after a patrol, report candidate actions and their impact, then wait for the maintainer to choose. Before maintainer confirmation, do not run `--apply-governance-actions`, `--apply-public-restore`, `--apply-index-updates`, `--write-state`, test execution, commits, or pushes. Always list every repository that would be set private and the concrete reason.
5. **Sync homepage / registry / quantskills**: after maintainer confirmation, update `D:/quantskill/.github/profile/README.md` when needed, the source shown on [github.com/quantskills](https://github.com/quantskills), especially the Chinese `## 🗂️ 社区技能仓库一览` and English `## 🗂️ Community Skill Repositories` tables, so they match the current public `skill-*` inventory. Also check whether every public `skill-*` and `agent-*` repository needs corresponding entries in `registry` and `quantskills/quantskills`. Keep descriptions concise, honest, non-promotional, and do not include non-skill repositories in the skill table. Prefer repository build scripts for generated artifacts instead of editing generated files by hand. Navigation categories are synchronized from canonical registry categories and high-confidence business-signal matches; low-confidence or conflicting signals remain unwritten. When the maintainer asks for remote index sync, commit, push, and verify all three targets: `.github`, `registry`, and `quantskills`; explicitly report any target that was unchanged.
6. **Commit and push safely**: after maintainer publication approval, when the homepage changes, verify `.github` cleanliness, remote URL, Markdown/link/diff checks, then commit as `abgyjaguo <213890245+abgyjaguo@users.noreply.github.com>` and push `main`. Stop and report blockers on dirty worktrees, remote mismatch, credential failures, validation failures, or uncertainty.
7. **Produce the Chinese brief**: use the fixed sections `今日社区更新`, `需要我注意`, `主页技能仓库一览更新结果`, `验证/推送状态`, and `下一步建议`, with concrete repository names, links, PR/Issue numbers, workflow names, or commit hashes.

## Checks

| Check | Rule |
| --- | --- |
| Repository naming | Except `.github`, `demo-repository`, `join`, `quantskills`, and `registry`, repositories should start with `skill-` or `agent-` |
| Type inference | Infer skill or agent from `SKILL.md`, `AGENTS.md`, description, and topics |
| Homepage README | A standard root `README.md` should exist |
| Declaration file | Skill repositories should have `SKILL.md`; agent repositories should have `AGENTS.md` |
| Bilingual docs | Published skill repositories should include Chinese-first `README.md` and `README.en.md` |
| Runtime entrypoints | Codex / Claude Code use root `SKILL.md`; Cursor uses `agents/cursor-rule.mdc`; Hermes uses `agents/portable-loader.md`; OpenClaw uses `agents/openai.yaml` or the portable loader |
| Content compliance | With local checkouts, scans for secret-shaped assignments, promised returns, endorsement claims, `GPL-3.0-only` metadata, and investment risk disclosure |
| Update testing | New projects and high-risk updates are `test-required`, low-risk docs/assets changes are `review-only`, unchanged repositories are `skip` |
| Index sync | GitHub organization homepage comes from `.github/profile/README.md`; `registry` follows generator rules for templates and quarantined entries; `quantskills` should list public repositories only |

## Safety Boundary

By default, the script does not rename GitHub repositories, push commits, delete repositories, or change repository visibility. Remote governance writes require the explicit `--apply-governance-actions` or `--apply-public-restore` flag.

Every patrol must first report candidate actions and wait for maintainer confirmation. Candidate actions must state affected repositories, whether they write GitHub Issues, change visibility, write local index files, run tests, or write the accepted update baseline; do not apply them before confirmation. Repositories that would be set private must be listed with reasons.

The state file is written only when `--write-state` is passed. Do not use `--mark-tested` until tests have passed or the review-only change has been accepted.

`--run-update-tests` only collects evidence. It does not automatically write the accepted baseline; use `--write-state --mark-tested` only after tests pass or a review-only decision is accepted.

The GitHub organization homepage, `registry`, and `quantskills` are index targets. `--apply-index-updates` updates `.github/profile/README.md` and runs the local registry / quantskills generator scripts. When the maintainer asks for remote index sync, commits and pushes are part of that action and require separate validation of `.github`, `registry`, and `quantskills` worktree status, remotes, generated outputs, credentials, and remote HEADs.

`registry` and `quantskills` are generated indexes. Sync them by running their repository scripts instead of hand-editing generated artifacts; `registry` may exclude `skill-template`, `agent-template`, and repositories marked `quarantined` in the latest scan report, while `quantskills` should read public repositories only.

`--apply-governance-actions` only performs the currently safe remediation set:

- Repository naming errors: set private and create or update a bilingual community-rule remediation Issue.
- `skill-*` repositories missing `SKILL.md`: set private and create or update a bilingual remediation Issue.
- `agent-*` repositories missing `AGENTS.md`: set private and create or update a bilingual remediation Issue.
- Missing `README.en.md`, missing `LICENSE`, and missing runtime adapters: keep visibility unchanged and create or update a bilingual community-rule remediation Issue.

`--apply-public-restore` only handles fixed private `skill-*` / `agent-*` repositories with no fail-level audit issues and a matching open remediation Issue: set public, comment on the Issue, and close it. Repository rename, deletion, transfer, registry listing, and homepage listing still require maintainer review.

## Maintainer

Creator / maintainer: `abgyjaguo`

## License

This project is licensed under the GNU General Public License v3.0. See [LICENSE](LICENSE).
