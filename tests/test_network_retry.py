"""A dropped connection makes the GitHub and arXiv collectors retry instead of stopping the weekly update."""
from __future__ import annotations

import sys
import unittest
from pathlib import Path
from unittest import mock

import requests

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "collectors"))

import github_threads  # noqa: E402
import papers  # noqa: E402


def response(status: int, body: str = "[]", headers: dict | None = None) -> requests.Response:
    r = requests.Response()
    r.status_code = status
    r._content = body.encode("utf-8")
    r.headers.update(headers or {})
    return r


class GitHubClientRetryTests(unittest.TestCase):
    def setUp(self):
        patcher = mock.patch.object(github_threads, "token", return_value="test-token")
        patcher.start()
        self.addCleanup(patcher.stop)
        sleep = mock.patch.object(github_threads.time, "sleep")
        sleep.start()
        self.addCleanup(sleep.stop)

    def test_get_retries_a_body_cut_off_mid_stream(self):
        cli = github_threads.Client()
        ok = response(200, "[1]", {"X-RateLimit-Remaining": "4000"})
        with mock.patch.object(cli.s, "request",
                               side_effect=[requests.exceptions.ChunkedEncodingError("cut"), ok]) as req:
            r = cli.get("https://api.github.com/repos/o/r/issues")
        self.assertIs(r, ok)
        self.assertEqual(req.call_count, 2)

    def test_graphql_retries_a_dropped_connection(self):
        cli = github_threads.Client()
        ok = response(200, '{"data": {"repository": null}}')
        with mock.patch.object(cli.s, "request",
                               side_effect=[requests.exceptions.ConnectionError("reset"), ok]):
            self.assertEqual(cli.graphql("query{}", {}), {"repository": None})

    def test_get_gives_up_after_repeated_failures(self):
        cli = github_threads.Client()
        with mock.patch.object(cli.s, "request", side_effect=requests.exceptions.Timeout("slow")):
            with self.assertRaises(RuntimeError):
                cli.get("https://api.github.com/repos/o/r/issues")


class ArxivRetryTests(unittest.TestCase):
    def test_fetch_retries_timeouts_and_server_errors(self):
        feed = '<feed xmlns="http://www.w3.org/2005/Atom"></feed>'
        answers = [requests.exceptions.Timeout("slow"), response(503), response(200, feed)]
        with mock.patch.object(papers.requests, "get", side_effect=answers) as get, \
                mock.patch.object(papers.time, "sleep"):
            self.assertEqual(papers.fetch({"id_list": "2501.00001"}), [])
        self.assertEqual(get.call_count, 3)


if __name__ == "__main__":
    unittest.main()
