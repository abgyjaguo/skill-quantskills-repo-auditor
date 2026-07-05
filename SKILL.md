---
name: quantskills-repo-auditor
description: "Audit and vet QuantSkills GitHub organization repositories, daily community activity, update-test decisions, and homepage skill listings. Use when checking today's quantskills updates, newly uploaded repositories, changed repositories that may need tests, repository rule violations, skill-/agent- package structure, safe remediation actions, local D:/quantskill sync drift, or .github/profile/README.md homepage table consistency."
license: GPL-3.0-only
metadata:
  organization: abgyjaguo
  organization_url: https://github.com/abgyjaguo
  repository: skill-quantskills-repo-auditor
  repository_url: https://github.com/abgyjaguo/skill-quantskills-repo-auditor
  project_type: skill
  collection: community-governance
  target_organization: QuantSkills
  target_organization_url: https://github.com/quantskills
  category: tooling
  tags: [github, audit, repository, governance, readme, registry, index-sync, update-check, vetting]
  platforms: [claude-code, codex, cursor, hermes, openclaw]
  language: zh-en
  status: draft
  validation_level: runnable
  maintainer_type: community
  requires: []
  creator: abgyjaguo
  maintainer: abgyjaguo
  summary_zh: "扫描 QuantSkills 组织仓库命名、声明文件、更新测试决策、可见性治理、失效仓库和主页/registry/quantskills 索引同步情况。"
  summary_en: Audits QuantSkills repositories for naming, declaration files, update-test decisions, visibility governance, stale repositories, and homepage/registry/quantskills index sync.
---

# QuantSkills Repo Auditor

Use this skill to audit and vet repositories in the `quantskills` GitHub organization before publication, public listing, homepage synchronization, update testing, or daily community maintenance. This skill package is maintained in the personal repository `abgyjaguo/skill-quantskills-repo-auditor`; its audit target remains the `quantskills` organization.

## Daily Community Workflow

Use this workflow for the regular QuantSkills community brief.

1. Establish the audit window.
   - Use Asia/Shanghai calendar days unless the user specifies another window.
   - Treat "today" as activity since local Shanghai midnight.
   - Use GitHub API or `gh` when available; fall back to credential-backed REST calls when CLI authentication is unavailable.

2. Check organization activity since the audit window start.
   - Inspect `https://github.com/quantskills` for newly created or updated `skill-*`, `agent-*`, `join`, `registry`, `.github`, and other visible repositories.
   - Summarize important commits, opened or updated Issues and PRs, failed GitHub Actions, and items that need maintainer response.
   - Check local nested repositories under `D:/quantskill` for obvious drift: dirty worktrees, ahead/behind branches, missing remotes, or remote URL mismatches.

3. Plan update testing before spending time on test runs.
   - Run `python scripts/audit_quantskills_repos.py --org quantskills --include-private --plan-update-tests --state-file outputs/update-check-state.json --local-root D:/quantskill` when credentials and local checkouts are available.
   - Treat repositories with no accepted baseline as `test-required`: newly uploaded projects must be tested before they are marked accepted.
   - Treat changed repositories as `test-required` when code, scripts, dependencies, workflow files, `SKILL.md`, `AGENTS.md`, `skill.yml`, `agents/`, or `references/` changed, or when the changed-file scope cannot be determined.
   - Treat documentation, license, examples, or static-asset-only updates as `review-only`: inspect claims, links, licenses, and risk language; if no problem is found, tests may be skipped.
   - Add `--run-update-tests --local-root D:/quantskill` only when the user explicitly wants local test or smoke-test commands to run. The script records blocked results when no checkout or deterministic test command is found.
   - After tests pass or a review-only update is accepted, write the baseline explicitly with `--write-state --mark-tested <repo>`; use `--mark-tested all` only after every current repository has been tested or accepted.

