from __future__ import annotations

import importlib.util
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "audit_quantskills_repos.py"
spec = importlib.util.spec_from_file_location("audit_quantskills_repos", SCRIPT)
audit = importlib.util.module_from_spec(spec)
assert spec and spec.loader
spec.loader.exec_module(audit)


class AuditQuantskillsReposTests(unittest.TestCase):
    def test_update_plan_skips_head_fetch_for_unaccepted_repos(self):
        report = {
            "repositories": [
                {"name": "skill-a"},
                {"name": "skill-b"},
            ]
        }
        state = {"repositories": {}}

        needed = audit.update_head_names_needed(
            report,
            state,
            marked_repos=[],
            plan_update_tests=True,
            write_state=False,
        )

        self.assertEqual(needed, set())

    def test_update_plan_fetches_current_heads_for_accepted_repos(self):
        report = {
            "repositories": [
                {"name": "skill-a"},
                {"name": "skill-b"},
                {"name": "skill-c"},
            ]
        }
        state = {
            "repositories": {
                "skill-a": {"accepted_head_sha": "a"},
                "skill-b": {"accepted_fingerprint": "b"},
                "skill-c": {},
            }
        }

        needed = audit.update_head_names_needed(
            report,
            state,
            marked_repos=[],
            plan_update_tests=True,
            write_state=False,
        )

        self.assertEqual(needed, {"skill-a", "skill-b"})

    def test_governance_actions_cover_community_rule_issue_types(self):
        report = {
            "repositories": [
                {
                    "name": "skill-bad-name",
                    "inferred_type": "skill",
                    "issues": [
                        {"code": "english-readme", "severity": "fail", "message": "missing"},
                        {"code": "license", "severity": "fail", "message": "missing"},
                        {"code": "runtime-adapter", "severity": "warn", "message": "missing"},
                    ],
                },
                {
                    "name": "bad-name",
                    "inferred_type": "skill",
                    "issues": [
                        {"code": "repository-prefix", "severity": "fail", "message": "bad name"},
                    ],
                },
                {
                    "name": "skill-missing-declaration",
                    "inferred_type": "skill",
                    "issues": [
                        {"code": "skill-declaration", "severity": "fail", "message": "missing"},
                    ],
                },
            ]
        }

        actions = audit.governance_action_records(report, audit.COMMUNITY_RULES_URL)

        by_repo = {action["repo"]: action for action in actions}
        self.assertEqual(by_repo["skill-bad-name"]["visibility_action"], "no-visibility-change")
        self.assertEqual(
            by_repo["skill-bad-name"]["issue_codes"],
            ["english-readme", "license", "runtime-adapter"],
        )
        self.assertEqual(by_repo["bad-name"]["visibility_action"], "set-private")
        self.assertEqual(by_repo["bad-name"]["issue_codes"], ["repository-prefix"])
        self.assertEqual(by_repo["bad-name"]["reasons"][0]["message"], "bad name")
        self.assertEqual(
            by_repo["skill-missing-declaration"]["visibility_action"],
            "set-private",
        )
        self.assertEqual(
            by_repo["skill-missing-declaration"]["issue_codes"],
            ["skill-declaration"],
        )

    def test_naming_governance_actions_set_private(self):
        for issue_code in audit.NAMING_REMEDIATION_CODES:
            with self.subTest(issue_code=issue_code):
                report = {
                    "repositories": [
                        {
                            "name": f"repo-{issue_code}",
                            "inferred_type": "skill",
                            "issues": [
                                {"code": issue_code, "severity": "fail", "message": "bad name"},
                            ],
                        }
                    ]
                }

                actions = audit.governance_action_records(report, audit.COMMUNITY_RULES_URL)

                self.assertEqual(actions[0]["visibility_action"], "set-private")
                self.assertEqual(actions[0]["issue_codes"], [issue_code])

    def test_runtime_adapter_issues_name_missing_runtime(self):
        issues = audit.runtime_adapter_issues({"SKILL.md", "agents/cursor-rule.mdc"}, None)
        messages = [issue["message"] for issue in issues]

        self.assertIn("Skill repository is missing hermes runtime adapter entrypoint.", messages)
        self.assertIn("Skill repository is missing openclaw runtime adapter entrypoint.", messages)
        self.assertNotIn("Skill repository is missing codex runtime adapter entrypoint.", messages)
        self.assertNotIn("Skill repository is missing cursor runtime adapter entrypoint.", messages)

    def test_content_policy_flags_missing_gpl_metadata(self):
        from tempfile import TemporaryDirectory

        with TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "SKILL.md").write_text("---\nlicense: GPL-3.0\n---\n# Skill\n", encoding="utf-8")
            issues = audit.content_policy_issues(root, {"SKILL.md"}, "skill")

        self.assertIn("license-metadata", {issue["code"] for issue in issues})

    def test_content_policy_ignores_negated_overpromise_examples(self):
        from tempfile import TemporaryDirectory

        with TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "SKILL.md").write_text(
                "---\nlicense: GPL-3.0-only\n---\nDo not imply guaranteed returns. 不自动代表官方验证或背书。",
                encoding="utf-8",
            )
            issues = audit.content_policy_issues(
                root,
                {"SKILL.md"},
                "skill",
                {"name": "skill-governance-auditor", "description": "audit tooling"},
            )

        self.assertNotIn("overpromise", {issue["code"] for issue in issues})
        self.assertNotIn("risk-disclosure", {issue["code"] for issue in issues})

    def test_detect_test_commands_prefers_unittest_for_tests_dir(self):
        from tempfile import TemporaryDirectory

        with TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "tests").mkdir()
            commands = audit.detect_test_commands(root, "python")

        self.assertIn(["python", "-m", "unittest", "discover", "-s", "tests"], commands)

    def test_homepage_sync_covers_github_org_profile(self):
        from tempfile import TemporaryDirectory

        with TemporaryDirectory() as directory:
            root = Path(directory)
            profile = root / ".github" / "profile"
            profile.mkdir(parents=True)
            readme = profile / "README.md"
            readme.write_text(
                "\n".join(
                    [
                        "# QUANTSKILLS",
                        "## 🗂️ 社区技能仓库一览",
                        "old",
                        "## 🤖 社区 Agent 仓库一览",
                        "old",
                        "## 🚀 如何参与",
                        "middle",
                        "## 🗂️ Community Skill Repositories",
                        "old",
                        "## 🤖 Community Agent Repositories",
                        "old",
                        "## 🚀 How to Participate",
                        "tail",
                    ]
                ),
                encoding="utf-8",
            )
            registry = root / "registry"
            registry.mkdir()
            (registry / "registry.json").write_text(
                '[{"name":"skill-a","summary_zh":"中文摘要","summary_en":"English summary"}]',
                encoding="utf-8",
            )
            report = {
                "org": "quantskills",
                "repositories": [
                    {
                        "name": "skill-a",
                        "private": False,
                        "archived": False,
                        "disabled": False,
                        "description": "fallback",
                    },
                    {
                        "name": "agent-a",
                        "private": False,
                        "archived": False,
                        "disabled": False,
                        "description": "agent summary",
                    },
                ],
            }

            result = audit.sync_homepage_profile(report, root)

            text = readme.read_text(encoding="utf-8")
            self.assertEqual(result["status"], "updated")
            self.assertIn("https://github.com/quantskills/skill-a", text)
            self.assertIn("https://github.com/quantskills/agent-a", text)
            self.assertIn("中文摘要", text)
            self.assertIn("English summary", text)

    def test_quantskills_index_detects_private_unprefixed_extra(self):
        from tempfile import TemporaryDirectory

        with TemporaryDirectory() as directory:
            root = Path(directory)
            (root / ".github" / "profile").mkdir(parents=True)
            (root / ".github" / "profile" / "README.md").write_text(
                "https://github.com/quantskills/skill-a\n",
                encoding="utf-8",
            )
            (root / "registry").mkdir()
            (root / "registry" / "registry.json").write_text(
                '[{"name":"skill-a"}]',
                encoding="utf-8",
            )
            (root / "quantskills" / "data").mkdir(parents=True)
            (root / "quantskills" / "data" / "curation.json").write_text(
                '{"denylist":["deleted-repo"]}',
                encoding="utf-8",
            )
            (root / "quantskills" / "README.md").write_text(
                "\n".join(
                    [
                        "https://github.com/quantskills/skill-a",
                        "https://github.com/quantskills/metadata-repo",
                        "https://github.com/quantskills/news-sentiment-analyst",
                        "https://github.com/quantskills/deleted-repo",
                    ]
                ),
                encoding="utf-8",
            )
            report = {
                "org": "quantskills",
                "repositories": [
                    {"name": "skill-a", "private": False, "archived": False, "disabled": False},
                    {"name": "metadata-repo", "private": False, "archived": False, "disabled": False},
                    {
                        "name": "news-sentiment-analyst",
                        "private": True,
                        "archived": False,
                        "disabled": False,
                    },
                    {"name": "deleted-repo", "private": False, "archived": False, "disabled": False},
                ],
            }

            actions = audit.index_update_records(report, root)

        by_target = {action["target"]: action for action in actions}
        self.assertIn("quantskills", by_target)
        self.assertEqual(by_target["quantskills"]["missing"], [])
        self.assertEqual(
            by_target["quantskills"]["extra"],
            ["deleted-repo", "news-sentiment-analyst"],
        )
        self.assertEqual(by_target["quantskills"]["ignored_present"], ["deleted-repo"])

    def test_public_restore_closes_recorded_remediation_issue(self):
        calls = []

        def fake_github_request(method, url, token, data=None):
            calls.append((method, url, data))
            if method == "GET" and url.endswith("/issues?state=open&per_page=100"):
                return [
                    {
                        "number": 1,
                        "title": audit.COMMUNITY_REMEDIATION_TITLE_ZH,
                        "html_url": "https://github.com/quantskills/agent-a/issues/1",
                    }
                ]
            if method == "GET":
                return {"private": True}
            if method == "PATCH" and url.endswith("/issues/1"):
                return {"number": 1, "html_url": "https://github.com/quantskills/agent-a/issues/1"}
            return {}

        original = audit.github_request
        audit.github_request = fake_github_request
        try:
            report = {
                "repositories": [
                    {
                        "name": "agent-a",
                        "inferred_type": "agent",
                        "private": True,
                        "visibility": "private",
                        "archived": False,
                        "disabled": False,
                        "issues": [],
                    }
                ]
            }

            actions = audit.apply_public_restore_actions(report, "quantskills", "token")
        finally:
            audit.github_request = original

        self.assertEqual(actions[0]["visibility_action"], "changed-to-public")
        self.assertEqual(actions[0]["issue_action"], "commented-and-closed #1")
        self.assertTrue(any(call[0] == "POST" and call[1].endswith("/issues/1/comments") for call in calls))

    def test_governance_apply_closes_resolved_public_remediation_issue(self):
        calls = []

        def fake_github_request(method, url, token, data=None):
            calls.append((method, url, data))
            if method == "GET" and url.endswith("/issues?state=open&per_page=100"):
                return [
                    {
                        "number": 2,
                        "title": audit.COMMUNITY_REMEDIATION_TITLE_ZH,
                        "html_url": "https://github.com/quantskills/skill-a/issues/2",
                    }
                ]
            if method == "PATCH" and url.endswith("/issues/2"):
                return {"number": 2, "html_url": "https://github.com/quantskills/skill-a/issues/2"}
            return {}

        original = audit.github_request
        audit.github_request = fake_github_request
        try:
            report = {
                "repositories": [
                    {
                        "name": "skill-a",
                        "inferred_type": "skill",
                        "private": False,
                        "visibility": "public",
                        "issues": [],
                    }
                ]
            }

            actions = audit.apply_governance_actions(report, "quantskills", "token", audit.COMMUNITY_RULES_URL)
        finally:
            audit.github_request = original

        self.assertEqual(actions[0]["repo"], "skill-a")
        self.assertEqual(actions[0]["issue_action"], "commented-and-closed #2")
        self.assertTrue(any(call[0] == "POST" and call[1].endswith("/issues/2/comments") for call in calls))

    def test_quantskills_curation_sync_adds_registry_factor_category(self):
        import json
        from tempfile import TemporaryDirectory

        with TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "registry").mkdir()
            (root / "registry" / "registry.json").write_text(
                json.dumps(
                    [
                        {
                            "name": "skill-factor-optimize",
                            "category": "factor",
                            "tags": ["factor-optimize"],
                        }
                    ]
                ),
                encoding="utf-8",
            )
            (root / "quantskills" / "data").mkdir(parents=True)
            curation = root / "quantskills" / "data" / "curation.json"
            curation.write_text(
                json.dumps({"org": "quantskills", "denylist": [], "infra": [], "categoryOverride": {}}),
                encoding="utf-8",
            )

            result = audit.sync_quantskills_curation_from_registry(root)

            payload = json.loads(curation.read_text(encoding="utf-8"))
            self.assertEqual(result["status"], "updated")
            self.assertEqual(payload["categoryOverride"]["skill-factor-optimize"], "02")

    def test_quantskills_curation_sync_infers_public_skill_and_agent_categories(self):
        import json
        from tempfile import TemporaryDirectory

        with TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "registry").mkdir()
            (root / "registry" / "registry.json").write_text(
                json.dumps(
                    [
                        {
                            "name": "skill-alpha-a06-hotmoney-reversal",
                            "category": "uncategorized",
                            "description": "Alpha factor from Dragon-Tiger hotmoney reversal signals.",
                        }
                    ]
                ),
                encoding="utf-8",
            )
            (root / "quantskills" / "data").mkdir(parents=True)
            curation = root / "quantskills" / "data" / "curation.json"
            curation.write_text(
                json.dumps({"org": "quantskills", "denylist": [], "infra": [], "categoryOverride": {}}),
                encoding="utf-8",
            )
            report = {
                "repositories": [
                    {
                        "name": "skill-build-b10-factor-evaluation",
                        "description": "Factor evaluation toolkit with IC/IR and stratified backtesting.",
                        "private": False,
                        "archived": False,
                        "disabled": False,
                    },
                    {
                        "name": "agent-factor-reviewer",
                        "description": "Agent for factor review workflows.",
                        "private": False,
                        "archived": False,
                        "disabled": False,
                    },
                    {
                        "name": "agent-private-reviewer",
                        "description": "Private agent should not be listed.",
                        "private": True,
                        "archived": False,
                        "disabled": False,
                    },
                ]
            }

            result = audit.sync_quantskills_curation_from_registry(root, report)

            payload = json.loads(curation.read_text(encoding="utf-8"))
            self.assertEqual(result["status"], "updated")
            self.assertEqual(payload["categoryOverride"]["skill-alpha-a06-hotmoney-reversal"], "02")
            self.assertEqual(payload["categoryOverride"]["skill-build-b10-factor-evaluation"], "02")
            self.assertEqual(payload["categoryOverride"]["agent-factor-reviewer"], "09")
            self.assertNotIn("agent-private-reviewer", payload["categoryOverride"])

    def test_skill_docs_do_not_contain_common_mojibake_tokens(self):
        mojibake_tokens = ["�", "绠€", "鎵", "馃"]
        for relative in ["SKILL.md", "README.md", "README.en.md", "skill.yml"]:
            text = (ROOT / relative).read_text(encoding="utf-8")
            self.assertFalse(any(token in text for token in mojibake_tokens), relative)


if __name__ == "__main__":
    unittest.main()
