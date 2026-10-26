"""Offline regression tests. All mutations use temporary fixtures; no service credentials are needed."""
from __future__ import annotations

import contextlib
import io
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import Mock, patch

import yaml

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
import draft_reviews as draft
import process_analysis as analysis
import process_rules as rules
import update
import weekly_summary as summary
import github_index


def mapping(**overrides):
    values = dict(decision="existing", method_id="grpo", scope_tag=None, new_method=None,
                  evidence="The option implements the cited objective.", confidence="high")
    return draft.Mapping(**(values | overrides))


def thread_code():
    return draft.ThreadCode(method="Example", proposer_says=None, outcome="open_no_reply",
                            reasons=[], quote=None, confidence="high", note="No maintainer replied.")


def response(payload=None, status=200):
    return Mock(status_code=status, json=Mock(return_value=payload), text="must not be logged")


def completion(value):
    return response({"choices": [{"finish_reason": "stop", "message": {"content": value.model_dump_json()}}]})


class MappingTests(unittest.TestCase):
    def test_preserves_every_other_mapping(self):
        cases = [
            'trl:\n  loss_type:\n    keep: grpo\n',
            'trl:\n  loss_type: {keep: grpo}\n',
            'trl:\n  loss_type: &options\n    keep: grpo\n',
            'trl:\n  "loss_type":\n    keep: grpo\n',
            '"trl":\n  loss_type:\n    keep: grpo\n',
            'trl: {loss_type: {keep: grpo}}\n',
            '# header\ntrl:\n  loss_type: # comment\n    keep: grpo\n# footer\nother:\n  opt: {x: grpo}\n',
            'trl:\n  loss_type:\n',
            'trl:\n  loss_type: null\n',
            'trl: null\n',
            'other: {opt: {x: grpo}}\n',
            'trl:\n  loss_type:\n    keep: grpo',  # no final newline
        ]
        for text in cases:
            with self.subTest(text=text):
                expected = yaml.safe_load(text)
                if expected.get("trl") is None:
                    expected["trl"] = {}
                if expected["trl"].get("loss_type") is None:
                    expected["trl"]["loss_type"] = {}
                expected["trl"]["loss_type"]["on"] = "grpo"
                result = draft.add_token(text, "trl", "loss_type", "on", "grpo")
                self.assertEqual(yaml.safe_load(result), expected)
                if "# header" in text:
                    self.assertIn("# header", result)
                    self.assertIn("# comment", result)
                    self.assertIn("# footer", result)

    def test_rejects_duplicate_keys_existing_tokens_and_alias_side_effects(self):
        for text in (
            "trl: {}\ntrl: {}\n",
            "trl:\n  loss_type: {new: grpo}\n",
            "trl:\n  loss_type: &shared {keep: grpo}\nother:\n  loss_type: *shared\n",
        ):
            with self.subTest(text=text), self.assertRaises(ValueError):
                draft.add_token(text, "trl", "loss_type", "new", "grpo")


class ResponseTests(unittest.TestCase):
    def test_bad_envelopes_retry_once(self):
        invalid = [None, [], {}, {"choices": []}, {"choices": [None]},
                   {"choices": [{"finish_reason": "stop", "message": {"content": []}}]},
                   {"choices": [{"finish_reason": "length", "message": {"content": "{}"}}]},
                   {"choices": [{"finish_reason": "stop", "message": {"content": "{}"}}]}]
        for payload in invalid:
            with self.subTest(payload=payload), patch.object(draft.requests, "post",
                    side_effect=[response(payload), completion(mapping())]) as post:
                self.assertEqual(draft.ask("rules", "evidence", draft.Mapping), mapping())
                self.assertEqual(post.call_count, 2)

    def test_non_json_and_invalid_twice(self):
        bad = response()
        bad.json.side_effect = ValueError("not JSON")
        with patch.object(draft.requests, "post", return_value=bad) as post:
            self.assertIsNone(draft.ask("", "", draft.Mapping))
            self.assertEqual(post.call_count, 2)

    def test_fatal_error_stops_and_does_not_echo_response(self):
        output = io.StringIO()
        with patch.object(draft.requests, "post", return_value=response(status=402)) as post:
            with contextlib.redirect_stdout(output), self.assertRaises(draft.StopDrafting) as error:
                draft.ask("", "", draft.Mapping)
        self.assertEqual(post.call_count, 1)
        self.assertNotIn("must not be logged", str(error.exception) + output.getvalue())