4. Run the repository structure audit.
   - Run `python scripts/audit_quantskills_repos.py --org quantskills --include-private --plan-governance-actions --plan-public-restore --report-stale-repos --plan-index-updates --local-root D:/quantskill` when credentials and local checkouts are available.
   - Add `--local-root D:/quantskill` when local checkouts should be inspected.
   - Add `--fix-local-readme` only when the user explicitly wants local checkout README files generated or copied into the repository root.
   - Add `--apply-governance-actions` only when the user explicitly asks to apply safe remote governance issues. This can set naming-noncompliant repositories and declaration-missing `skill-*` / `agent-*` repositories to private, and create or update a bilingual community-rule remediation Issue for naming errors, missing `README.en.md`, missing `LICENSE`, missing runtime adapters, and missing declaration files.
   - When `--apply-governance-actions` sees a public repository that no longer has community-rule remediation issues, it comments on and closes the matching open remediation Issue.
   - Add `--apply-public-restore` only when the user explicitly asks to restore eligible repositories after fixes. This can set private `skill-*` / `agent-*` repositories back to public when an open remediation Issue exists and the declaration problem plus other fail-level audit issues are resolved.
   - When `--apply-public-restore` restores an eligible repository to public, it also comments on and closes the matched remediation Issue.

5. Stop for maintainer confirmation before applying changes.
   - After a patrol or audit run, present grouped candidate actions and wait for the user to choose what to do next.
   - Do not run `--apply-governance-actions`, `--apply-public-restore`, `--apply-index-updates`, `--write-state`, Git commits, or Git pushes in the same response that reports the patrol results unless the user already explicitly approved those exact actions.
   - Include the expected effect and scope for each candidate action: affected repository names, whether it writes GitHub Issues, changes repository visibility, writes local index files, runs tests, or writes the update-check baseline.
   - Always list every repository that would be set to private and the human-readable reasons before applying `--apply-governance-actions`.

6. Identify items requiring user attention.
   - Prioritize new repositories that violate naming rules.
   - Prioritize `test-required` update-check actions before any public listing or release recommendation.
   - Prioritize skill repositories missing `SKILL.md`, `GPL-3.0-only`, `LICENSE`, Chinese-first `README.md`, `README.en.md`, or five-runtime adapter entrypoints.
   - When local checkouts are available, scan README / declaration / manifest text for possible secret assignments, over-promising return or official-verification claims, missing `GPL-3.0-only` metadata, and missing non-investment-advice risk disclosure for investment workflows.
   - For repositories with naming rule violations, `skill-*` repositories missing `SKILL.md`, and `agent-*` repositories missing `AGENTS.md`, keep the repository private and leave a bilingual remediation Issue with the community rules link.
   - When the missing declaration is fixed, the repository has no fail-level audit issues, and an open remediation Issue exists, plan or apply public visibility restoration with `--plan-public-restore` / `--apply-public-restore`.
   - Report potentially stale or invalid repositories: archived, disabled, empty or uninitialized repositories, repositories without a default branch, or repositories older than the configured stale threshold without pushes.
   - Flag project descriptions that over-promise, imply investment advice, or claim official/verified/production-ready status without approval.
   - Flag possible sensitive information in public repositories, blocked PRs or Issues, failed workflows, and dirty local worktrees that affect sync safety.

