# Portable Loader Prompt

Use this prompt in agents that do not natively discover `SKILL.md` folders.

```text
You have access to a local skill named quantskills-repo-auditor at:
<QUANTSKILLS_REPO_AUDITOR_ROOT>

When the user request matches this skill's SKILL.md description:
1. Read <QUANTSKILLS_REPO_AUDITOR_ROOT>/SKILL.md.
2. Run <QUANTSKILLS_REPO_AUDITOR_ROOT>/scripts/audit_quantskills_repos.py for repository inventory checks.
3. Use GitHub tokens with `--include-private` when the task requires all visible repositories.
4. Use `--plan-update-tests --state-file <path>` to identify newly uploaded repositories, changed repositories that need tests, and low-risk updates that can skip tests after review.
5. Use `--write-state --mark-tested <repo>` only after tests pass or a review-only update is accepted.
6. Use `--plan-governance-actions` to report safe remediation steps without writing to GitHub.
7. Use `--plan-public-restore`, `--report-stale-repos`, and `--plan-index-updates --local-root D:/quantskill` when the request covers public restoration, invalid repository reporting, or homepage / registry / quantskills sync checks.
8. Use `--apply-index-updates --local-root D:/quantskill` only after the user explicitly asks to synchronize the GitHub organization homepage, registry, and quantskills indexes.
9. Use `--apply-governance-actions` only after the user explicitly asks to apply community-rule remediation. It may set missing-declaration repositories private, and may create/update Issues for naming errors, missing README.en, missing LICENSE, missing runtime adapters, and missing declarations.
10. Use `--apply-public-restore` only after the user explicitly asks to restore eligible fixed repositories with a matching open remediation Issue to public.
11. Do not rename repositories, push commits, delete repositories, transfer repositories, or delete repositories through this skill.
12. Treat unknown skill/agent classifications as maintainer review items.
13. Generate or copy local root README files only when `--fix-local-readme` is explicitly requested.
```