class ParticipantTests(unittest.TestCase):
    def test_role_at_each_reply_with_full_timestamp(self):
        prior = rules.build_prior_merger([
            {"framework": "trl", "merged_by": "alice", "merged": "2026-10-21T10:00:00Z"},
            {"framework": "trl", "merged_by": "copilot", "merged": "2026-10-20T10:00:00Z"},
        ])
        self.assertFalse(prior("trl", "alice", "2026-10-21T09:59:59Z"))
        self.assertFalse(prior("trl", "alice", "2026-10-21T10:00:00Z"))
        self.assertTrue(prior("trl", "alice", "2026-10-21T10:00:01Z"))
        self.assertTrue(prior("trl", "alice", "2026-10-21T21:00:00+10:00"))
        self.assertFalse(prior("trl", "copilot", "2026-10-21T11:00:00Z"))
        self.assertIs(analysis.build_prior_merger, draft.build_prior_merger)

    def test_transcript_roles_change_after_first_merge(self):
        issue = dict(user={"login": "proposer"}, state="open", title="Proposal",
                     created_at="2026-10-20T00:00:00Z", body="Context")
        comments = [dict(user={"login": "alice"}, created_at=t, body="reply") for t in
                    ["2026-10-21T09:00:00Z", "2026-10-21T11:00:00Z"]]
        prior = rules.build_prior_merger([
            {"framework": "trl", "merged_by": "alice", "merged": "2026-10-21T10:00:00Z"}])
        with patch.object(draft, "gh", return_value=issue), patch.object(draft, "gh_list", return_value=comments):
            text, _ = draft.thread_text("https://github.com/a/b/issues/1", prior, "trl")
        self.assertIn("09:00:00Z] alice (other)", text)
        self.assertIn("11:00:00Z] alice (maintainer)", text)

    def test_long_thread_is_never_silently_truncated(self):
        issue = dict(user={"login": "proposer"}, state="open", title="Proposal",
                     created_at="2026-10-20T00:00:00Z", body="x" * 9000)
        comments = [dict(user={"login": "alice"}, created_at="2026-10-21T00:00:00Z",
                         body="y" * 5000 + " Final decision: refused.")]
        with patch.object(draft, "gh", return_value=issue), patch.object(draft, "gh_list", return_value=comments):
            text, _ = draft.thread_text("https://github.com/a/b/issues/1", lambda *a: True, "trl")
            self.assertIn("Final decision: refused.", text)
            self.assertIn("x" * 9000, text)
            comments[0]["body"] = "y" * 60000 + " Final decision: refused."
            with self.assertRaises(draft.IncompleteThread):
                draft.thread_text("https://github.com/a/b/issues/1", lambda *a: True, "trl")

    def test_unread_discussion_pages_are_rejected(self):
        for comments in [
            {"pageInfo": {"hasNextPage": True}, "nodes": []},
            {"pageInfo": {"hasNextPage": False}, "nodes": [
                {"replies": {"pageInfo": {"hasNextPage": True}, "nodes": []}}]},
        ]:
            payload = {"data": {"repository": {"discussion": {"comments": comments}}}}
            with patch.object(draft, "gh", return_value=payload), self.assertRaises(draft.IncompleteThread):
                draft.thread_text("https://github.com/a/b/discussions/1", lambda *a: False, "trl")


class FixtureTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.gen = self.root / "data/generated"
        for path in ("config", "data/generated/process", "data/generated/github", ".cache"):
            (self.root / path).mkdir(parents=True, exist_ok=True)
        self.journal = draft.DraftJournal(self.root / ".cache/drafts.json")
        self.write("config/token_map.yaml", "trl:\n  loss_type: {keep: grpo}\n")
        self.write("data/methods.yaml", yaml.safe_dump([
            dict(id="grpo", name="GRPO", source={"arxiv": "2501.00001"}, family="objective", symptoms=[]),
            dict(id="foo", name="Foo", source={"arxiv": "2501.00002"}, family="objective", symptoms=[]),
        ]))
        self.write("data/symptoms.yaml", "[]")
        self.write("data/generated/unmapped.json", json.dumps({"tokens": {}}))
        for module, attrs in ((draft, {"ROOT": self.root, "GEN": self.gen, "DRAFTS": self.journal.path,
                                     "REPOS": self.root / ".cache/repos"}),
                              (update, {"ROOT": self.root}), (summary, {"ROOT": self.root, "GEN": self.gen})):
            for key, value in attrs.items():
                p = patch.object(module, key, value)
                p.start()
                self.addCleanup(p.stop)
        draft.STOPPED.clear()

    def write(self, relative, text):
        (self.root / relative).write_text(text, encoding="utf-8")

    def populate(self, options=0, threads=0):
        self.write("data/generated/unmapped.json", json.dumps({"tokens": {
            "trl": {"loss_type": [f"option_{i}" for i in range(options)]}}}))
        self.write("data/generated/process/uncoded_threads.jsonl", "".join(
            json.dumps(dict(arxiv="2501.00002", framework="trl", number=i,
                            date="2026-10-21T00:00:00Z", url=f"https://github.com/a/b/issues/{i}")) + "\n"
            for i in range(threads)))

    def test_shared_budget_caps_both_kinds_including_invalid_attempts(self):
        self.populate(options=7, threads=13)
        budget = draft.Budget()
        with patch.object(draft, "ask", side_effect=lambda rules, content, schema:
                          mapping() if schema is draft.Mapping else thread_code()) as ask:
            with patch.object(draft.Threads, "prompt", return_value=("complete thread", "issues")):
                draft.draft_options(False, budget, self.journal)
                draft.draft_threads(False, budget, self.journal)
        self.assertEqual(ask.call_count, 12)
        self.assertEqual(len(self.journal.rows), 12)
        self.assertEqual(len(draft.jl(self.gen / "process/uncoded_threads.jsonl")), 8)

    def test_total_http_budget_is_24_even_if_every_response_is_invalid(self):
        self.populate(options=13, threads=13)
        budget = draft.Budget()
        with patch.object(draft.requests, "post", return_value=response({"choices": []})) as post:
            with patch.object(draft.Threads, "prompt", return_value=("thread", "issues")):
                draft.draft_options(False, budget, self.journal)
                draft.draft_threads(False, budget, self.journal)
        self.assertEqual(post.call_count, 24)
        self.assertEqual(self.journal.rows, [])

    def test_journal_survives_unexpected_failure_and_partial_write(self):
        self.populate(options=2)
        with patch.object(draft, "ask", side_effect=[mapping(), RuntimeError("unexpected")]):
            with self.assertRaises(RuntimeError):
                draft.draft_options(False, journal=self.journal)
        self.assertEqual(json.loads(self.journal.path.read_text())[0]["state"], "applied")
        with self.assertRaises(OSError):
            self.journal.apply({"item": "second"}, Mock(side_effect=OSError("disk error")))
        self.assertEqual(json.loads(self.journal.path.read_text())[1]["state"], "pending")

    def test_fatal_error_preserves_first_draft_and_stops_threads(self):
        self.populate(options=2, threads=2)
        with patch.object(draft, "ask", side_effect=[mapping(), draft.StopDrafting("HTTP 402")]) as ask:
            draft.draft_options(False, journal=self.journal)
            self.assertEqual(draft.draft_threads(False, journal=self.journal), [])
        self.assertEqual(ask.call_count, 2)
        self.assertEqual(len(json.loads(self.journal.path.read_text())), 1)

    def test_citation_without_proposal_goes_to_the_reference_list(self):
        self.populate(threads=1)
        code = draft.ThreadCode(method="Example", proposer_says=None, outcome="reference", reasons=[],
                                quote=None, confidence="low",
                                note="The pull request fixes numerical precision and cites the paper's appendix.")
        with patch.object(draft, "ask", return_value=code):
            with patch.object(draft.Threads, "prompt", return_value=("complete thread", "pull")):
                drafts = draft.draft_threads(False, journal=self.journal)
        self.assertEqual(draft.jl(self.gen / "process/attempts_coded.jsonl"), [])
        self.assertEqual(draft.jl(self.gen / "process/threads_reference_only.jsonl"), [
            {"framework": "trl", "kind": "pr", "number": 0, "arxiv": "2501.00002", "category": "reference",
             "coder": "draft"}])
        self.assertEqual(drafts[0]["draft"], "reference only, not a proposal")
        self.assertEqual(draft.jl(self.gen / "process/uncoded_threads.jsonl"), [])

    def test_incomplete_thread_stays_pending_and_makes_no_model_call(self):
        self.populate(threads=1)
        with patch.object(draft.Threads, "prompt", side_effect=draft.IncompleteThread("unread pages")):
            with patch.object(draft, "ask") as ask:
                draft.draft_threads(False, journal=self.journal)
        ask.assert_not_called()
        self.assertEqual(draft.jl(self.gen / "process/uncoded_threads.jsonl")[0]["draft_blocked"], "unread pages")

    def test_new_method_writes_catalog_and_mapping_with_journal(self):
        self.populate(options=1)
        new = draft.NewMethod(id="new_method", name="New method", arxiv="2601.00001", family="objective", symptoms=[])
        with patch.object(draft, "ask", return_value=mapping(decision="new", method_id=None, new_method=new)):
            draft.draft_options(False, journal=self.journal)
        self.assertEqual(yaml.safe_load((self.root / "config/token_map.yaml").read_text())["trl"]["loss_type"]["option_0"],
                         "new_method")
        self.assertEqual(yaml.safe_load((self.root / "data/methods.yaml").read_text())[-1]["id"], "new_method")
        self.assertTrue(json.loads(self.journal.path.read_text())[0]["new_method"])

    def test_rebuild_order_and_snapshot_for_mapping_only_run(self):
        self.populate(options=1)
        events = []
        with patch.dict(os.environ, {"LLM_API_KEY": "offline-fixture"}), patch.object(sys, "argv",
                ["draft_reviews.py", "--snapshot", "2026-10-21"]):
            with patch.object(draft, "ask", return_value=mapping()), patch.object(update, "run",
                    side_effect=lambda *a: events.append(a)), patch.object(update, "list_uncoded",
                    side_effect=lambda: events.append(("uncoded",))):
                self.assertEqual(draft.main(), 0)
        self.assertEqual(events, [
            ("collectors/frameworks.py",), ("tools/impl_links.py",), ("tools/summary.py",),
            ("tools/adoption_rate.py",), ("uncoded",),
            ("tools/process_analysis.py", "--build-facts", "--snapshot", "2026-10-21"), ("uncoded",),
            ("tools/frameworks_doc.py",), ("tools/framework_profiles.py",),
            ("tools/site_data.py",), ("tools/site_hero.py",)])

    def test_updated_pool_removes_newly_included_proposals(self):
        self.write("data/generated/pool_adoption.jsonl", json.dumps(
            {"arxiv": "2501.00002", "strict_general": True, "adopted": True}) + "\n")
        self.write("data/generated/github/mentions.jsonl", json.dumps(dict(arxiv="2501.00002",
            framework="trl", number=1, tier="link", place="opening", kind="issue", date="2026-10-21", url="url")) + "\n")
        update.list_uncoded()
        self.assertEqual(draft.jl(self.gen / "process/uncoded_threads.jsonl"), [])

    def test_rebuilt_facts_include_newly_coded_thread(self):
        cache = self.root / ".cache/github/a__b/issue_comments"
        cache.mkdir(parents=True)
        (cache / "0001.json").write_text(json.dumps([dict(issue_url="https://api.github.com/repos/a/b/issues/1",
            user={"login": "alice"}, created_at="2026-10-21T00:00:00Z")]))
        self.write("data/generated/github/threads.jsonl", json.dumps(dict(framework="trl", number=1, user="proposer")) + "\n")
        with patch.multiple(analysis, GEN=self.gen, OUT=self.gen / "process", CACHE=self.root / ".cache/github",
                FACTS=self.gen / "github/pr_facts.jsonl", REPLIES=self.gen / "process/attempt_replies.jsonl",
                REPOS={"trl": "a/b"}):
            analysis.build_facts()
            self.assertEqual(draft.jl(analysis.REPLIES), [])
            self.write("data/generated/process/attempts_coded.jsonl", json.dumps(dict(framework="trl", number=1)) + "\n")
            analysis.build_facts()
            self.assertEqual(draft.jl(analysis.REPLIES)[0]["replies"][0]["user"], "alice")

    def test_explicit_snapshot_controls_replies_and_open_pr_age(self):
        self.write("data/generated/adoption.json", "[]")
        self.write("data/generated/process/attempts_coded.jsonl", json.dumps(dict(
            arxiv="2501.00002", framework="trl", number=1, type="pr", outcome="open_engaged", reasons=[])) + "\n")
        self.write("data/generated/process/attempt_replies.jsonl", json.dumps(dict(
            framework="trl", number=1, proposer="proposer", replies=[
                {"user": "alice", "at": "2026-10-20T11:00:00Z", "kind": "comment"}])) + "\n")
        self.write("data/generated/github/merged_prs.jsonl", json.dumps(dict(
            framework="trl", merged_by="alice", merged="2026-10-20T10:00:00Z")) + "\n")
        det = {"pull": dict(created_at="2026-10-18T00:00:00Z", closed_at=None, state="open"), "files": []}
        with patch.multiple(analysis, ROOT=self.root, GEN=self.gen, OUT=self.gen / "process",
                            REPLIES=self.gen / "process/attempt_replies.jsonl"):
            with patch.object(analysis, "pr_detail", return_value=det), patch.object(github_index,
                    "load_papers", return_value=({}, {}, {})), contextlib.redirect_stdout(io.StringIO()):
                analysis.main()
                frozen = json.loads((analysis.OUT / "summary.json").read_text())
                analysis.main("2026-10-21")
                live = json.loads((analysis.OUT / "summary.json").read_text())
        self.assertEqual(frozen["attempts_any_human_reply"], 0)
        self.assertEqual(live["attempts_any_human_reply"], 1)
        self.assertEqual(frozen["open_attempt_median_age"], 0)
        self.assertEqual(live["open_attempt_median_age"], 3)

    def test_smoke_test_exercises_new_method_without_writing(self):
        self.write("config/token_map.yaml", yaml.safe_dump({"trl": {"loss_type": {
            "a": "grpo", "b": "foo", "c": "~config", "d": "~systems"}}}))
        self.write("data/generated/framework_events.jsonl", "".join(json.dumps(dict(
            event="added", date="2026-10-01", framework="trl", surface="loss_type", token=t, sha="a" * 40))
            + "\n" for t in "abcd"))
        responses = [mapping(), mapping(method_id="foo")]
        responses += [mapping(decision="new", method_id=None, new_method=draft.NewMethod(
            id="new_" + m, name=m, arxiv=a, family="objective", symptoms=[]))
            for m, a in [("grpo", "2501.00001"), ("foo", "2501.00002")]]
        responses += [mapping(decision="out_of_scope", method_id=None, scope_tag=t) for t in ["~config", "~systems"]]
        before = {p: p.read_bytes() for p in self.root.rglob("*") if p.is_file()}
        output = io.StringIO()
        with patch.object(draft, "ask", side_effect=responses) as ask, patch.dict(os.environ, {"GITHUB_STEP_SUMMARY": ""}):
            with contextlib.redirect_stdout(output):
                draft.selftest(n_threads=0)
        self.assertEqual(ask.call_count, 6)
        self.assertNotIn("- grpo:", ask.call_args_list[2].args[1])
        self.assertIn("6 of 6", output.getvalue())
        self.assertIn("smoke test", output.getvalue())
        self.assertEqual(before, {p: p.read_bytes() for p in self.root.rglob("*") if p.is_file()})

    def test_merge_guard_defaults_to_manual_and_blocks_failures(self):
        cases = [
            ([], 0, [], {}, [], False),
            (["--auto-merge-enabled", "true"], 0, [], {}, [], True),
            (["--auto-merge-enabled", "true", "--draft-outcome", "failure"], 0, [], {}, [], False),
            (["--auto-merge-enabled", "true", "--refresh-rc", "1"], 0, [], {}, [], False),
            (["--auto-merge-enabled", "true"], 1, [], {}, [], False),
            (["--auto-merge-enabled", "true"], 0, [dict(item="x", draft="x", evidence="", confidence="low", state="pending")], {}, [], False),
            (["--auto-merge-enabled", "true"], 0, [], {"trl": {"loss_type": ["x"]}}, [], False),
            (["--auto-merge-enabled", "true"], 0, [], {}, [dict(framework="trl", number=1, url="url", arxiv="2501.00002")], False),
        ]
        out = self.root / "outputs"
        for args, validation, drafts, tokens, uncoded, expected in cases:
            with self.subTest(args=args, validation=validation, expected=expected):
                self.journal.path.write_text(json.dumps(drafts))
                self.write("data/generated/unmapped.json", json.dumps({"tokens": tokens}))
                self.write("data/generated/process/uncoded_threads.jsonl", "".join(json.dumps(x) + "\n" for x in uncoded))
                out.write_text("")
                with patch.object(sys, "argv", ["weekly_summary.py", "--out", "summary.md"] + args):
                    with patch.object(summary, "at_head", return_value=None), patch.object(summary.subprocess,
                            "run", return_value=Mock(returncode=validation)), patch.dict(os.environ, {"GITHUB_OUTPUT": str(out)}):
                        summary.main()
                self.assertEqual(out.read_text(), f"clean={str(expected).lower()}\n")


