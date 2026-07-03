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
5. Use `--run-update-tests --test-repo <repo>` only when the user explicitly wants detected local test or smoke-test commands to run for test-required repositories.
6. Use `--write-state --mark-tested <repo>` only after tests pass or a review-only update is accepted.
7. Use `--plan-governance-actions` to report safe remediation steps without writing to GitHub.
8. Use `--plan-public-restore`, `--report-stale-repos`, and `--plan-index-updates --local-root D:/quantskill` when the request covers public restoration, invalid repository reporting, or homepage / registry / quantskills sync checks.
9. After each patrol, summarize candidate actions and stop for user confirmation before applying any action. Always list repositories that would be set private and their reasons.
10. Use `--apply-index-updates --local-root D:/quantskill` only after the user explicitly asks to synchronize the GitHub organization homepage, registry, and quantskills indexes. For remote index sync, commit, push, and verify `.github`, `registry`, and `quantskills` together.
11. During index sync, canonical registry categories feed quantskills category overrides before navigation generation; keyword-only category guesses are reported for maintainer review instead of being written automatically.
12. Use `--apply-governance-actions` only after the user explicitly asks to apply community-rule remediation. It may set naming-noncompliant and missing-declaration repositories private, create/update Issues for active problems, and close matching remediation Issues when public repositories are now clean.
13. Use `--apply-public-restore` only after the user explicitly asks to restore eligible fixed repositories with a matching open remediation Issue to public; the matched Issue is commented and closed after restoration.
14. Do not rename repositories, push commits, delete repositories, transfer repositories, or delete repositories through this skill.
15. Treat unknown skill/agent classifications as maintainer review items.
16. Generate or copy local root README files only when `--fix-local-readme` is explicitly requested.
```