7. Sync the organization homepage when needed.
   - Compare the live public `skill-*` inventory with `D:/quantskill/.github/profile/README.md`.
   - Update the Chinese `## 🗂️ 社区技能仓库一览` and English `## 🗂️ Community Skill Repositories` tables so they reflect the current public `skill-*` repositories.
   - Preserve the existing page structure and bilingual style.
   - Add concise, honest, non-promotional descriptions for new repositories; do not imply investment advice, guaranteed returns, official certification, or production readiness.
   - Do not place non-`skill-*` repositories in the skill table.
   - Keep the agent repository table aligned with public `agent-*` inventory when necessary, while treating skill inventory as the primary target.
   - For every public `skill-*` and `agent-*`, check whether corresponding entries need to be reflected in the GitHub organization homepage (`.github/profile/README.md` shown at `https://github.com/quantskills`), `registry`, and `quantskills/quantskills`; generated files should be regenerated through their repository scripts instead of hand-editing generated artifacts.
   - Use `--apply-index-updates --local-root D:/quantskill` only when the user explicitly asks to synchronize indexes. It updates `.github/profile/README.md`, runs the registry generator, and runs the quantskills navigation generator.
   - During `--apply-index-updates`, registry generation runs before quantskills navigation generation. Canonical registry categories update `quantskills/data/curation.json` so public `skill-*` and `agent-*` repositories can appear in the correct navigation category instead of falling into "Repos not in catalog". Business-signal matches are reported with rationale as suggestions and require maintainer review.
   - When the user asks for remote index synchronization, keep all three targets aligned remotely: `.github/profile/README.md`, `registry`, and `quantskills/quantskills`. Apply local generation first, then commit and push every changed target repository, and verify each pushed remote branch matches its local HEAD. Report unchanged targets explicitly.
   - Treat `registry` as a generated asset with target-specific rules: `skill-template` and `agent-template` are intentionally excluded, and repositories marked `quarantined` by the latest `registry/reports/scan-*.json` should not be reported as missing from `registry.json`.
   - Treat `quantskills/quantskills` as a public-navigation site: its generator should use public GitHub repositories only and can use local `registry/registry.json` metadata when the registry has just been regenerated locally.

8. Commit and push homepage changes only when safe.
   - If `D:/quantskill/.github/profile/README.md` changed, first confirm `D:/quantskill/.github` is clean or only contains this task's edits.
   - Verify the remote URL is `https://github.com/quantskills/.github`.
   - Run reasonable Markdown, link, and diff checks.
   - Commit with author `abgyjaguo <213890245+abgyjaguo@users.noreply.github.com>`.
   - Push to `main` only after validation passes.
   - If the worktree is dirty, remote does not match, credentials fail, validation fails, or risk is uncertain, do not force-push or overwrite user changes; report the blocker.

9. Produce the Chinese community brief.
   - Use exactly these sections: `今日社区更新`, `需要我注意`, `主页技能仓库一览更新结果`, `验证/推送状态`, `下一步建议`.
   - Include concrete repository names, links, PR or Issue numbers, workflow names, and commit hashes when available.
   - If there are no updates, state the checked scope and exact audit window.

## Script Workflow

1. Run `python scripts/audit_quantskills_repos.py --org quantskills` to scan public organization repositories.
2. Add `--token <token>` or set `GITHUB_TOKEN` / `GH_TOKEN` with `--include-private` when all visible public and private repositories must be included.
3. Add `--plan-governance-actions` to include safe remediation actions in the report without writing to GitHub.
4. Add `--plan-public-restore` to report private prefixed repositories that can be made public after fixes and an open remediation Issue match, and `--apply-public-restore` only after explicit maintainer approval.
5. Add `--report-stale-repos` to report archived, disabled, empty, uninitialized, or stale repositories.
6. Add `--plan-index-updates --local-root D:/quantskill` to compare public `skill-*` and `agent-*` inventory against `.github`, `registry`, and `quantskills/quantskills` local files.
7. Add `--apply-index-updates --local-root D:/quantskill` only after explicit maintainer approval to synchronize the GitHub organization homepage, registry artifacts, and quantskills navigation through local scripts.
   - This also synchronizes quantskills category overrides from canonical registry metadata before generating navigation README files. Business-signal category guesses are suggestions with rationale, not automatic overrides.
8. Add `--plan-update-tests --state-file <path>` to compare the current inventory with the accepted update-check baseline.
9. Add `--run-update-tests --local-root D:/quantskill` with `--test-repo <repo>` when selected test-required repositories should run detected local tests.
10. Add `--write-state --mark-tested <repo>` only after tests pass or a review-only update is accepted.
11. Add `--apply-governance-actions` only for the remote remediation mode described in the guardrails.
12. Review the Markdown or JSON report and ask the user to choose next actions before any GitHub rename, Issue write, visibility change, test execution, state write, registry update, homepage publication, commit, or push. If the user chooses remote index sync, publish `.github`, `registry`, and `quantskills` together or report the blocker that prevents keeping them synchronized.

