#!/usr/bin/env python3
"""Audit QuantSkills organization repositories for naming and README structure.

The script is intentionally conservative:
- remote scans only report problems;
- local README fixes require --fix-local-readme;
- GitHub quarantine writes require --apply-governance-actions;
- GitHub public restoration writes require --apply-public-restore;
- repository renames, deletion, transfer, and destructive operations are never performed.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import ssl
import subprocess
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


DEFAULT_EXEMPT_REPOS = {".github", "demo-repository", "join", "quantskills", "registry"}
COMMUNITY_RULES_URL = "https://github.com/quantskills/join/blob/main/COMMUNITY_RULES.md"
REMEDIATION_TITLE_ZH = "\u6574\u6539\u8981\u6c42\uff1a\u8865\u5145\u4ed3\u5e93\u58f0\u660e\u6587\u4ef6"
LEGACY_REMEDIATION_TITLE_EN = "Remediation required: add repository declaration file"
COMMUNITY_REMEDIATION_TITLE_ZH = "\u6574\u6539\u8981\u6c42\uff1a\u5b8c\u5584 QuantSkills \u793e\u533a\u89c4\u5219\u4e8b\u9879"
COMMUNITY_REMEDIATION_TITLE_EN = "Remediation required: complete QuantSkills community rule items"
INDEX_TARGETS = [
    (
        "homepage",
        ".github/profile/README.md",
        "Update the bilingual skill and agent tables in the organization profile README.",
    ),
    (
        "registry",
        "registry/registry.json",
        "Regenerate or update the public registry artifacts for skill-* and agent-* repositories.",
    ),
    (
        "quantskills",
        "quantskills/README.md",
        "Regenerate quantskills/quantskills navigation content from the current org inventory.",
    ),
]
README_NAMES = {"readme", "readme.md", "readme.markdown", "readme.rst", "readme.txt"}
VALID_PREFIXED_NAME_RE = re.compile(r"^(?:skill|agent)-[a-z0-9]+(?:-[a-z0-9]+)*$")
RUNTIME_FILES = [
    "agents/openai.yaml",
    "agents/cursor-rule.mdc",
    "agents/portable-loader.md",
    ".cursor",
    "HERMES.md",
    "OPENCLAW.md",
]
RUNTIME_REQUIREMENTS = [
    ("codex", ("SKILL.md",)),
    ("claude-code", ("SKILL.md",)),
    ("cursor", ("agents/cursor-rule.mdc", ".cursor")),
    ("hermes", ("agents/portable-loader.md", "HERMES.md")),
    ("openclaw", ("agents/openai.yaml", "agents/portable-loader.md", "OPENCLAW.md")),
]
REGISTRY_INDEX_EXCLUDED_REPOS = {"agent-template", "skill-template"}
# Keys are the registry's own category enum (see registry/scripts/validate_skill.py
# CATEGORIES); values are quantskills navigation ids. Categories intentionally left
# unmapped (e.g. "tooling", "uncategorized") return None and stay out of the public
# navigation. Legacy free-form keys were removed because the registry only ever emits
# enum values, so they never matched.
REGISTRY_CATEGORY_TO_QUANTSKILLS_CATEGORY = {
    "data-api": "01",
    "factor": "02",
    "analyst": "03",
    "monitor": "04",
    "trader-research": "05",
    "replication": "06",
    "research-agent": "09",
    "monitor-agent": "09",
    "risk-agent": "09",
    "workflow-agent": "09",
    "review-agent": "09",
}
QUANTSKILLS_CATEGORY_SUGGESTION_RULES = {
    "01": (
        (5, ("data api", "data warehouse", "warehouse", "dataset", "data source")),
    ),
    "02": (
        (5, ("factor evaluation", "factor research", "rank ic", "information coefficient")),
        (4, ("dragon tiger", "hotmoney", "position concentration", "main divergence")),
        (3, ("alpha", "factor", "ic ir")),
    ),
    "03": (
        (
            6,
            (
                "smart money",
                "lhb",
                "northbound",
                "portfolio health",
                "portfolio checkup",
                "earnings season",
                "industry prosperity",
            ),
        ),
        (5, ("stock screener", "valuation filters", "beat miss", "audit opinion", "dossier")),
        (3, ("market", "stock", "futures", "options", "macro", "valuation")),
    ),
    "04": (
        (6, ("risk alert", "event risk", "early warning", "drawdown alert")),
        (4, ("monitor", "exposure alert", "volatility alert")),
        (1, ("risk", "exposure", "drawdown", "volatility")),
    ),
    "05": (
        (
            6,
            (
                "backtest overfit",
                "deflated sharpe",
                "purged embargoed",
                "portfolio optimizer",
                "portfolio optimize",
                "mean variance",
                "risk parity",
                "risk attribution",
                "barra style",
                "specific risk",
            ),
        ),
        (5, ("backtest", "trading", "strategy", "turnover limits", "weight caps")),
        (2, ("signal", "portfolio")),
    ),
    "06": (
        (5, ("research replication", "paper replication", "report replication")),
        (3, ("research", "replication", "paper", "report")),
    ),
    "07": (
        (5, ("prediction market", "forecast model", "forecast distribution")),
        (2, ("prediction", "forecast", "model")),
    ),
    "08": (
        (5, ("web scraping", "search crawler", "information retrieval")),
        (3, ("search", "scraping", "crawler", "web")),
    ),
}
QUANTSKILLS_CATEGORY_SUGGESTION_MIN_SCORE = 4
QUANTSKILLS_CATEGORY_SUGGESTION_MIN_MARGIN = 2
ISSUE_REMEDIATION_CODES = {
    "repository-prefix",
    "repository-name-format",
    "type-prefix-mismatch",
    "root-readme",
    "root-readme-name",
    "skill-declaration",
    "agent-declaration",
    "english-readme",
    "license",
    "license-metadata",
    "runtime-adapter",
    "sensitive-content",
    "overpromise",
    "risk-disclosure",
}
NAMING_REMEDIATION_CODES = {
    "repository-prefix",
    "repository-name-format",
    "type-prefix-mismatch",
}
SENSITIVE_ASSIGNMENT_RE = re.compile(
    r"(?i)(api[_-]?key|secret|token|password|passwd|access[_-]?key)\s*[:=]\s*['\"]?[A-Za-z0-9_./+=:-]{16,}"
)
OVERPROMISE_RE = re.compile(
    r"(?i)(guaranteed\s+(profit|return|alpha)|risk[- ]?free|officially\s+verified|certified\s+profit|稳赚|保收益|保证收益|无风险收益|官方认证|官方验证)"
)
INVESTMENT_WORKFLOW_RE = re.compile(
    r"(?i)(factor|alpha|strategy|backtest|trading|signal|portfolio|因子|策略|回测|交易|信号|组合)"
)
RISK_DISCLOSURE_RE = re.compile(
    r"(?i)(not\s+investment\s+advice|does\s+not\s+constitute\s+investment\s+advice|不构成投资建议|非投资建议)"
)
NEGATED_CLAIM_RE = re.compile(
    r"(?i)(do\s+not|does\s+not|must\s+not|should\s+not|not\s+imply|not\s+represent|without|不得|不要|不能|不应|不代表|不自动|禁止)"
)
SKILL_KEYWORDS = {
    "skill",
    "factor",
    "strategy",
    "backtest",
    "data",
    "api",
    "report",
    "replication",
    "tool",
    "analysis",
    "analyst",
    "screener",
}
AGENT_KEYWORDS = {
    "agent",
    "workflow",
    "automation",
    "monitor",
    "bot",
    "orchestrator",
    "research-agent",
}
# Chinese-first community: the keyword fallback must also read CJK text. Whole-word
# matching does not work for Chinese (no whitespace boundaries), so these are matched
# as substrings. Kept in sync with the ASCII sets above.
SKILL_KEYWORDS_ZH = {
    "因子",
    "策略",
    "回测",
    "数据",
    "接口",
    "报告",
    "复现",
    "工具",
    "分析",
    "筛选",
    "选股",
    "估值",
}
AGENT_KEYWORDS_ZH = {
    "智能体",
    "代理",
    "工作流",
    "自动化",
    "监控",
    "盯盘",
    "机器人",
    "编排",
}
LOW_RISK_DOC_FILENAMES = {
    "readme",
    "readme.md",
    "readme.en.md",
    "license",
    "notice",
    "notice.md",
    "changelog",
    "changelog.md",
    "contributing.md",
    "code_of_conduct.md",
}
LOW_RISK_DOC_PREFIXES = (
    "docs/",
    "doc/",
    "assets/",
    "images/",
    "examples/",
    "example/",
)
LOW_RISK_DOC_EXTENSIONS = {
    ".md",
    ".rst",
    ".txt",
    ".png",
    ".jpg",
    ".jpeg",
    ".gif",
    ".svg",
    ".webp",
}
TEST_RELEVANT_EXACT_PATHS = {
    "SKILL.md",
    "AGENTS.md",
    "skill.yml",
    "agent.yml",
    "pyproject.toml",
    "requirements.txt",
    "requirements-dev.txt",
    "package.json",
    "package-lock.json",
    "pnpm-lock.yaml",
    "yarn.lock",
    "tsconfig.json",
}
TEST_RELEVANT_PREFIXES = (
    "agents/",
    "scripts/",
    "src/",
    "tests/",
    ".github/workflows/",
    "references/",
)
TEST_RELEVANT_EXTENSIONS = {
    ".py",
    ".js",
    ".jsx",
    ".ts",
    ".tsx",
    ".mjs",
    ".cjs",
    ".ps1",
    ".sh",
    ".bat",
    ".cmd",
    ".toml",
    ".yaml",
    ".yml",
    ".json",
    ".csv",
    ".parquet",
    ".sqlite",
    ".db",
}


def now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def parse_github_datetime(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


def stable_hash(payload: Any) -> str:
    encoded = json.dumps(payload, ensure_ascii=True, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def normalize_repo_slug(name: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")
    slug = re.sub(r"-+", "-", slug)
    for prefix in ("skill-", "agent-"):
        if slug.startswith(prefix):
            slug = slug[len(prefix) :]
    return slug or "unnamed-repo"


def resolve_token(args: argparse.Namespace) -> str | None:
    return args.token or os.environ.get("GITHUB_TOKEN") or os.environ.get("GH_TOKEN")


def github_request(
    method: str,
    url: str,
    token: str | None,
    payload: dict[str, Any] | None = None,
) -> Any:
    headers = {
        "Accept": "application/vnd.github+json",
        "User-Agent": "quantskills-repo-auditor",
        "X-GitHub-Api-Version": "2022-11-28",
    }
    if token:
        headers["Authorization"] = f"Bearer {token}"
    data = None
    if payload is not None:
        data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        headers["Content-Type"] = "application/json; charset=utf-8"
    request = urllib.request.Request(url, data=data, headers=headers, method=method)
    for attempt in range(3):
        try:
            with urllib.request.urlopen(request, timeout=30) as response:
                return json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            if exc.code not in {500, 502, 503, 504} or attempt == 2:
                raise
            time.sleep(1.5 * (attempt + 1))
        except (urllib.error.URLError, TimeoutError, ssl.SSLError):
            if attempt == 2:
                raise
            time.sleep(1.5 * (attempt + 1))
    raise RuntimeError("unreachable GitHub request retry state")


def github_json(url: str, token: str | None) -> Any:
    return github_request("GET", url, token)


def fetch_org_repos(org: str, token: str | None, include_private: bool) -> list[dict[str, Any]]:
    repo_type = "all" if include_private and token else "public"
    repos: list[dict[str, Any]] = []
    page = 1
    while True:
        query = urllib.parse.urlencode(
            {"per_page": 100, "page": page, "type": repo_type, "sort": "full_name"}
        )
        url = f"https://api.github.com/orgs/{urllib.parse.quote(org)}/repos?{query}"
        batch = github_json(url, token)
        if not isinstance(batch, list):
            raise RuntimeError(f"Unexpected GitHub repository response for {org}: {batch!r}")
        repos.extend(batch)
        if len(batch) < 100:
            break
        page += 1
    return repos


def fetch_default_branch_head(
    org: str,
    repo_name: str,
    branch: str | None,
    token: str | None,
) -> str | None:
    if not branch:
        return None
    url = (
        f"https://api.github.com/repos/{urllib.parse.quote(org)}/"
        f"{urllib.parse.quote(repo_name)}/commits/{urllib.parse.quote(branch)}"
    )
    payload = github_json(url, token)
    return payload.get("sha") if isinstance(payload, dict) else None


def fetch_changed_files(
    org: str,
    repo_name: str,
    base_sha: str,
    head_sha: str,
    token: str | None,
) -> tuple[list[str], str | None]:
    url = (
        f"https://api.github.com/repos/{urllib.parse.quote(org)}/"
        f"{urllib.parse.quote(repo_name)}/compare/"
        f"{urllib.parse.quote(base_sha)}...{urllib.parse.quote(head_sha)}"
    )
    try:
        payload = github_json(url, token)
    except urllib.error.HTTPError as exc:
        if exc.code in {403, 404, 409, 422}:
            return [], f"compare unavailable via GitHub API: HTTP {exc.code}"
        raise
    if not isinstance(payload, dict):
        return [], "compare response was not an object"
    files = payload.get("files")
    if not isinstance(files, list):
        return [], "compare response did not include files"
    changed = [
        str(item.get("filename", "")).replace("\\", "/")
        for item in files
        if isinstance(item, dict) and item.get("filename")
    ]
    return sorted(set(changed)), None


def fetch_contents_names(
    org: str,
    repo_name: str,
    token: str | None,
    branch: str | None,
    subpath: str = "",
) -> tuple[set[str], str | None]:
    encoded_path = "/".join(urllib.parse.quote(part) for part in subpath.split("/") if part)
    path_suffix = f"/{encoded_path}" if encoded_path else ""
    query = urllib.parse.urlencode({"ref": branch}) if branch else ""
    url = (
        f"https://api.github.com/repos/{urllib.parse.quote(org)}/"
        f"{urllib.parse.quote(repo_name)}/contents{path_suffix}"
    )
    if query:
        url = f"{url}?{query}"
    try:
        payload = github_json(url, token)
    except urllib.error.HTTPError as exc:
        if exc.code in {403, 404, 409}:
            label = subpath or "root"
            return set(), f"{label} contents unavailable via GitHub API: HTTP {exc.code}"
        raise
    if isinstance(payload, list):
        names = set()
        for item in payload:
            item_name = item.get("name")
            if not item_name:
                continue
            names.add(f"{subpath}/{item_name}" if subpath else item_name)
        return names, None
    label = subpath or "root"
    return set(), f"{label} contents response was not a directory listing"


def fetch_root_names(org: str, repo: dict[str, Any], token: str | None) -> tuple[set[str], str | None]:
    name = repo["name"]
    branch = repo.get("default_branch")
    names, warning = fetch_contents_names(org, name, token, branch)
    if "agents" in names:
        agent_names, agent_warning = fetch_contents_names(org, name, token, branch, "agents")
        names.update(agent_names)
        warning = warning or agent_warning
    return names, warning


def load_repositories_from_json(path: Path) -> list[dict[str, Any]]:
    payload = json.loads(path.read_text(encoding="utf-8-sig"))
    if isinstance(payload, dict):
        payload = payload.get("repositories", payload.get("repos", payload))
    if not isinstance(payload, list):
        raise ValueError("--repositories-json must contain a list or {'repositories': [...]}")
    repos = []
    for item in payload:
        if not isinstance(item, dict) or not item.get("name"):
            raise ValueError("Each repository fixture must be an object with a name")
        repos.append(item)
    return repos


def local_repo_dir(local_root: Path | None, repo_name: str) -> Path | None:
    if not local_root:
        return None
    candidate = local_root / repo_name
    return candidate if candidate.is_dir() else None


def local_root_names(repo_dir: Path | None) -> set[str] | None:
    if not repo_dir:
        return None
    names = {entry.name for entry in repo_dir.iterdir()}
    agents_dir = repo_dir / "agents"
    if agents_dir.is_dir():
        names.update(f"agents/{entry.name}" for entry in agents_dir.iterdir() if entry.is_file())
    return names


def has_path(root_names: set[str], path: str) -> bool:
    parts = path.replace("\\", "/").split("/")
    if len(parts) == 1:
        return parts[0] in root_names
    return False


def nested_file_exists(repo_dir: Path | None, relative_path: str) -> bool:
    return bool(repo_dir and (repo_dir / relative_path).is_file())


def repository_path_exists(repo_dir: Path | None, root_names: set[str], relative_path: str) -> bool:
    return relative_path in root_names or nested_file_exists(repo_dir, relative_path)


def read_local_text(repo_dir: Path | None, relative_path: str) -> str:
    if not repo_dir:
        return ""
    path = repo_dir / relative_path
    if not path.is_file():
        return ""
    try:
        return path.read_text(encoding="utf-8-sig", errors="replace")
    except OSError:
        return ""


def root_readme_status(root_names: set[str]) -> tuple[str, str | None]:
    if "README.md" in root_names:
        return "ok", None
    for name in root_names:
        if name.lower() in README_NAMES:
            return "nonstandard", name
    return "missing", None


def find_nested_readme(repo_dir: Path) -> Path | None:
    candidates: list[Path] = []
    for child in repo_dir.rglob("*"):
        if ".git" in child.parts or not child.is_file():
            continue
        try:
            rel = child.relative_to(repo_dir)
        except ValueError:
            continue
        if len(rel.parts) > 3:
            continue
        if child.name.lower() in README_NAMES and rel.parts[0].lower() != "readme.md":
            candidates.append(child)
    candidates.sort(key=lambda p: (len(p.relative_to(repo_dir).parts), str(p).lower()))
    return candidates[0] if candidates else None


def infer_repo_type(repo: dict[str, Any], root_names: set[str]) -> str | None:
    name = str(repo.get("name", "")).lower()
    if name.startswith("skill-"):
        return "skill"
    if name.startswith("agent-"):
        return "agent"
    has_skill_decl = "SKILL.md" in root_names
    has_agent_decl = "AGENTS.md" in root_names
    if has_skill_decl and not has_agent_decl:
        return "skill"
    if has_agent_decl and not has_skill_decl:
        return "agent"
    if has_skill_decl and has_agent_decl:
        # Both declaration files present: the type is ambiguous. Default to skill;
        # audit_repo raises a type-ambiguous warning so a maintainer can resolve it.
        return "skill"

    corpus = " ".join(
        [
            str(repo.get("name", "")),
            str(repo.get("description", "") or ""),
            " ".join(str(topic) for topic in repo.get("topics", []) or []),
        ]
    ).lower()
    # ASCII keywords match on word boundaries; CJK keywords match as substrings. The
    # corpus must not be stripped of non-ASCII characters or Chinese repos lose the
    # fallback entirely.
    ascii_words = set(re.findall(r"[a-z0-9]+(?:-[a-z0-9]+)*", corpus))
    if (ascii_words & AGENT_KEYWORDS) or any(kw in corpus for kw in AGENT_KEYWORDS_ZH):
        return "agent"
    if (ascii_words & SKILL_KEYWORDS) or any(kw in corpus for kw in SKILL_KEYWORDS_ZH):
        return "skill"
    return None


def make_issue(
    code: str,
    severity: str,
    message: str,
    action: str | None = None,
) -> dict[str, str]:
    issue = {"code": code, "severity": severity, "message": message}
    if action:
        issue["action"] = action
    return issue


def runtime_adapter_issues(root_names: set[str], repo_dir: Path | None) -> list[dict[str, str]]:
    issues = []
    for runtime, candidates in RUNTIME_REQUIREMENTS:
        if any(repository_path_exists(repo_dir, root_names, candidate) for candidate in candidates):
            continue
        issues.append(
            make_issue(
                "runtime-adapter",
                "warn",
                f"Skill repository is missing {runtime} runtime adapter entrypoint.",
                f"Add one of: {', '.join(candidates)}.",
            )
        )
    return issues


def has_unnegated_overpromise(text: str) -> bool:
    for match in OVERPROMISE_RE.finditer(text):
        context = text[max(0, match.start() - 80) : match.start()]
        if not NEGATED_CLAIM_RE.search(context):
            return True
    return False


def content_policy_issues(
    repo_dir: Path | None,
    root_names: set[str],
    inferred_type: str | None,
    repo: dict[str, Any] | None = None,
) -> list[dict[str, str]]:
    if not repo_dir:
        return []
    texts = {
        relative: read_local_text(repo_dir, relative)
        for relative in ("README.md", "README.en.md", "SKILL.md", "AGENTS.md", "skill.yml")
        if repository_path_exists(repo_dir, root_names, relative)
    }
    combined = "\n".join(texts.values())
    issues: list[dict[str, str]] = []
    if inferred_type == "skill" and "SKILL.md" in texts:
        metadata_text = "\n".join([texts.get("SKILL.md", ""), texts.get("skill.yml", "")])
        if "GPL-3.0-only" not in metadata_text:
            issues.append(
                make_issue(
                    "license-metadata",
                    "fail",
                    "Skill metadata does not declare GPL-3.0-only.",
                    "Add license: GPL-3.0-only to SKILL.md metadata or skill.yml.",
                )
            )
    if combined and SENSITIVE_ASSIGNMENT_RE.search(combined):
        issues.append(
            make_issue(
                "sensitive-content",
                "fail",
                "Possible API key, token, password, or secret assignment appears in public-facing text.",
                "Remove secrets and replace examples with placeholders.",
            )
        )
    if combined and has_unnegated_overpromise(combined):
        issues.append(
            make_issue(
                "overpromise",
                "fail",
                "Project text appears to promise returns, imply official verification, or overstate safety.",
                "Rewrite claims to be factual, non-promotional, and maintainer-reviewed.",
            )
        )
    identity_text = " ".join(
        [
            str((repo or {}).get("name", "")),
            str((repo or {}).get("description", "") or ""),
            " ".join(str(topic) for topic in (repo or {}).get("topics", []) or []),
        ]
    )
    if inferred_type == "skill" and combined and INVESTMENT_WORKFLOW_RE.search(identity_text) and not RISK_DISCLOSURE_RE.search(combined):
        issues.append(
            make_issue(
                "risk-disclosure",
                "warn",
                "Quant investment workflow text is missing a clear non-investment-advice risk disclosure.",
                "State data sources, assumptions, limitations, risk boundaries, and that outputs are not investment advice.",
            )
        )
    return issues


def generated_readme(repo: dict[str, Any], inferred_type: str | None) -> str:
    name = repo["name"]
    title = name
    description = repo.get("description") or "TODO: describe this QuantSkills community repository."
    kind = inferred_type or "community project"
    return (
        f"# {title}\n\n"
        "**简体中文** | English below\n\n"
        f"> {description}\n\n"
        "## 项目定位\n\n"
        f"这是一个 QuantSkills {kind} 仓库。请维护者补充用途、使用方法、维护者、数据来源、"
        "已知限制和风险边界。\n\n"
        "## 使用方式\n\n"
        "TODO: add usage instructions.\n\n"
        "## 维护者\n\n"
        "TODO: add maintainer information.\n\n"
        "## 风险声明\n\n"
        "本仓库内容仅用于研究和教育示例，不构成投资建议，不承诺收益。\n\n"
        "---\n\n"
        "## English\n\n"
        f"{description}\n\n"
        f"This is a QuantSkills {kind} repository. Maintainers should add usage instructions, "
        "data sources, limitations, risk boundaries, and maintainer information.\n"
    )


def fix_local_readme(repo_dir: Path, repo: dict[str, Any], inferred_type: str | None) -> str:
    target = repo_dir / "README.md"
    if target.exists():
        return "root README.md already exists"
    nested = find_nested_readme(repo_dir)
    if nested:
        shutil.copyfile(nested, target)
        return f"copied {nested.relative_to(repo_dir)} to README.md"
    target.write_text(generated_readme(repo, inferred_type), encoding="utf-8", newline="\n")
    return "generated README.md template"


def audit_repo(
    org: str,
    repo: dict[str, Any],
    root_names: set[str],
    repo_dir: Path | None,
    exempt_repos: set[str],
    fix_readme: bool,
    root_warning: str | None,
) -> dict[str, Any]:
    name = repo["name"]
    issues: list[dict[str, str]] = []
    fixed: list[str] = []
    exempt = name in exempt_repos
    inferred_type = infer_repo_type(repo, root_names)
    root_unavailable = bool(root_warning and root_warning.startswith("root "))
    agents_unavailable = bool(root_warning and root_warning.startswith("agents "))

    if root_warning:
        issues.append(make_issue("root-contents", "warn", root_warning))

    if not exempt and not (name.startswith("skill-") or name.startswith("agent-")):
        if inferred_type:
            suggested = f"{inferred_type}-{normalize_repo_slug(name)}"
            issues.append(
                make_issue(
                    "repository-prefix",
                    "fail",
                    "Repository is not prefixed with skill- or agent-.",
                    f"Maintainer review: rename {name} to {suggested}.",
                )
            )
        else:
            issues.append(
                make_issue(
                    "repository-prefix",
                    "fail",
                    "Repository is not prefixed with skill- or agent-, and the intended type could not be inferred.",
                    "Maintainer classification required before renaming.",
                )
            )
    elif not exempt and not VALID_PREFIXED_NAME_RE.match(name):
        prefix = "skill" if name.startswith("skill-") else "agent"
        suggested = f"{prefix}-{normalize_repo_slug(name)}"
        issues.append(
            make_issue(
                "repository-name-format",
                "fail",
                "Repository has the required prefix but is not lowercase hyphen-case.",
                f"Maintainer review: rename {name} to {suggested}.",
            )
        )

    if not exempt and name.startswith("skill-") and inferred_type == "agent":
        issues.append(
            make_issue(
                "type-prefix-mismatch",
                "warn",
                "Repository name uses skill- but files or metadata look agent-like.",
                "Check whether this should be an agent- repository.",
            )
        )
    if not exempt and name.startswith("agent-") and inferred_type == "skill":
        issues.append(
            make_issue(
                "type-prefix-mismatch",
                "warn",
                "Repository name uses agent- but files or metadata look skill-like.",
                "Check whether this should be a skill- repository.",
            )
        )

    if (
        not exempt
        and not root_unavailable
        and not name.startswith(("skill-", "agent-"))
        and "SKILL.md" in root_names
        and "AGENTS.md" in root_names
    ):
        issues.append(
            make_issue(
                "type-ambiguous",
                "warn",
                "Repository has both root SKILL.md and AGENTS.md, so the intended type is ambiguous.",
                "Keep only the declaration that matches the repository type: SKILL.md for skills, AGENTS.md for agents.",
            )
        )

    if not root_unavailable:
        readme_state, readme_name = root_readme_status(root_names)
        if readme_state == "missing":
            action = "Add a root README.md so GitHub renders a repository homepage."
            if repo_dir and fix_readme:
                fixed.append(fix_local_readme(repo_dir, repo, inferred_type))
                root_names.add("README.md")
            else:
                issues.append(make_issue("root-readme", "fail", "Root README.md is missing.", action))
        elif readme_state == "nonstandard":
            issues.append(
                make_issue(
                    "root-readme-name",
                    "warn",
                    f"Root README exists as {readme_name}, but the QuantSkills standard is README.md.",
                    f"Rename {readme_name} to README.md.",
                )
            )

    if inferred_type == "skill" and not root_unavailable:
        if "SKILL.md" not in root_names:
            issues.append(
                make_issue(
                    "skill-declaration",
                    "fail",
                    "Skill repository is missing root SKILL.md.",
                    "Add SKILL.md with description, usage, maintainer, supported scenarios, limitations, and metadata.",
                )
            )
        if "README.en.md" not in root_names:
            issues.append(
                make_issue(
                    "english-readme",
                    "fail",
                    "Skill repository is missing README.en.md.",
                    "Add English README while keeping README.md Chinese-first.",
                )
            )
        if "LICENSE" not in root_names:
            issues.append(
                make_issue(
                    "license",
                    "fail",
                    "Skill repository is missing LICENSE.",
                    "Add GPLv3 LICENSE and declare GPL-3.0-only in metadata.",
                )
            )
        if not agents_unavailable:
            issues.extend(runtime_adapter_issues(root_names, repo_dir))

    if inferred_type == "agent" and not root_unavailable and "AGENTS.md" not in root_names:
        issues.append(
            make_issue(
                "agent-declaration",
                "fail",
                "Agent repository is missing root AGENTS.md.",
                "Add AGENTS.md with description, usage, maintainer, supported scenarios, limitations, and metadata.",
            )
        )

    issues.extend(content_policy_issues(repo_dir, root_names, inferred_type, repo))

    return {
        "name": name,
        "url": repo.get("html_url") or f"https://github.com/{org}/{name}",
        "description": repo.get("description") or "",
        "visibility": repo.get("visibility") or ("private" if repo.get("private") else "public"),
        "private": bool(repo.get("private")),
        "archived": bool(repo.get("archived")),
        "disabled": bool(repo.get("disabled")),
        "default_branch": repo.get("default_branch"),
        "created_at": repo.get("created_at"),
        "updated_at": repo.get("updated_at"),
        "pushed_at": repo.get("pushed_at"),
        "head_sha": repo.get("head_sha"),
        "exempt": exempt,
        "inferred_type": inferred_type or "unknown",
        "has_prefix": name.startswith(("skill-", "agent-")),
        "has_root_readme": "README.md" in root_names,
        "root_files": sorted(root_names),
        "changed_files": sorted(repo.get("changed_files", []) or []),
        "fixed": fixed,
        "issues": issues,
    }


def audit(args: argparse.Namespace) -> dict[str, Any]:
    token = resolve_token(args)
    if args.repositories_json:
        repos = load_repositories_from_json(Path(args.repositories_json))
    else:
        repos = fetch_org_repos(args.org, token, args.include_private)

    local_root = Path(args.local_root).resolve() if args.local_root else None
    exempt_repos = set(DEFAULT_EXEMPT_REPOS)
    exempt_repos.update(args.allow_special or [])

    results = []
    for repo in sorted(repos, key=lambda item: item["name"].lower()):
        repo_dir = local_repo_dir(local_root, repo["name"])
        root_names = local_root_names(repo_dir)
        root_warning = None
        if root_names is None:
            if args.repositories_json:
                root_names = set(repo.get("root_names", []) or [])
            else:
                root_names, root_warning = fetch_root_names(args.org, repo, token)
        results.append(
            audit_repo(
                args.org,
                repo,
                root_names,
                repo_dir,
                exempt_repos,
                args.fix_local_readme,
                root_warning,
            )
        )

    fail_count = sum(any(issue["severity"] == "fail" for issue in item["issues"]) for item in results)
    warn_count = sum(any(issue["severity"] == "warn" for issue in item["issues"]) for item in results)
    issue_count = sum(len(item["issues"]) for item in results)
    fixed_count = sum(len(item["fixed"]) for item in results)

    return {
        "generated_at": now_iso(),
        "org": args.org,
        "source": "json-fixture" if args.repositories_json else "github-api",
        "summary": {
            "repositories": len(results),
            "repositories_with_failures": fail_count,
            "repositories_with_warnings": warn_count,
            "issues": issue_count,
            "local_readmes_fixed": fixed_count,
            "governance_actions": 0,
            "public_restore_actions": 0,
            "stale_repositories": 0,
            "index_update_actions": 0,
            "index_apply_actions": 0,
            "update_check_actions": 0,
            "update_tests_required": 0,
            "update_review_only": 0,
            "update_skipped": 0,
            "test_run_results": 0,
            "test_run_passed": 0,
            "test_run_failed": 0,
            "test_run_blocked": 0,
        },
        "repositories": results,
        "governance_actions": [],
        "public_restore_actions": [],
        "stale_repositories": [],
        "index_update_actions": [],
        "index_apply_actions": [],
        "update_check_actions": [],
        "test_run_results": [],
    }


def declaration_remediation_target(item: dict[str, Any]) -> tuple[str, str] | None:
    issue_codes = {issue["code"] for issue in item.get("issues", [])}
    name = item["name"]
    if name.startswith("skill-") and "skill-declaration" in issue_codes:
        return "skill", "SKILL.md"
    if name.startswith("agent-") and "agent-declaration" in issue_codes:
        return "agent", "AGENTS.md"
    return None


def declaration_issue_body(repo_name: str, kind: str, declaration: str, rules_url: str) -> str:
    # Keep source ASCII while producing a bilingual GitHub issue body.
    return (
        "## \u6574\u6539\u8981\u6c42\n\n"
        f"\u8be5\u4ed3\u5e93 `{repo_name}` \u5f53\u524d\u7f3a\u5c11\u6839\u76ee\u5f55 "
        f"`{declaration}`\uff0c\u6682\u4e0d\u7b26\u5408 QuantSkills "
        "\u793e\u533a\u4ed3\u5e93\u7ed3\u6784\u8981\u6c42\u3002\u4ed3\u5e93\u5e94\u4fdd\u6301\u4e3a "
        "private\uff0c\u5f85\u8865\u9f50\u540e\u518d\u7531\u7ef4\u62a4\u8005\u590d\u6838"
        "\u662f\u5426\u6062\u590d\u516c\u5f00\u6216\u6536\u5f55\u3002\n\n"
        f"\u8bf7\u63d0\u4ea4\u6210\u5458\u5728\u4ed3\u5e93\u6839\u76ee\u5f55\u8865\u5145 `{declaration}`"
        "\uff0c\u5e76\u786e\u4fdd\u8bf4\u660e\uff1a\n\n"
        "- \u9879\u76ee\u505a\u4ec0\u4e48\uff1b\n"
        "- \u5982\u4f55\u4f7f\u7528\uff1b\n"
        "- \u7531\u8c01\u7ef4\u62a4\uff1b\n"
        "- \u652f\u6301\u54ea\u4e9b\u573a\u666f\uff1b\n"
        "- \u91cd\u8981\u9650\u5236\u662f\u4ec0\u4e48\uff1b\n"
        "- \u5fc5\u8981\u5143\u6570\u636e\uff0c\u4f8b\u5982 `organization`\u3001"
        "`organization_url`\u3001`repository`\u3001`repository_url`\u3001`project_type`\uff1b\n"
        "- \u5982\u679c\u6d89\u53ca\u56e0\u5b50\u3001\u7b56\u7565\u3001\u56de\u6d4b\u3001"
        "\u4ea4\u6613\u4fe1\u53f7\u6216\u6295\u8d44\u5de5\u4f5c\u6d41\uff0c\u8bf7\u5199\u660e"
        "\u6570\u636e\u6765\u6e90\u3001\u5047\u8bbe\u3001\u53c2\u6570\u3001\u5df2\u77e5"
        "\u9650\u5236\u3001\u98ce\u9669\u8fb9\u754c\uff0c\u5e76\u660e\u786e\u4e0d\u6784\u6210"
        "\u6295\u8d44\u5efa\u8bae\uff1b\n"
        "- \u4e0d\u8981\u5305\u542b API key\u3001\u79c1\u6709 token\u3001\u8d26\u53f7\u51ed\u636e"
        "\u3001\u79c1\u6709\u6570\u636e\u96c6\u3001\u6cc4\u9732\u6570\u636e\u6216\u673a\u5bc6"
        "\u6587\u6863\u3002\n\n"
        f"\u5f53\u524d\u4ed3\u5e93\u540d\u9884\u671f\u7c7b\u578b\uff1a`{kind}`  \n"
        f"\u9700\u8865\u5145\u7684\u58f0\u660e\u6587\u4ef6\uff1a`{declaration}`\n\n"
        f"\u793e\u533a\u89c4\u5219\uff1a{rules_url}\n\n"
        "\u8865\u5145\u5b8c\u6210\u540e\uff0c\u8bf7\u5728\u672c Issue \u4e0b\u56de\u590d\u3002"
        "\u7ef4\u62a4\u8005\u4f1a\u91cd\u65b0\u8fd0\u884c\u4ed3\u5e93\u5ba1\u8ba1\uff0c"
        "\u518d\u51b3\u5b9a\u662f\u5426\u6062\u590d\u516c\u5f00\u6216\u52a0\u5165\u6536\u5f55\u3002"
        "\n\n---\n\n"
        "## Remediation Required\n\n"
        f"This repository `{repo_name}` is currently missing the root `{declaration}` file, "
        "so it does not yet satisfy the QuantSkills community repository structure rules. "
        "The repository should remain private until maintainers confirm that the declaration "
        "file and required documentation have been added.\n\n"
        f"Please add `{declaration}` at the repository root and make sure it explains:\n\n"
        "- what the project does;\n"
        "- how to use it;\n"
        "- who maintains it;\n"
        "- supported scenarios;\n"
        "- important limitations;\n"
        "- required metadata such as `organization`, `organization_url`, `repository`, "
        "`repository_url`, and `project_type`;\n"
        "- for factors, strategies, backtests, trading signals, or investment workflows: "
        "data sources, assumptions, parameters, known limitations, risk boundaries, and "
        "a clear statement that the project is not investment advice;\n"
        "- no API keys, private tokens, account credentials, private datasets, leaked data, "
        "or confidential documents.\n\n"
        f"Expected repository type from its name: `{kind}`  \n"
        f"Required declaration file: `{declaration}`\n\n"
        f"Community rules: {rules_url}\n\n"
        "After the file is added, reply in this Issue. Maintainers will rerun the audit "
        "and decide whether to restore public visibility or include the project in indexes."
    )


def community_rule_issues(item: dict[str, Any]) -> list[dict[str, Any]]:
    return [
        issue
        for issue in item.get("issues", [])
        if issue.get("code") in ISSUE_REMEDIATION_CODES
    ]


def remediation_visibility_action(item: dict[str, Any]) -> str:
    issue_codes = {issue["code"] for issue in item.get("issues", [])}
    if declaration_remediation_target(item) or issue_codes.intersection(NAMING_REMEDIATION_CODES):
        return "set-private"
    return "no-visibility-change"


def community_rule_issue_body(
    repo_name: str,
    issues: list[dict[str, Any]],
    rules_url: str,
) -> str:
    zh_items = []
    en_items = []
    for issue in issues:
        code = issue.get("code", "unknown")
        severity = issue.get("severity", "warn")
        message = issue.get("message", "")
        action = issue.get("action", "Maintainer review required.")
        zh_items.append(f"- `{severity}:{code}`：{message}  \n  建议动作：{action}")
        en_items.append(f"- `{severity}:{code}`: {message}  \n  Suggested action: {action}")
    zh_block = "\n".join(zh_items) or "- 暂无可列出的规则问题。"
    en_block = "\n".join(en_items) or "- No rule issues to list."
    return (
        "## 整改要求\n\n"
        f"仓库 `{repo_name}` 当前存在 QuantSkills 社区规则相关问题。请维护者按下列事项补齐后，"
        "再申请公开、收录、恢复 public 或进入 registry / quantskills / 组织首页索引。\n\n"
        f"{zh_block}\n\n"
        "重点规则包括：仓库命名应使用小写 `skill-` / `agent-` 前缀；Skill 仓库需要 "
        "`SKILL.md`、`README.md`、`README.en.md`、GPLv3 `LICENSE`、`GPL-3.0-only` "
        "元数据，以及面向 Codex / Claude Code / Cursor / Hermes / OpenClaw 的运行时入口；"
        "项目说明不得包含敏感信息、收益承诺、投资建议或未经维护者确认的官方背书表述。\n\n"
        f"社区规则：{rules_url}\n\n"
        "修复完成后，请在本 Issue 下回复。维护者会重新运行仓库审计，再决定是否恢复 public、"
        "进入索引或关闭本 Issue。\n\n"
        "---\n\n"
        "## Remediation Required\n\n"
        f"Repository `{repo_name}` currently has QuantSkills community-rule issues. Please resolve "
        "the items below before requesting public visibility, listing, restoration, or inclusion in "
        "registry / quantskills / organization-homepage indexes.\n\n"
        f"{en_block}\n\n"
        "Core rules include lowercase `skill-` / `agent-` repository names; Skill repositories should "
        "include `SKILL.md`, `README.md`, `README.en.md`, a GPLv3 `LICENSE`, `GPL-3.0-only` metadata, "
        "and runtime entrypoints for Codex, Claude Code, Cursor, Hermes, and OpenClaw. Project text "
        "must not include sensitive information, promised returns, investment advice, or unapproved "
        "official endorsement claims.\n\n"
        f"Community rules: {rules_url}\n\n"
        "After fixing the repository, reply in this Issue. Maintainers will rerun the audit and decide "
        "whether to restore public visibility, include the project in indexes, or close this Issue."
    )


def matching_remediation_issue(
    issues: list[dict[str, Any]],
    titles: set[str] | None = None,
) -> dict[str, Any] | None:
    titles = titles or {
        COMMUNITY_REMEDIATION_TITLE_ZH,
        COMMUNITY_REMEDIATION_TITLE_EN,
        REMEDIATION_TITLE_ZH,
        LEGACY_REMEDIATION_TITLE_EN,
    }
    for issue in issues:
        if issue.get("pull_request"):
            continue
        if issue.get("title") in titles:
            return issue
    return None


def governance_action_records(report: dict[str, Any], rules_url: str) -> list[dict[str, Any]]:
    actions: list[dict[str, Any]] = []
    for item in report["repositories"]:
        issues = community_rule_issues(item)
        if not issues:
            continue
        target = declaration_remediation_target(item)
        kind, declaration = target if target else (item.get("inferred_type", "unknown"), None)
        actions.append(
            {
                "repo": item["name"],
                "kind": kind,
                "declaration": declaration,
                "issue_codes": sorted({issue.get("code", "unknown") for issue in issues}),
                "reasons": [
                    {
                        "code": issue.get("code", "unknown"),
                        "severity": issue.get("severity", "warn"),
                        "message": issue.get("message", ""),
                        "action": issue.get("action", "Maintainer review required."),
                    }
                    for issue in issues
                ],
                "issue_count": len(issues),
                "status": "planned",
                "visibility_action": remediation_visibility_action(item),
                "issue_action": "create-or-update-community-rule-issue",
                "rules_url": rules_url,
                "issue_url": None,
            }
        )
    return actions


def apply_governance_actions(
    report: dict[str, Any],
    org: str,
    token: str,
    rules_url: str,
) -> list[dict[str, Any]]:
    actions = governance_action_records(report, rules_url)
    for action in actions:
        repo_name = action["repo"]
        repo_api = f"https://api.github.com/repos/{urllib.parse.quote(org)}/{urllib.parse.quote(repo_name)}"
        repo_info = github_request("GET", repo_api, token)
        if action.get("visibility_action") == "set-private":
            if repo_info.get("private"):
                action["visibility_action"] = "already-private"
            else:
                github_request("PATCH", repo_api, token, {"private": True})
                action["visibility_action"] = "changed-to-private"
        else:
            action["visibility_action"] = "no-visibility-change"

        issues_url = f"{repo_api}/issues?state=open&per_page=100"
        issues = github_request("GET", issues_url, token)
        existing = matching_remediation_issue(issues if isinstance(issues, list) else [])
        item = next((entry for entry in report["repositories"] if entry["name"] == repo_name), None)
        rule_issues = community_rule_issues(item or {})
        body = community_rule_issue_body(repo_name, rule_issues, rules_url)
        payload = {"title": COMMUNITY_REMEDIATION_TITLE_ZH, "body": body}
        if existing:
            issue = github_request("PATCH", f"{repo_api}/issues/{existing['number']}", token, payload)
            action["issue_action"] = f"updated #{issue['number']}"
        else:
            issue = github_request("POST", f"{repo_api}/issues", token, payload)
            action["issue_action"] = f"created #{issue['number']}"
        action["issue_url"] = issue.get("html_url")
        action["status"] = "applied"
    actions.extend(close_resolved_remediation_issue_actions(report, org, token))
    return actions


def attach_governance_actions(report: dict[str, Any], actions: list[dict[str, Any]]) -> None:
    report["governance_actions"] = actions
    report["summary"]["governance_actions"] = len(actions)


def failure_codes(item: dict[str, Any]) -> set[str]:
    return {
        issue["code"]
        for issue in item.get("issues", [])
        if issue.get("severity") == "fail"
    }


def issue_codes(item: dict[str, Any]) -> set[str]:
    return {issue["code"] for issue in item.get("issues", [])}


def public_restore_target(item: dict[str, Any]) -> tuple[str, str] | None:
    name = item["name"]
    if not item.get("private") and item.get("visibility") != "private":
        return None
    if item.get("archived") or item.get("disabled"):
        return None
    if failure_codes(item):
        return None
    if community_rule_issues(item):
        return None
    if "root-contents" in issue_codes(item):
        return None
    if name.startswith("skill-") and item.get("inferred_type") == "skill":
        return "skill", "SKILL.md"
    if name.startswith("agent-") and item.get("inferred_type") == "agent":
        return "agent", "AGENTS.md"
    return None


def public_restore_action_records(
    report: dict[str, Any],
    org: str | None = None,
    token: str | None = None,
) -> list[dict[str, Any]]:
    actions: list[dict[str, Any]] = []
    if not org or not token:
        return actions
    for item in report["repositories"]:
        target = public_restore_target(item)
        if not target:
            continue
        kind, declaration = target
        issue_url = None
        issue_action = "comment-and-close-remediation-issue-if-present"
        repo_api = f"https://api.github.com/repos/{urllib.parse.quote(org)}/{urllib.parse.quote(item['name'])}"
        issues_url = f"{repo_api}/issues?state=open&per_page=100"
        issues = github_request("GET", issues_url, token)
        existing = matching_remediation_issue(issues if isinstance(issues, list) else [])
        if not existing:
            continue
        issue_url = existing.get("html_url")
        issue_action = f"comment-and-close #{existing['number']}"
        actions.append(
            {
                "repo": item["name"],
                "kind": kind,
                "declaration": declaration,
                "status": "planned",
                "visibility_action": "set-public",
                "issue_action": issue_action,
                "issue_number": existing["number"],
                "issue_url": issue_url,
            }
        )
    return actions


def declaration_resolved_comment(repo_name: str, declaration: str) -> str:
    return (
        "## \u590d\u6838\u7ed3\u679c\n\n"
        f"\u5ba1\u8ba1\u5df2\u68c0\u6d4b\u5230 `{repo_name}` \u6839\u76ee\u5f55\u5df2\u5177\u5907 "
        f"`{declaration}`\uff0c\u672c\u8f6e\u58f0\u660e\u6587\u4ef6\u7f3a\u5931\u95ee\u9898"
        "\u5df2\u89e3\u51b3\u3002\u7ef4\u62a4\u8005\u53ef\u4ee5\u6062\u590d\u516c\u5f00"
        "\u53ef\u89c1\u6027\uff0c\u5e76\u7ee7\u7eed\u68c0\u67e5 README\u3001LICENSE\u3001"
        "\u8fd0\u884c\u65f6\u9002\u914d\u5165\u53e3\u548c\u6536\u5f55\u4fe1\u606f\u3002\n\n"
        "---\n\n"
        "## Review Result\n\n"
        f"The audit now detects `{declaration}` at the root of `{repo_name}`. "
        "This declaration-file issue is resolved. Maintainers may restore public "
        "visibility and continue reviewing README, LICENSE, runtime adapters, and index metadata."
    )


def remediation_resolved_comment(repo_name: str) -> str:
    return (
        "## \u590d\u6838\u7ed3\u679c\n\n"
        f"\u672c\u8f6e\u5ba1\u8ba1\u672a\u518d\u68c0\u6d4b\u5230 `{repo_name}` \u7684 "
        "QuantSkills \u793e\u533a\u89c4\u5219\u6574\u6539\u9879\uff0c\u672c Issue \u5df2\u6309"
        "\u81ea\u52a8\u590d\u6838\u7ed3\u679c\u5173\u95ed\u3002\u5982\u540e\u7eed\u518d\u51fa\u73b0"
        "\u547d\u540d\u3001README\u3001LICENSE\u3001\u5143\u6570\u636e\u3001\u8fd0\u884c\u65f6"
        "\u9002\u914d\u6216\u98ce\u9669\u62ab\u9732\u95ee\u9898\uff0c\u7ef4\u62a4\u8005\u4f1a"
        "\u91cd\u65b0\u6253\u5f00\u6216\u521b\u5efa\u6574\u6539 Issue\u3002\n\n"
        "---\n\n"
        "## Review Result\n\n"
        f"The current audit no longer detects QuantSkills community-rule remediation items "
        f"for `{repo_name}`, so this Issue is closed by the automated review. If naming, "
        "README, license, metadata, runtime adapter, or risk-disclosure issues reappear, "
        "maintainers may reopen this Issue or create a new remediation Issue."
    )


def close_resolved_remediation_issue_actions(
    report: dict[str, Any],
    org: str,
    token: str,
) -> list[dict[str, Any]]:
    actions: list[dict[str, Any]] = []
    for item in report["repositories"]:
        if community_rule_issues(item):
            continue
        if item.get("private") or item.get("visibility") == "private":
            continue
        repo_name = item["name"]
        repo_api = f"https://api.github.com/repos/{urllib.parse.quote(org)}/{urllib.parse.quote(repo_name)}"
        issues_url = f"{repo_api}/issues?state=open&per_page=100"
        issues = github_request("GET", issues_url, token)
        existing = matching_remediation_issue(issues if isinstance(issues, list) else [])
        if not existing:
            continue
        github_request(
            "POST",
            f"{repo_api}/issues/{existing['number']}/comments",
            token,
            {"body": remediation_resolved_comment(repo_name)},
        )
        issue = github_request(
            "PATCH",
            f"{repo_api}/issues/{existing['number']}",
            token,
            {"state": "closed"},
        )
        actions.append(
            {
                "repo": repo_name,
                "kind": item.get("inferred_type", "unknown"),
                "declaration": None,
                "issue_codes": [],
                "reasons": [],
                "issue_count": 0,
                "status": "applied",
                "visibility_action": "no-visibility-change",
                "issue_action": f"commented-and-closed #{issue['number']}",
                "rules_url": COMMUNITY_RULES_URL,
                "issue_url": issue.get("html_url"),
            }
        )
    return actions


def apply_public_restore_actions(
    report: dict[str, Any],
    org: str,
    token: str,
) -> list[dict[str, Any]]:
    actions = public_restore_action_records(report, org, token)
    for action in actions:
        repo_name = action["repo"]
        repo_api = f"https://api.github.com/repos/{urllib.parse.quote(org)}/{urllib.parse.quote(repo_name)}"
        repo_info = github_request("GET", repo_api, token)
        if repo_info.get("private"):
            github_request("PATCH", repo_api, token, {"private": False})
            action["visibility_action"] = "changed-to-public"
        else:
            action["visibility_action"] = "already-public"

        issue_number = action.get("issue_number")
        if issue_number:
            github_request(
                "POST",
                f"{repo_api}/issues/{issue_number}/comments",
                token,
                {"body": remediation_resolved_comment(repo_name)},
            )
            issue = github_request(
                "PATCH",
                f"{repo_api}/issues/{issue_number}",
                token,
                {"state": "closed"},
            )
            action["issue_action"] = f"commented-and-closed #{issue['number']}"
            action["issue_url"] = issue.get("html_url")
        else:
            action["issue_action"] = "no-open-remediation-issue-found"
        action["status"] = "applied"
    return actions


def attach_public_restore_actions(report: dict[str, Any], actions: list[dict[str, Any]]) -> None:
    report["public_restore_actions"] = actions
    report["summary"]["public_restore_actions"] = len(actions)


def stale_repository_records(report: dict[str, Any], stale_days: int) -> list[dict[str, Any]]:
    now = datetime.now(timezone.utc)
    records: list[dict[str, Any]] = []
    for item in report["repositories"]:
        reasons: list[str] = []
        severity = "info"
        if item.get("archived"):
            reasons.append("archived")
            severity = "warn"
        if item.get("disabled"):
            reasons.append("disabled")
            severity = "fail"
        if not item.get("default_branch"):
            reasons.append("no default branch")
            severity = "fail"
        root_issue_messages = [
            issue.get("message", "")
            for issue in item.get("issues", [])
            if issue.get("code") == "root-contents"
        ]
        if any("HTTP 409" in message for message in root_issue_messages):
            reasons.append("empty or uninitialized repository")
            severity = "fail"
        pushed_at = parse_github_datetime(item.get("pushed_at"))
        if pushed_at:
            age_days = (now - pushed_at).days
            if age_days >= stale_days:
                reasons.append(f"no pushes for {age_days} days")
        elif item.get("created_at"):
            reasons.append("no pushed_at timestamp")
        if reasons:
            records.append(
                {
                    "repo": item["name"],
                    "url": item["url"],
                    "severity": severity,
                    "visibility": item.get("visibility"),
                    "pushed_at": item.get("pushed_at"),
                    "reasons": reasons,
                }
            )
    return records


def attach_stale_repositories(report: dict[str, Any], records: list[dict[str, Any]]) -> None:
    report["stale_repositories"] = records
    report["summary"]["stale_repositories"] = len(records)


def extract_repo_mentions(path: Path, org: str, prefixes: tuple[str, ...] | None = ("skill-", "agent-")) -> set[str] | None:
    if not path.is_file():
        return None
    text = path.read_text(encoding="utf-8-sig", errors="replace")
    org_pattern = re.escape(org)
    mentions = {
        match.group(1).rstrip("/).,;'\"")
        for match in re.finditer(
            rf"github\.com/{org_pattern}/([A-Za-z0-9_.-]+)",
            text,
            flags=re.IGNORECASE,
        )
    }
    mentions.update(re.findall(r'"name"\s*:\s*"([^"]+)"', text))
    if prefixes is None:
        return mentions
    return {name for name in mentions if name.startswith(prefixes)}


def latest_registry_scan(local_root: Path) -> list[dict[str, Any]]:
    reports_dir = local_root / "registry" / "reports"
    if not reports_dir.is_dir():
        return []
    candidates = sorted(
        reports_dir.glob("scan-*.json"),
        key=lambda path: path.stat().st_mtime,
        reverse=True,
    )
    if not candidates:
        return []
    try:
        payload = json.loads(candidates[0].read_text(encoding="utf-8-sig"))
    except (OSError, json.JSONDecodeError):
        return []
    return payload if isinstance(payload, list) else []


def registry_quarantined_names(local_root: Path) -> set[str]:
    return {
        str(item.get("name"))
        for item in latest_registry_scan(local_root)
        if isinstance(item, dict) and item.get("health") == "quarantined" and item.get("name")
    }


def quantskills_denylist_names(local_root: Path) -> set[str]:
    path = local_root / "quantskills" / "data" / "curation.json"
    if not path.is_file():
        return set()
    try:
        payload = json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, json.JSONDecodeError):
        return set()
    denylist = payload.get("denylist") if isinstance(payload, dict) else None
    if not isinstance(denylist, list):
        return set()
    return {str(name) for name in denylist if name}


def expected_index_names(report: dict[str, Any], target: str, local_root: Path) -> tuple[set[str], set[str]]:
    public_names = {
        item["name"]
        for item in report["repositories"]
        if not item.get("private")
        and not item.get("archived")
        and not item.get("disabled")
    }
    ignored: set[str] = set()
    if target == "quantskills":
        ignored.update(quantskills_denylist_names(local_root))
        return public_names - ignored, ignored
    expected = {name for name in public_names if name.startswith(("skill-", "agent-"))}
    if target == "registry":
        ignored.update(REGISTRY_INDEX_EXCLUDED_REPOS)
        ignored.update(registry_quarantined_names(local_root))
    return expected - ignored, ignored


def index_update_records(report: dict[str, Any], local_root: Path | None) -> list[dict[str, Any]]:
    if not local_root:
        return [
            {
                "target": "workspace",
                "path": None,
                "status": "blocked",
                "missing": [],
                "extra": [],
                "action": "Rerun with --local-root D:/quantskill to compare homepage, registry, and quantskills files.",
            }
        ]

    actions: list[dict[str, Any]] = []
    for target, relative_path, action_text in INDEX_TARGETS:
        path = local_root / relative_path
        expected, ignored = expected_index_names(report, target, local_root)
        prefixes = None if target == "quantskills" else ("skill-", "agent-")
        mentions = extract_repo_mentions(path, report["org"], prefixes)
        if mentions is None:
            actions.append(
                {
                    "target": target,
                    "path": str(path),
                    "status": "blocked",
                    "missing": sorted(expected),
                    "extra": [],
                    "ignored": sorted(ignored),
                    "action": f"{relative_path} is missing. {action_text}",
                }
            )
            continue
        missing = sorted(expected - mentions)
        extra = sorted(mentions - expected)
        ignored_present = sorted(mentions & ignored)
        if missing or extra:
            actions.append(
                {
                    "target": target,
                    "path": str(path),
                    "status": "planned",
                    "missing": missing,
                    "extra": extra,
                    "ignored": sorted(ignored),
                    "ignored_present": ignored_present,
                    "action": action_text,
                }
            )
    return actions


def attach_index_update_actions(report: dict[str, Any], actions: list[dict[str, Any]]) -> None:
    report["index_update_actions"] = actions
    report["summary"]["index_update_actions"] = len(actions)


def markdown_table_summaries(text: str, org: str, start_marker: str, end_marker: str) -> dict[str, str]:
    start = text.find(start_marker)
    end = text.find(end_marker, start + len(start_marker)) if start >= 0 else -1
    if start < 0 or end < 0:
        return {}
    section = text[start:end]
    pattern = re.compile(
        rf"\|\s*\[([A-Za-z0-9_.-]+)\]\(https://github\.com/{re.escape(org)}/\1\)\s*\|\s*(.*?)\s*\|"
    )
    summaries: dict[str, str] = {}
    for match in pattern.finditer(section):
        summaries[match.group(1)] = match.group(2).strip()
    return summaries


def markdown_table_order(text: str, org: str, start_marker: str, end_marker: str) -> list[str]:
    start = text.find(start_marker)
    end = text.find(end_marker, start + len(start_marker)) if start >= 0 else -1
    if start < 0 or end < 0:
        return []
    section = text[start:end]
    pattern = re.compile(rf"https://github\.com/{re.escape(org)}/([A-Za-z0-9_.-]+)")
    ordered: list[str] = []
    seen: set[str] = set()
    for match in pattern.finditer(section):
        name = match.group(1)
        if name.startswith(("skill-", "agent-")) and name not in seen:
            ordered.append(name)
            seen.add(name)
    return ordered


def profile_summary_maps(path: Path, org: str) -> dict[str, dict[str, str]]:
    if not path.is_file():
        return {"zh": {}, "en": {}}
    text = path.read_text(encoding="utf-8-sig", errors="replace")
    return {
        "zh": {
            **markdown_table_summaries(text, org, "## 🗂️ 社区技能仓库一览", "## 🤖 社区 Agent 仓库一览"),
            **markdown_table_summaries(text, org, "## 🤖 社区 Agent 仓库一览", "## 🚀 如何参与"),
        },
        "en": {
            **markdown_table_summaries(text, org, "## 🗂️ Community Skill Repositories", "## 🤖 Community Agent Repositories"),
            **markdown_table_summaries(text, org, "## 🤖 Community Agent Repositories", "## 🚀 How to Participate"),
        },
    }


def profile_inventory_order(path: Path, org: str) -> dict[str, list[str]]:
    if not path.is_file():
        return {"skill": [], "agent": []}
    text = path.read_text(encoding="utf-8-sig", errors="replace")
    skill_order = markdown_table_order(text, org, "## 🗂️ 社区技能仓库一览", "## 🤖 社区 Agent 仓库一览")
    agent_order = markdown_table_order(text, org, "## 🤖 社区 Agent 仓库一览", "## 🚀 如何参与")
    return {
        "skill": [name for name in skill_order if name.startswith("skill-")],
        "agent": [name for name in agent_order if name.startswith("agent-")],
    }


def registry_summary_maps(local_root: Path) -> dict[str, dict[str, str]]:
    path = local_root / "registry" / "registry.json"
    summaries = {"zh": {}, "en": {}}
    if not path.is_file():
        return summaries
    try:
        payload = json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, json.JSONDecodeError):
        return summaries
    if not isinstance(payload, list):
        return summaries
    for item in payload:
        if not isinstance(item, dict) or not item.get("name"):
            continue
        name = str(item["name"])
        if item.get("summary_zh"):
            summaries["zh"][name] = str(item["summary_zh"])
        if item.get("summary_en"):
            summaries["en"][name] = str(item["summary_en"])
        elif item.get("description"):
            summaries["en"][name] = str(item["description"])
    return summaries


def infer_quantskills_category(name: str, entry: dict[str, Any] | None, repo: dict[str, Any] | None) -> str | None:
    if name.startswith("agent-"):
        return "09"

    category = str((entry or {}).get("category") or "").strip().lower()
    return REGISTRY_CATEGORY_TO_QUANTSKILLS_CATEGORY.get(category)


def normalize_quantskills_category_text(text: str) -> str:
    normalized = re.sub(r"[-_/&]+", " ", text.lower())
    return re.sub(r"\s+", " ", normalized).strip()


def explain_quantskills_category_suggestion(
    name: str, entry: dict[str, Any] | None, repo: dict[str, Any] | None
) -> dict[str, Any] | None:
    haystack_parts = [name]
    for source in (entry, repo):
        if not isinstance(source, dict):
            continue
        haystack_parts.extend(
            str(source.get(key) or "")
            for key in ("description", "summary_zh", "summary_en")
        )
        haystack_parts.extend(str(tag) for tag in (source.get("tags") or []) if tag)
    haystack = normalize_quantskills_category_text(" ".join(haystack_parts))
    scores: dict[str, int] = {}
    signals: dict[str, list[str]] = {}
    for category_id, weighted_groups in QUANTSKILLS_CATEGORY_SUGGESTION_RULES.items():
        for weight, phrases in weighted_groups:
            for phrase in phrases:
                normalized_phrase = normalize_quantskills_category_text(phrase)
                if normalized_phrase and normalized_phrase in haystack:
                    scores[category_id] = scores.get(category_id, 0) + weight
                    signals.setdefault(category_id, []).append(phrase)
    if not scores:
        return None

    ranked = sorted(scores.items(), key=lambda item: (-item[1], item[0]))
    category_id, score = ranked[0]
    next_score = ranked[1][1] if len(ranked) > 1 else 0
    if (
        score < QUANTSKILLS_CATEGORY_SUGGESTION_MIN_SCORE
        or score - next_score < QUANTSKILLS_CATEGORY_SUGGESTION_MIN_MARGIN
    ):
        return None
    return {
        "category": category_id,
        "score": score,
        "signals": signals.get(category_id, []),
    }


def suggest_quantskills_category(name: str, entry: dict[str, Any] | None, repo: dict[str, Any] | None) -> str | None:
    suggestion = explain_quantskills_category_suggestion(name, entry, repo)
    if not suggestion:
        return None
    return str(suggestion["category"])


def sync_quantskills_curation_from_registry(local_root: Path, report: dict[str, Any] | None = None) -> dict[str, Any]:
    curation_path = local_root / "quantskills" / "data" / "curation.json"
    registry_path = local_root / "registry" / "registry.json"
    if not curation_path.is_file():
        return {
            "target": "quantskills-curation",
            "status": "blocked",
            "path": str(curation_path),
            "action": "quantskills curation.json is missing",
        }
    if not registry_path.is_file():
        return {
            "target": "quantskills-curation",
            "status": "blocked",
            "path": str(registry_path),
            "action": "registry.json is missing; run registry generation first",
        }
    try:
        curation = json.loads(curation_path.read_text(encoding="utf-8-sig"))
        registry = json.loads(registry_path.read_text(encoding="utf-8-sig"))
    except (OSError, json.JSONDecodeError) as exc:
        return {
            "target": "quantskills-curation",
            "status": "blocked",
            "path": str(curation_path),
            "action": f"failed to read curation or registry JSON: {exc}",
        }
    if not isinstance(curation, dict) or not isinstance(registry, list):
        return {
            "target": "quantskills-curation",
            "status": "blocked",
            "path": str(curation_path),
            "action": "curation.json must be an object and registry.json must be an array",
        }

    overrides = curation.setdefault("categoryOverride", {})
    if not isinstance(overrides, dict):
        return {
            "target": "quantskills-curation",
            "status": "blocked",
            "path": str(curation_path),
            "action": "categoryOverride must be an object",
        }
    denylist = set(curation.get("denylist") or [])
    infra = set(curation.get("infra") or [])
    added: dict[str, str] = {}
    suggested: dict[str, str] = {}
    suggested_rationale: dict[str, dict[str, Any]] = {}
    registry_by_name = {
        str(entry.get("name") or ""): entry
        for entry in registry
        if isinstance(entry, dict) and entry.get("name")
    }
    for entry in registry:
        if not isinstance(entry, dict):
            continue
        name = str(entry.get("name") or "")
        if (
            not name
            or name in denylist
            or name in infra
            or name in overrides
            or name.endswith("-template")
        ):
            continue
        target = infer_quantskills_category(name, entry, None)
        if target:
            overrides[name] = target
            added[name] = target
            continue
        suggestion_detail = explain_quantskills_category_suggestion(name, entry, None)
        suggestion = str(suggestion_detail["category"]) if suggestion_detail else None
        if suggestion:
            overrides[name] = suggestion
            added[name] = suggestion
            suggested[name] = suggestion
            suggested_rationale[name] = suggestion_detail

    for repo in (report or {}).get("repositories", []):
        if not isinstance(repo, dict):
            continue
        name = str(repo.get("name") or "")
        if (
            not name
            or name in denylist
            or name in infra
            or name in overrides
            or name.endswith("-template")
            or repo.get("private")
            or repo.get("archived")
            or repo.get("disabled")
            or not name.startswith(("skill-", "agent-"))
        ):
            continue
        target = infer_quantskills_category(name, registry_by_name.get(name), repo)
        if target:
            overrides[name] = target
            added[name] = target
            continue
        suggestion_detail = explain_quantskills_category_suggestion(name, registry_by_name.get(name), repo)
        suggestion = str(suggestion_detail["category"]) if suggestion_detail else None
        if suggestion:
            overrides[name] = suggestion
            added[name] = suggestion
            suggested[name] = suggestion
            suggested_rationale[name] = suggestion_detail

    if not added:
        return {
            "target": "quantskills-curation",
            "status": "unchanged",
            "path": str(curation_path),
            "action": "categoryOverride already covers registry and high-confidence business-signal categories",
            "added": {},
            "suggested": suggested,
            "suggestedRationale": suggested_rationale,
        }

    curation["categoryOverride"] = dict(sorted(overrides.items(), key=lambda item: (item[1], item[0].lower())))
    curation_path.write_text(
        json.dumps(curation, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    return {
        "target": "quantskills-curation",
        "status": "updated",
        "path": str(curation_path),
        "action": "synchronized quantskills categoryOverride from registry and high-confidence business-signal categories",
        "added": added,
        "suggested": suggested,
        "suggestedRationale": suggested_rationale,
    }


def safe_repo_summary(item: dict[str, Any], lang: str) -> str:
    description = str(item.get("description") or "").strip()
    if description:
        return description
    if lang == "zh":
        return "QuantSkills 社区项目；请维护者补充准确、克制的一句话说明。"
    return "QuantSkills community project; maintainers should add an accurate one-line summary."


def public_inventory_items(
    report: dict[str, Any],
    prefix: str,
    preferred_order: list[str] | None = None,
) -> list[dict[str, Any]]:
    items = [
        item
        for item in report["repositories"]
        if item["name"].startswith(prefix)
        and not item.get("private")
        and not item.get("archived")
        and not item.get("disabled")
    ]
    by_name = {item["name"]: item for item in items}
    ordered: list[dict[str, Any]] = []
    seen: set[str] = set()
    for name in preferred_order or []:
        if name in by_name and name not in seen:
            ordered.append(by_name[name])
            seen.add(name)
    ordered.extend(sorted((item for item in items if item["name"] not in seen), key=lambda item: item["name"].lower()))
    return ordered


def render_inventory_rows(
    org: str,
    items: list[dict[str, Any]],
    summaries: dict[str, str],
    lang: str,
) -> list[str]:
    lines = ["| 仓库 | 一句话说明 |" if lang == "zh" else "| Repository | One-line summary |", "|---|---|"]
    for item in items:
        name = item["name"]
        summary = summaries.get(name) or safe_repo_summary(item, lang)
        lines.append(f"| [{name}](https://github.com/{org}/{name}) | {summary} |")
    return lines


def render_profile_inventory_sections(
    report: dict[str, Any],
    local_root: Path,
    profile_path: Path,
) -> dict[str, str]:
    org = report["org"]
    existing = profile_summary_maps(profile_path, org)
    order = profile_inventory_order(profile_path, org)
    registry = registry_summary_maps(local_root)
    summaries = {
        "zh": {**registry["zh"], **existing["zh"]},
        "en": {**registry["en"], **existing["en"]},
    }
    skills = public_inventory_items(report, "skill-", order["skill"])
    agents = public_inventory_items(report, "agent-", order["agent"])
    top_skills = skills[:6]
    remaining_skills = skills[6:]

    zh_skill = [
        "## 🗂️ 社区技能仓库一览",
        "",
        "下表与 [registry/INDEX.md](https://github.com/quantskills/registry/blob/main/INDEX.md) 中的 Skill 资产目录保持同步。",
        "",
        *render_inventory_rows(org, top_skills, summaries["zh"], "zh"),
        "",
    ]
    if remaining_skills:
        zh_skill.extend(
            [
                f"<details>",
                f"<summary>显示更多：剩余 {len(remaining_skills)} 个 Skill 仓库</summary>",
                "",
                *render_inventory_rows(org, remaining_skills, summaries["zh"], "zh"),
                "",
                "</details>",
                "",
            ]
        )

    zh_agent = [
        "## 🤖 社区 Agent 仓库一览",
        "",
        "下表与 [registry/INDEX.md](https://github.com/quantskills/registry/blob/main/INDEX.md) 中的 Agent 资产目录保持同步。",
        "",
        *render_inventory_rows(org, agents, summaries["zh"], "zh"),
        "",
    ]

    en_skill = [
        "## 🗂️ Community Skill Repositories",
        "",
        "This table mirrors the Skill asset directory in [registry/INDEX.md](https://github.com/quantskills/registry/blob/main/INDEX.md).",
        "",
        *render_inventory_rows(org, top_skills, summaries["en"], "en"),
        "",
    ]
    if remaining_skills:
        en_skill.extend(
            [
                f"<details>",
                f"<summary>Show more: remaining {len(remaining_skills)} Skill repositories</summary>",
                "",
                *render_inventory_rows(org, remaining_skills, summaries["en"], "en"),
                "",
                "</details>",
                "",
            ]
        )

    en_agent = [
        "## 🤖 Community Agent Repositories",
        "",
        "This table mirrors the Agent asset directory in [registry/INDEX.md](https://github.com/quantskills/registry/blob/main/INDEX.md).",
        "",
        *render_inventory_rows(org, agents, summaries["en"], "en"),
        "",
    ]
    return {
        "zh_skill": "\n".join(zh_skill).rstrip() + "\n\n",
        "zh_agent": "\n".join(zh_agent).rstrip() + "\n\n",
        "en_skill": "\n".join(en_skill).rstrip() + "\n\n",
        "en_agent": "\n".join(en_agent).rstrip() + "\n\n",
    }


def replace_between(text: str, start_marker: str, end_marker: str, replacement: str) -> tuple[str, bool]:
    start = text.find(start_marker)
    end = text.find(end_marker, start + len(start_marker)) if start >= 0 else -1
    if start < 0 or end < 0:
        return text, False
    return text[:start] + replacement + text[end:], True


def sync_homepage_profile(report: dict[str, Any], local_root: Path) -> dict[str, Any]:
    path = local_root / ".github" / "profile" / "README.md"
    if not path.is_file():
        return {
            "target": "homepage",
            "status": "blocked",
            "path": str(path),
            "action": "profile README is missing",
        }
    original = path.read_text(encoding="utf-8-sig", errors="replace")
    sections = render_profile_inventory_sections(report, local_root, path)
    updated, ok1 = replace_between(original, "## 🗂️ 社区技能仓库一览", "## 🤖 社区 Agent 仓库一览", sections["zh_skill"])
    updated, ok2 = replace_between(updated, "## 🤖 社区 Agent 仓库一览", "## 🚀 如何参与", sections["zh_agent"])
    updated, ok3 = replace_between(updated, "## 🗂️ Community Skill Repositories", "## 🤖 Community Agent Repositories", sections["en_skill"])
    updated, ok4 = replace_between(updated, "## 🤖 Community Agent Repositories", "## 🚀 How to Participate", sections["en_agent"])
    if not all([ok1, ok2, ok3, ok4]):
        return {
            "target": "homepage",
            "status": "blocked",
            "path": str(path),
            "action": "profile README headings were not found",
        }
    if updated != original:
        path.write_text(updated, encoding="utf-8", newline="\n")
        status = "updated"
    else:
        status = "unchanged"
    return {
        "target": "homepage",
        "status": status,
        "path": str(path),
        "action": "synchronized .github/profile/README.md from current public inventory",
    }


def run_generation_command(
    target: str,
    command: list[str],
    cwd: Path,
    env: dict[str, str] | None = None,
    timeout: int = 900,
) -> dict[str, Any]:
    try:
        result = subprocess.run(
            command,
            cwd=str(cwd),
            env=env,
            text=True,
            encoding="utf-8",
            errors="replace",
            capture_output=True,
            check=False,
            timeout=timeout,
        )
    except subprocess.TimeoutExpired as exc:
        return {
            "target": target,
            "status": "failed",
            "path": str(cwd),
            "action": " ".join(command),
            "returncode": None,
            "stdout": (exc.stdout or "").strip()[-2000:] if isinstance(exc.stdout, str) else "",
            "stderr": f"command timed out after {timeout} seconds",
        }
    except OSError as exc:
        return {
            "target": target,
            "status": "blocked",
            "path": str(cwd),
            "action": f"command failed to start: {exc}",
        }
    return {
        "target": target,
        "status": "applied" if result.returncode == 0 else "failed",
        "path": str(cwd),
        "action": " ".join(command),
        "returncode": result.returncode,
        "stdout": result.stdout.strip()[-2000:],
        "stderr": result.stderr.strip()[-2000:],
    }


def apply_index_updates(
    report: dict[str, Any],
    local_root: Path | None,
    python_bin: str,
    node_bin: str,
) -> list[dict[str, Any]]:
    if not local_root:
        return [
            {
                "target": "workspace",
                "status": "blocked",
                "path": None,
                "action": "Rerun with --local-root D:/quantskill to apply homepage, registry, and quantskills sync.",
            }
        ]
    records = [sync_homepage_profile(report, local_root)]
    registry_script = local_root / "registry" / "scripts" / "build_registry.py"
    if registry_script.is_file():
        records.append(
            run_generation_command(
                "registry",
                [python_bin, str(registry_script), "--full", "--audit-dir", "reports"],
                local_root / "registry",
            )
        )
    else:
        records.append(
            {
                "target": "registry",
                "status": "blocked",
                "path": str(registry_script),
                "action": "registry generator script is missing",
            }
        )
    records.append(sync_quantskills_curation_from_registry(local_root, report))
    quantskills_script = local_root / "quantskills" / "scripts" / "build.mjs"
    if quantskills_script.is_file():
        env = dict(os.environ)
        env["QS_REGISTRY_JSON"] = str(local_root / "registry" / "registry.json")
        records.append(
            run_generation_command(
                "quantskills",
                [node_bin, str(quantskills_script)],
                local_root / "quantskills",
                env=env,
            )
        )
    else:
        records.append(
            {
                "target": "quantskills",
                "status": "blocked",
                "path": str(quantskills_script),
                "action": "quantskills generator script is missing",
            }
        )
    return records


def attach_index_apply_actions(report: dict[str, Any], actions: list[dict[str, Any]]) -> None:
    report["index_apply_actions"] = actions
    report["summary"]["index_apply_actions"] = len(actions)


def default_update_state_path() -> Path:
    return Path(__file__).resolve().parents[1] / "outputs" / "update-check-state.json"


def load_update_state(path: Path) -> dict[str, Any]:
    if not path.is_file():
        return {"schema": 1, "repositories": {}}
    payload = json.loads(path.read_text(encoding="utf-8-sig"))
    if not isinstance(payload, dict):
        raise ValueError(f"Update state file must contain a JSON object: {path}")
    payload.setdefault("schema", 1)
    payload.setdefault("repositories", {})
    if not isinstance(payload["repositories"], dict):
        raise ValueError(f"Update state repositories must be an object: {path}")
    return payload


def write_update_state(path: Path, state: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(state, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def update_fingerprint_payload(item: dict[str, Any]) -> dict[str, Any]:
    return {
        "name": item["name"],
        "visibility": item.get("visibility"),
        "private": item.get("private"),
        "archived": item.get("archived"),
        "disabled": item.get("disabled"),
        "default_branch": item.get("default_branch"),
        "pushed_at": item.get("pushed_at"),
        "inferred_type": item.get("inferred_type"),
        "has_root_readme": item.get("has_root_readme"),
        "root_files": item.get("root_files", []),
        "issues": [
            {
                "code": issue.get("code"),
                "severity": issue.get("severity"),
                "message": issue.get("message"),
            }
            for issue in item.get("issues", [])
        ],
    }


def update_fingerprint(item: dict[str, Any]) -> str:
    return stable_hash(update_fingerprint_payload(item))


def normalize_changed_path(path: str) -> str:
    return path.replace("\\", "/").lstrip("/")


def is_low_risk_update_path(path: str) -> bool:
    normalized = normalize_changed_path(path)
    lower = normalized.lower()
    name = lower.rsplit("/", 1)[-1]
    suffix = Path(lower).suffix
    if normalized in TEST_RELEVANT_EXACT_PATHS or lower in {p.lower() for p in TEST_RELEVANT_EXACT_PATHS}:
        return False
    if lower.startswith(TEST_RELEVANT_PREFIXES):
        return False
    if suffix in TEST_RELEVANT_EXTENSIONS and suffix not in LOW_RISK_DOC_EXTENSIONS:
        return False
    if name in LOW_RISK_DOC_FILENAMES:
        return True
    if lower.startswith(LOW_RISK_DOC_PREFIXES) and suffix in LOW_RISK_DOC_EXTENSIONS:
        return True
    return suffix in LOW_RISK_DOC_EXTENSIONS and "/" not in lower


def classify_update_files(changed_files: list[str], compare_warning: str | None) -> dict[str, Any]:
    if compare_warning:
        return {
            "scope": "unknown",
            "risk": "medium",
            "summary": compare_warning,
            "test_relevant_files": [],
            "low_risk_files": changed_files,
        }
    if not changed_files:
        return {
            "scope": "unknown",
            "risk": "medium",
            "summary": "changed files unavailable",
            "test_relevant_files": [],
            "low_risk_files": [],
        }
    low_risk = [path for path in changed_files if is_low_risk_update_path(path)]
    test_relevant = [path for path in changed_files if path not in low_risk]
    if test_relevant:
        return {
            "scope": "test-relevant",
            "risk": "high",
            "summary": "runtime, code, dependency, workflow, reference, or declaration files changed",
            "test_relevant_files": test_relevant,
            "low_risk_files": low_risk,
        }
    return {
        "scope": "low-risk",
        "risk": "low",
        "summary": "only documentation, license, examples, or static assets changed",
        "test_relevant_files": [],
        "low_risk_files": low_risk,
    }


def recommended_update_checks(item: dict[str, Any], scope: str) -> list[str]:
    checks = ["rerun repository structure audit"]
    inferred_type = item.get("inferred_type")
    if inferred_type == "skill":
        checks.append("validate SKILL.md and five-runtime adapter consistency")
    if inferred_type == "agent":
        checks.append("validate AGENTS.md and agent runtime instructions")
    if scope == "test-relevant":
        checks.append("run repository-specific tests or smoke tests before marking accepted")
    elif scope == "low-risk":
        checks.append("review documentation claims, links, licenses, and risk language before skipping tests")
    else:
        checks.append("inspect the commit diff manually because changed-file scope is unknown")
    return checks


def ensure_update_heads(
    report: dict[str, Any],
    org: str,
    token: str | None,
    from_fixture: bool,
    needed_names: set[str],
) -> None:
    if from_fixture:
        return
    for item in report["repositories"]:
        if item["name"] not in needed_names:
            continue
        if item.get("head_sha") or not item.get("default_branch"):
            continue
        if item.get("archived") or item.get("disabled"):
            continue
        try:
            item["head_sha"] = fetch_default_branch_head(
                org,
                item["name"],
                item.get("default_branch"),
                token,
            )
        except urllib.error.HTTPError as exc:
            item["head_sha_warning"] = f"head sha unavailable via GitHub API: HTTP {exc.code}"
        except urllib.error.URLError as exc:
            item["head_sha_warning"] = f"head sha unavailable via GitHub API: {exc.reason}"


def update_check_records(
    report: dict[str, Any],
    state: dict[str, Any],
    org: str,
    token: str | None,
    from_fixture: bool,
) -> list[dict[str, Any]]:
    previous = state.get("repositories", {})
    actions: list[dict[str, Any]] = []
    for item in report["repositories"]:
        name = item["name"]
        current_fingerprint = update_fingerprint(item)
        current_head = item.get("head_sha")
        prior = previous.get(name, {}) if isinstance(previous.get(name, {}), dict) else {}
        accepted_fingerprint = prior.get("accepted_fingerprint")
        accepted_head = prior.get("accepted_head_sha")
        last_accepted_at = prior.get("accepted_at")
        changed_files = sorted(set(item.get("changed_files") or []))
        compare_warning = None
        status = "skip"
        reason = "unchanged since accepted baseline"
        scope = "unchanged"
        risk = "low"

        if not prior:
            status = "test-required"
            reason = "new repository has no accepted baseline"
            scope = "new"
            risk = "high"
        elif not accepted_fingerprint and not accepted_head:
            status = "test-required"
            reason = "repository was seen before but has never been marked tested or accepted"
            scope = "untested"
            risk = "high"
        elif (
            accepted_fingerprint
            and current_fingerprint == accepted_fingerprint
            and (not current_head or not accepted_head or current_head == accepted_head)
        ):
            status = "skip"
        else:
            if not changed_files and accepted_head and current_head and accepted_head != current_head:
                if from_fixture:
                    compare_warning = "fixture did not provide changed_files"
                else:
                    changed_files, compare_warning = fetch_changed_files(
                        org,
                        name,
                        str(accepted_head),
                        str(current_head),
                        token,
                    )
            elif not changed_files and current_head and accepted_head and current_head == accepted_head:
                changed_files = []
            classification = classify_update_files(changed_files, compare_warning)
            scope = classification["scope"]
            risk = classification["risk"]
            if scope == "low-risk":
                status = "review-only"
                reason = "updated after accepted baseline, but changed files are low risk; tests may be skipped after review"
            else:
                status = "test-required"
                reason = f"updated after accepted baseline; {classification['summary']}"

        if any(issue.get("severity") == "fail" for issue in item.get("issues", [])) and status != "skip":
            risk = "high"

        actions.append(
            {
                "repo": name,
                "url": item.get("url"),
                "status": status,
                "reason": reason,
                "risk": risk,
                "scope": scope,
                "accepted_at": last_accepted_at,
                "previous_head_sha": accepted_head,
                "current_head_sha": current_head,
                "head_sha_warning": item.get("head_sha_warning"),
                "current_fingerprint": current_fingerprint,
                "accepted_fingerprint": accepted_fingerprint,
                "changed_files": changed_files,
                "recommended_checks": recommended_update_checks(item, scope),
            }
        )
    return actions


def attach_update_check_actions(
    report: dict[str, Any],
    actions: list[dict[str, Any]],
    state_path: Path,
) -> None:
    report["update_check_state_file"] = str(state_path)
    report["update_check_actions"] = actions
    report["summary"]["update_check_actions"] = len(actions)
    report["summary"]["update_tests_required"] = sum(
        1 for action in actions if action["status"] == "test-required"
    )
    report["summary"]["update_review_only"] = sum(
        1 for action in actions if action["status"] == "review-only"
    )
    report["summary"]["update_skipped"] = sum(
        1 for action in actions if action["status"] == "skip"
    )


def update_head_names_needed(
    report: dict[str, Any],
    state: dict[str, Any],
    marked_repos: list[str],
    plan_update_tests: bool,
    write_state: bool,
) -> set[str]:
    needed: set[str] = set()
    previous = state.get("repositories", {})
    if plan_update_tests:
        for item in report["repositories"]:
            prior = previous.get(item["name"], {}) if isinstance(previous.get(item["name"], {}), dict) else {}
            if prior.get("accepted_fingerprint") or prior.get("accepted_head_sha"):
                needed.add(item["name"])
    if write_state and marked_repos:
        if "all" in marked_repos:
            needed.update(item["name"] for item in report["repositories"])
        else:
            needed.update(marked_repos)
    return needed


def build_update_state(
    prior_state: dict[str, Any],
    report: dict[str, Any],
    marked_repos: list[str],
) -> dict[str, Any]:
    marked = set(marked_repos or [])
    mark_all = "all" in marked
    current_names = {item["name"] for item in report["repositories"]}
    unknown_marks = sorted(name for name in marked if name != "all" and name not in current_names)
    if unknown_marks:
        raise ValueError(f"--mark-tested names not present in current report: {', '.join(unknown_marks)}")

    repositories = dict(prior_state.get("repositories", {}))
    generated_at = report["generated_at"]
    for item in report["repositories"]:
        name = item["name"]
        entry = dict(repositories.get(name, {}))
        fingerprint = update_fingerprint(item)
        entry.update(
            {
                "last_seen_at": generated_at,
                "last_seen": {
                    "name": name,
                    "url": item.get("url"),
                    "visibility": item.get("visibility"),
                    "private": item.get("private"),
                    "default_branch": item.get("default_branch"),
                    "pushed_at": item.get("pushed_at"),
                    "updated_at": item.get("updated_at"),
                    "head_sha": item.get("head_sha"),
                    "fingerprint": fingerprint,
                    "issue_codes": [issue.get("code") for issue in item.get("issues", [])],
                },
            }
        )
        if mark_all or name in marked:
            entry.update(
                {
                    "accepted_at": generated_at,
                    "accepted_fingerprint": fingerprint,
                    "accepted_head_sha": item.get("head_sha"),
                    "accepted_pushed_at": item.get("pushed_at"),
                    "accepted_issue_codes": [
                        issue.get("code") for issue in item.get("issues", [])
                    ],
                }
            )
        repositories[name] = entry

    return {
        "schema": 1,
        "org": report["org"],
        "updated_at": generated_at,
        "repositories": repositories,
    }


def detect_test_commands(repo_dir: Path, python_bin: str) -> list[list[str]]:
    commands: list[list[str]] = []
    if (repo_dir / "scripts" / "validate.py").is_file():
        commands.append([python_bin, "scripts/validate.py"])
    if (repo_dir / "tests").is_dir():
        commands.append([python_bin, "-m", "unittest", "discover", "-s", "tests"])
    if (repo_dir / "package.json").is_file():
        commands.append(["npm", "test"])
    if not commands and any((repo_dir / name).is_file() for name in ("pyproject.toml", "requirements.txt")):
        commands.append([python_bin, "-m", "compileall", "-q", "."])
    return commands


def run_local_test_command(command: list[str], repo_dir: Path, timeout: int) -> dict[str, Any]:
    try:
        result = subprocess.run(
            command,
            cwd=str(repo_dir),
            text=True,
            encoding="utf-8",
            errors="replace",
            capture_output=True,
            timeout=timeout,
            check=False,
        )
    except subprocess.TimeoutExpired as exc:
        return {
            "command": " ".join(command),
            "status": "timeout",
            "returncode": None,
            "stdout": (exc.stdout or "")[-2000:] if isinstance(exc.stdout, str) else "",
            "stderr": (exc.stderr or "")[-2000:] if isinstance(exc.stderr, str) else "",
        }
    except OSError as exc:
        return {
            "command": " ".join(command),
            "status": "blocked",
            "returncode": None,
            "stdout": "",
            "stderr": str(exc),
        }
    return {
        "command": " ".join(command),
        "status": "passed" if result.returncode == 0 else "failed",
        "returncode": result.returncode,
        "stdout": result.stdout.strip()[-2000:],
        "stderr": result.stderr.strip()[-2000:],
    }


def run_update_tests(
    report: dict[str, Any],
    local_root: Path | None,
    selected_repos: list[str],
    python_bin: str,
    timeout: int,
) -> list[dict[str, Any]]:
    if not local_root:
        return [
            {
                "repo": None,
                "status": "blocked",
                "reason": "Rerun with --local-root D:/quantskill to run local update tests.",
                "commands": [],
            }
        ]
    selected = set(selected_repos or [])
    actions = report.get("update_check_actions", [])
    results: list[dict[str, Any]] = []
    for action in actions:
        repo_name = action["repo"]
        if selected and repo_name not in selected:
            continue
        if action.get("status") != "test-required":
            continue
        repo_dir = local_repo_dir(local_root, repo_name)
        if not repo_dir:
            results.append(
                {
                    "repo": repo_name,
                    "status": "blocked",
                    "reason": "local checkout not found",
                    "commands": [],
                }
            )
            continue
        commands = detect_test_commands(repo_dir, python_bin)
        if not commands:
            results.append(
                {
                    "repo": repo_name,
                    "status": "blocked",
                    "reason": "no deterministic local test command detected",
                    "commands": [],
                }
            )
            continue
        command_results = [run_local_test_command(command, repo_dir, timeout) for command in commands]
        status = "passed" if all(item["status"] == "passed" for item in command_results) else "failed"
        results.append(
            {
                "repo": repo_name,
                "status": status,
                "reason": "ran detected local test command(s)",
                "commands": command_results,
            }
        )
    return results


def attach_test_run_results(report: dict[str, Any], results: list[dict[str, Any]]) -> None:
    report["test_run_results"] = results
    report["summary"]["test_run_results"] = len(results)
    report["summary"]["test_run_passed"] = sum(1 for item in results if item.get("status") == "passed")
    report["summary"]["test_run_failed"] = sum(1 for item in results if item.get("status") == "failed")
    report["summary"]["test_run_blocked"] = sum(1 for item in results if item.get("status") == "blocked")


def issue_summary(item: dict[str, Any]) -> str:
    if not item["issues"]:
        return "ok"
    parts = []
    for issue in item["issues"]:
        parts.append(f"{issue['severity']}:{issue['code']}")
    return ", ".join(parts)


def to_markdown(report: dict[str, Any]) -> str:
    lines = [
        f"# QuantSkills Repository Audit",
        "",
        f"- Organization: `{report['org']}`",
        f"- Generated at: `{report['generated_at']}`",
        f"- Source: `{report['source']}`",
        f"- Repositories: `{report['summary']['repositories']}`",
        f"- Repositories with failures: `{report['summary']['repositories_with_failures']}`",
        f"- Repositories with warnings: `{report['summary']['repositories_with_warnings']}`",
        f"- Local README fixes applied: `{report['summary']['local_readmes_fixed']}`",
        f"- Governance actions: `{report['summary'].get('governance_actions', 0)}`",
        f"- Public restore actions: `{report['summary'].get('public_restore_actions', 0)}`",
        f"- Stale or invalid repositories: `{report['summary'].get('stale_repositories', 0)}`",
        f"- Index update actions: `{report['summary'].get('index_update_actions', 0)}`",
        f"- Index apply actions: `{report['summary'].get('index_apply_actions', 0)}`",
        f"- Update-check actions: `{report['summary'].get('update_check_actions', 0)}`",
        f"- Update tests required: `{report['summary'].get('update_tests_required', 0)}`",
        f"- Update review-only: `{report['summary'].get('update_review_only', 0)}`",
        f"- Update skipped: `{report['summary'].get('update_skipped', 0)}`",
        f"- Test run results: `{report['summary'].get('test_run_results', 0)}`",
        f"- Test run passed: `{report['summary'].get('test_run_passed', 0)}`",
        f"- Test run failed: `{report['summary'].get('test_run_failed', 0)}`",
        f"- Test run blocked: `{report['summary'].get('test_run_blocked', 0)}`",
        "",
        "## Summary Table",
        "",
        "| Repository | Type | Visibility | Prefix | Root README | Issues |",
        "| --- | --- | --- | --- | --- | --- |",
    ]
    for item in report["repositories"]:
        prefix = "yes" if item["has_prefix"] or item["exempt"] else "no"
        readme = "yes" if item["has_root_readme"] else "no"
        lines.append(
            f"| [{item['name']}]({item['url']}) | {item['inferred_type']} | {item['visibility']} | {prefix} | {readme} | {issue_summary(item)} |"
        )

    problem_items = [item for item in report["repositories"] if item["issues"] or item["fixed"]]
    if problem_items:
        lines.extend(["", "## Details", ""])
        for item in problem_items:
            lines.append(f"### {item['name']}")
            if item["fixed"]:
                for fixed in item["fixed"]:
                    lines.append(f"- fixed: {fixed}")
            for issue in item["issues"]:
                line = f"- {issue['severity']}: {issue['message']}"
                if issue.get("action"):
                    line += f" Action: {issue['action']}"
                lines.append(line)
            lines.append("")
    if report.get("governance_actions"):
        lines.extend(["", "## Governance Actions", ""])
        for action in report["governance_actions"]:
            codes = ", ".join(action.get("issue_codes") or [])
            line = (
                f"- {action['status']}: `{action['repo']}` "
                f"{action['visibility_action']}; {action['issue_action']}"
            )
            if codes:
                line += f"; issues: {codes}"
            if action.get("visibility_action") == "set-private" and action.get("reasons"):
                reasons = "; ".join(
                    f"{reason.get('code', 'unknown')}: {reason.get('message', '')}"
                    for reason in action["reasons"]
                )
                if reasons:
                    line += f"; private reasons: {reasons}"
            if action.get("issue_url"):
                line += f" ({action['issue_url']})"
            lines.append(line)
    if report.get("public_restore_actions"):
        lines.extend(["", "## Public Restore Actions", ""])
        for action in report["public_restore_actions"]:
            line = (
                f"- {action['status']}: `{action['repo']}` "
                f"{action['visibility_action']}; {action['issue_action']}"
            )
            if action.get("issue_url"):
                line += f" ({action['issue_url']})"
            lines.append(line)
    if report.get("stale_repositories"):
        lines.extend(["", "## Stale Or Invalid Repositories", ""])
        for record in report["stale_repositories"]:
            reasons = "; ".join(record["reasons"])
            lines.append(
                f"- {record['severity']}: [{record['repo']}]({record['url']}) "
                f"({record['visibility']}, pushed_at={record.get('pushed_at')}) - {reasons}"
            )
    if report.get("index_update_actions"):
        lines.extend(["", "## Index Update Actions", ""])
        for action in report["index_update_actions"]:
            lines.append(f"- {action['status']}: `{action['target']}` - {action['action']}")
            if action.get("path"):
                lines.append(f"  - path: `{action['path']}`")
            if action.get("missing"):
                lines.append(f"  - missing: {', '.join(action['missing'])}")
            if action.get("extra"):
                lines.append(f"  - extra: {', '.join(action['extra'])}")
            if action.get("ignored"):
                lines.append(f"  - ignored by target rules: {', '.join(action['ignored'])}")
            if action.get("ignored_present"):
                lines.append(f"  - ignored but present: {', '.join(action['ignored_present'])}")
    if report.get("index_apply_actions"):
        lines.extend(["", "## Index Apply Actions", ""])
        for action in report["index_apply_actions"]:
            lines.append(f"- {action['status']}: `{action['target']}` - {action['action']}")
            if action.get("path"):
                lines.append(f"  - path: `{action['path']}`")
            if action.get("returncode") is not None:
                lines.append(f"  - returncode: `{action['returncode']}`")
            if action.get("stderr"):
                lines.append(f"  - stderr: {action['stderr']}")
    if report.get("update_check_actions"):
        lines.extend(["", "## Update Check Actions", ""])
        if report.get("update_check_state_file"):
            lines.append(f"- State file: `{report['update_check_state_file']}`")
            lines.append("")
        lines.extend(
            [
                "| Repository | Decision | Risk | Reason | Changed Files |",
                "| --- | --- | --- | --- | --- |",
            ]
        )
        for action in report["update_check_actions"]:
            files = ", ".join(action.get("changed_files") or [])
            if len(files) > 160:
                files = files[:157] + "..."
            if not files:
                files = "-"
            lines.append(
                f"| [{action['repo']}]({action['url']}) | {action['status']} | "
                f"{action['risk']} | {action['reason']} | {files} |"
            )
        lines.extend(["", "### Recommended Checks", ""])
        for action in report["update_check_actions"]:
            if action["status"] == "skip":
                continue
            checks = "; ".join(action.get("recommended_checks", []))
            lines.append(f"- `{action['repo']}`: {checks}")
    if report.get("state_write"):
        state_write = report["state_write"]
        lines.extend(["", "## State Write", ""])
        lines.append(
            f"- {state_write['status']}: `{state_write['path']}` "
            f"(marked: {', '.join(state_write.get('marked_repos') or ['none'])})"
        )
    if report.get("test_run_results"):
        lines.extend(["", "## Test Run Results", ""])
        for result in report["test_run_results"]:
            lines.append(f"- {result['status']}: `{result.get('repo')}` - {result.get('reason')}")
            for command in result.get("commands", []):
                line = f"  - {command['status']}: `{command['command']}`"
                if command.get("returncode") is not None:
                    line += f" (returncode={command['returncode']})"
                lines.append(line)
                if command.get("stderr"):
                    lines.append(f"    - stderr: {command['stderr']}")
    return "\n".join(lines).rstrip() + "\n"


def write_output(path: str | None, content: str) -> None:
    if not path:
        return
    output_path = Path(path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(content, encoding="utf-8", newline="\n")


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--org", default="quantskills", help="GitHub organization to audit")
    parser.add_argument("--token", help="GitHub token. Defaults to GITHUB_TOKEN or GH_TOKEN.")
    parser.add_argument(
        "--include-private",
        action="store_true",
        help="Request all repositories. Requires a token with organization repository access.",
    )
    parser.add_argument("--local-root", help="Local directory containing repository checkouts")
    parser.add_argument(
        "--fix-local-readme",
        action="store_true",
        help="Create or copy missing root README.md files in local checkouts. Never writes to GitHub.",
    )
    parser.add_argument(
        "--plan-governance-actions",
        action="store_true",
        help="Add safe remediation actions to the report without writing to GitHub.",
    )
    parser.add_argument(
        "--apply-governance-actions",
        action="store_true",
        help=(
            "Apply safe GitHub remediation: set skill-/agent-prefixed repositories missing "
            "SKILL.md/AGENTS.md to private, and create/update bilingual community-rule "
            "Issues for naming, README.en, LICENSE, runtime-adapter, and declaration problems."
        ),
    )
    parser.add_argument(
        "--plan-public-restore",
        action="store_true",
        help=(
            "Add planned public visibility restoration actions for private skill-/agent-prefixed "
            "repositories that no longer have fail-level audit issues."
        ),
    )
    parser.add_argument(
        "--apply-public-restore",
        action="store_true",
        help=(
            "Set eligible private skill-/agent-prefixed repositories back to public and close "
            "their remediation issue when present. Requires explicit maintainer approval."
        ),
    )
    parser.add_argument(
        "--report-stale-repos",
        action="store_true",
        help="Report archived, disabled, empty, uninitialized, or stale repositories.",
    )
    parser.add_argument(
        "--stale-days",
        type=int,
        default=180,
        help="Days without pushes before a repository is reported as stale. Default: 180.",
    )
    parser.add_argument(
        "--plan-index-updates",
        action="store_true",
        help=(
            "Compare public skill-* and agent-* repositories against local homepage, registry, "
            "and quantskills navigation files. Use with --local-root D:/quantskill."
        ),
    )
    parser.add_argument(
        "--apply-index-updates",
        action="store_true",
        help=(
            "Synchronize .github/profile/README.md and run local registry/quantskills generator "
            "scripts. Requires explicit maintainer approval and --local-root."
        ),
    )
    parser.add_argument(
        "--python-bin",
        default=sys.executable,
        help="Python executable used by --apply-index-updates. Defaults to the current interpreter.",
    )
    parser.add_argument(
        "--node-bin",
        default="node",
        help="Node executable used by --apply-index-updates. Defaults to node on PATH.",
    )
    parser.add_argument(
        "--plan-update-tests",
        action="store_true",
        help=(
            "Compare the current repository inventory with the update-check state file and "
            "plan which new or changed repositories need tests, review-only handling, or no action."
        ),
    )
    parser.add_argument(
        "--run-update-tests",
        action="store_true",
        help=(
            "Run detected local test or smoke-test commands for repositories whose update-check "
            "decision is test-required. Must be used with --plan-update-tests and --local-root."
        ),
    )
    parser.add_argument(
        "--test-repo",
        action="append",
        default=[],
        help="Limit --run-update-tests to a repository name. May be repeated.",
    )
    parser.add_argument(
        "--test-timeout",
        type=int,
        default=120,
        help="Per-command timeout in seconds for --run-update-tests. Default: 120.",
    )
    parser.add_argument(
        "--state-file",
        help=(
            "JSON state file for update checks. Defaults to outputs/update-check-state.json "
            "inside this skill package when update checking or state writing is used."
        ),
    )
    parser.add_argument(
        "--write-state",
        action="store_true",
        help="Write the latest observed repository snapshots to the update-check state file.",
    )
    parser.add_argument(
        "--mark-tested",
        action="append",
        default=[],
        help=(
            "Repository name to mark as tested or accepted in the state file after checks pass. "
            "Repeat as needed, or use 'all' after all current repositories are accepted."
        ),
    )
    parser.add_argument(
        "--community-rules-url",
        default=COMMUNITY_RULES_URL,
        help="Community rules URL to include in remediation issues.",
    )
    parser.add_argument(
        "--allow-special",
        action="append",
        default=[],
        help="Additional repository name to exempt from skill-/agent- prefix checks. May be repeated.",
    )
    parser.add_argument(
        "--repositories-json",
        help="Use a local JSON fixture instead of the GitHub API. Useful for tests.",
    )
    parser.add_argument("--json-output", help="Write full JSON report to this path")
    parser.add_argument("--markdown", help="Write Markdown report to this path")
    parser.add_argument(
        "--fail-on-issues",
        action="store_true",
        help="Exit 2 when failures are found and 1 when only warnings are found.",
    )
    return parser.parse_args(argv)


def main(argv: list[str]) -> int:
    args = parse_args(argv)
    if args.fix_local_readme and not args.local_root:
        print("--fix-local-readme requires --local-root", file=sys.stderr)
        return 2
    token = resolve_token(args)
    if args.apply_governance_actions and args.repositories_json:
        print("--apply-governance-actions cannot be used with --repositories-json", file=sys.stderr)
        return 2
    if args.apply_governance_actions and not token:
        print("--apply-governance-actions requires --token, GITHUB_TOKEN, or GH_TOKEN", file=sys.stderr)
        return 2
    if args.apply_public_restore and args.repositories_json:
        print("--apply-public-restore cannot be used with --repositories-json", file=sys.stderr)
        return 2
    if args.apply_public_restore and not token:
        print("--apply-public-restore requires --token, GITHUB_TOKEN, or GH_TOKEN", file=sys.stderr)
        return 2
    if args.apply_public_restore and not args.include_private:
        print("--apply-public-restore requires --include-private so private repositories are audited", file=sys.stderr)
        return 2
    if args.mark_tested and not args.write_state:
        print("--mark-tested requires --write-state", file=sys.stderr)
        return 2
    if args.apply_index_updates and not args.local_root:
        print("--apply-index-updates requires --local-root", file=sys.stderr)
        return 2
    if args.run_update_tests and not args.plan_update_tests:
        print("--run-update-tests requires --plan-update-tests", file=sys.stderr)
        return 2
    if args.run_update_tests and not args.local_root:
        print("--run-update-tests requires --local-root", file=sys.stderr)
        return 2
    update_state_path = Path(args.state_file) if args.state_file else default_update_state_path()
    try:
        report = audit(args)
        if args.apply_governance_actions:
            attach_governance_actions(
                report,
                apply_governance_actions(report, args.org, token or "", args.community_rules_url),
            )
        elif args.plan_governance_actions:
            attach_governance_actions(
                report,
                governance_action_records(report, args.community_rules_url),
            )
        if args.apply_public_restore:
            attach_public_restore_actions(
                report,
                apply_public_restore_actions(report, args.org, token or ""),
            )
        elif args.plan_public_restore:
            attach_public_restore_actions(
                report,
                public_restore_action_records(report, args.org, token),
            )
        if args.report_stale_repos:
            attach_stale_repositories(report, stale_repository_records(report, args.stale_days))
        if args.apply_index_updates:
            local_root = Path(args.local_root).resolve() if args.local_root else None
            attach_index_apply_actions(
                report,
                apply_index_updates(report, local_root, args.python_bin, args.node_bin),
            )
            attach_index_update_actions(report, index_update_records(report, local_root))
        elif args.plan_index_updates:
            local_root = Path(args.local_root).resolve() if args.local_root else None
            attach_index_update_actions(report, index_update_records(report, local_root))
        update_state = None
        if args.plan_update_tests or args.write_state:
            update_state = load_update_state(update_state_path)
            ensure_update_heads(
                report,
                args.org,
                token,
                bool(args.repositories_json),
                update_head_names_needed(
                    report,
                    update_state,
                    args.mark_tested,
                    args.plan_update_tests,
                    args.write_state,
                ),
            )
        if args.plan_update_tests:
            attach_update_check_actions(
                report,
                update_check_records(
                    report,
                    update_state or {"repositories": {}},
                    args.org,
                    token,
                    bool(args.repositories_json),
                ),
                update_state_path,
            )
        if args.run_update_tests:
            local_root = Path(args.local_root).resolve() if args.local_root else None
            attach_test_run_results(
                report,
                run_update_tests(
                    report,
                    local_root,
                    args.test_repo,
                    args.python_bin,
                    args.test_timeout,
                ),
            )
        if args.write_state:
            next_state = build_update_state(
                update_state or {"repositories": {}},
                report,
                args.mark_tested,
            )
            write_update_state(update_state_path, next_state)
            report["state_write"] = {
                "status": "written",
                "path": str(update_state_path),
                "marked_repos": args.mark_tested,
            }
    except urllib.error.HTTPError as exc:
        print(
            f"GitHub API request failed: HTTP {exc.code} {exc.reason}. "
            "If this is rate limiting or private repository access, rerun with --token, "
            "GITHUB_TOKEN, or GH_TOKEN.",
            file=sys.stderr,
        )
        return 2
    except urllib.error.URLError as exc:
        print(f"GitHub API request failed: {exc.reason}", file=sys.stderr)
        return 2
    except ValueError as exc:
        print(str(exc), file=sys.stderr)
        return 2
    markdown = to_markdown(report)
    write_output(args.markdown, markdown)
    if args.json_output:
        write_output(args.json_output, json.dumps(report, ensure_ascii=False, indent=2) + "\n")
    if not args.markdown:
        print(markdown, end="")

    if args.fail_on_issues:
        if report["summary"]["repositories_with_failures"]:
            return 2
        if report["summary"]["repositories_with_warnings"]:
            return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