class WorkflowTests(unittest.TestCase):
    def test_credentials_pending_guard_failure_reporting_and_rollout(self):
        weekly = yaml.safe_load((ROOT / ".github/workflows/update.yml").read_text())
        smoke = yaml.safe_load((ROOT / ".github/workflows/draft-selftest.yml").read_text())
        for workflow in (weekly, smoke):
            steps = next(iter(workflow["jobs"].values()))["steps"]
            checkout = next(s for s in steps if s.get("uses", "").startswith("actions/checkout"))
            self.assertIs(checkout["with"]["persist-credentials"], False)
        steps = weekly["jobs"]["update"]["steps"]
        pending = next(s for s in steps if s.get("id") == "pending")
        self.assertNotIn("--label", pending["run"])
        report = next(s for s in steps if s.get("name") == "Report a failed run")
        self.assertNotIn("pull-request-number == ''", report["if"])
        merge = next(s for s in steps if s.get("name") == "Merge a clean refresh")
        self.assertIn("vars.WEEKLY_AUTO_MERGE == 'true'", merge["if"])
        for step in steps:
            if step.get("id") in ("refresh", "draft"):
                self.assertIn('--snapshot "${{ steps.collection.outputs.snapshot }}"', step["run"])

    def test_default_snapshot_remains_v1(self):
        self.assertEqual(analysis.SNAPSHOT, "2026-10-18")
        self.assertEqual(analysis.main.__defaults__, ("2026-10-18",))
        self.assertEqual(rules.snapshot_date("2026-10-21"), "2026-10-21")
        with self.assertRaises(Exception):
            rules.snapshot_date("today")


if __name__ == "__main__":
    unittest.main()