## Checks

The script treats `.github`, `demo-repository`, `join`, `quantskills`, and `registry` as allowed exceptions. All other repositories should be named with a `skill-` or `agent-` prefix.

For repositories without a prefix, infer the intended type from root declarations and metadata:

- `SKILL.md` or skill/factor/tooling keywords suggest a `skill-` repository.
- `AGENTS.md` or agent/workflow/automation keywords suggest an `agent-` repository.
- Unknown cases are reported for maintainer classification instead of being renamed automatically.

Repository homepage structure checks require a root `README.md`. Skill repositories should also expose `SKILL.md`, `README.en.md`, GPL licensing, and runtime adapter files when publishing under QuantSkills rules. Runtime checks map root `SKILL.md` to Codex and Claude Code, `agents/cursor-rule.mdc` to Cursor, `agents/portable-loader.md` to Hermes, and `agents/openai.yaml` or `agents/portable-loader.md` to OpenClaw.

Index checks are target-specific. The `homepage` target is the GitHub organization profile shown at `https://github.com/quantskills` and is backed by `.github/profile/README.md`. The `registry` target ignores `skill-template`, `agent-template`, and repositories quarantined by the latest local registry scan report. The `quantskills` target should not list private remediation repositories.

Update checks maintain a local JSON state file. The state stores the last observed repository snapshot and the last explicitly accepted snapshot. It does not store credentials. The script plans:

- `test-required` for newly uploaded repositories, never-accepted repositories, runtime/code/dependency/workflow/declaration changes, unknown changed-file scope, or current fail-level audit issues.
- `review-only` for documentation, license, example, or static-asset-only updates; tests can be skipped only after the review finds no issue.
- `skip` for repositories unchanged from the accepted baseline.

Local test execution is explicit. `--run-update-tests` detects repository-local commands such as `scripts/validate.py`, `python -m unittest discover -s tests`, `npm test`, or Python compile smoke checks. Missing local checkouts or missing deterministic commands are reported as blocked, not as passed.

## Guardrails

- Do not automatically rename GitHub repositories.
- Do not push commits, make repositories public, or update organization settings unless the user explicitly asks for that publication action.
- Do not delete, transfer, or destroy repositories through automation.
- Treat generated rename commands and README fixes as proposals until a maintainer approves them.
- Treat every patrol result as a decision checkpoint: report candidate actions first and stop for user confirmation before applying them.
- Before applying governance, show the full set-private candidate list with reasons.
- Treat `--apply-governance-actions` as a guarded remote remediation mode: naming-rule violations and missing-declaration repositories may be made private, while naming errors, missing `README.en.md`, missing `LICENSE`, missing runtime adapters, and declaration-file failures may create or update bilingual community-rule Issues.
- Treat `--apply-index-updates` as the local generation step for a guarded index sync. For remote index sync, also validate, commit, push, and verify `.github`, `registry`, and `quantskills` so the organization homepage, registry, and navigation repository remain synchronized.
- Treat `--run-update-tests` as evidence collection only. Do not mark a repository accepted until the test result is passed or a review-only decision has been manually accepted.
- Treat `--apply-public-restore` as a narrow restoration mode: only private prefixed repositories with a matching open remediation Issue and no fail-level checks may be set back to public; the matched remediation Issue is then commented and closed.
- Do not use `--mark-tested` until the repository tests have passed or the review-only change has been manually accepted.

## Output

Produce:

- A concise Markdown audit report for maintainers.
- Optional JSON output for CI, bots, or dashboards.
- Update-check actions showing which repositories require testing, review-only handling, or no action.
- Local README changes only when `--fix-local-readme` is explicitly set.
- Remote governance actions only when `--apply-governance-actions` is explicitly set.
