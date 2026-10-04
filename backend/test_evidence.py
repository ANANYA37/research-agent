import ast
import asyncio
import json
import logging
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest.mock import AsyncMock, Mock, patch

from evidence import analyze_evidence, prepare_evidence, validate_review

CLAIM = "Solar generation increased during the study period."
QUOTE = "Solar generation increased by twenty percent during the study period."
ITEM = {"report": CLAIM, "sources": [{"title": "Study", "url": "https://example.org/study", "snippet": QUOTE}]}


def candidate(entries=None):
    return {"claims": [{"claim": CLAIM, "explanation": "The saved study describes an increase.",
                        "evidence": entries if entries is not None else [{"source_id": 1, "quote": QUOTE, "relation": "supports"}],
                        "gaps": []}]}


class GroundingTests(unittest.TestCase):
    def test_support_uses_saved_source_metadata(self):
        payload = candidate()
        payload["claims"][0]["evidence"][0]["url"] = "https://invented.invalid"
        claim = validate_review(payload, prepare_evidence(ITEM))["claims"][0]
        self.assertEqual(claim["status"], "supported")
        self.assertEqual(claim["evidence"][0]["url"], ITEM["sources"][0]["url"])

    def test_invented_quotes_or_source_ids_cannot_support_claim(self):
        for entry in [{"source_id": 1, "quote": "This invented evidence never appeared in the saved article.", "relation": "supports"},
                      {"source_id": 99, "quote": QUOTE, "relation": "supports"},
                      {"source_id": True, "quote": QUOTE, "relation": "supports"}]:
            result = validate_review(candidate([entry]), prepare_evidence(ITEM))["claims"][0]
            self.assertEqual(result["status"], "insufficient")
            self.assertTrue(result["gaps"])

    def test_claim_must_appear_in_report(self):
        payload = candidate()
        payload["claims"][0]["claim"] = "A completely fabricated statement about nuclear power."
        with self.assertRaises(ValueError):
            validate_review(payload, prepare_evidence(ITEM))

    def test_conflicting_evidence_is_mixed(self):
        result = validate_review(candidate([{"source_id": 1, "quote": QUOTE, "relation": "contradicts"}]), prepare_evidence(ITEM))
        self.assertEqual(result["claims"][0]["status"], "mixed")

    def test_unsafe_urls_are_removed_and_context_is_bounded(self):
        item = {"report": "x" * 20000, "sources": [{"url": "javascript:alert(1)", "snippet": "x" * 3000}] * 30}
        context = prepare_evidence(item)
        self.assertEqual(len(context["sources"]), 24)
        self.assertEqual(len(context["report"]), 18000)
        self.assertEqual(context["sources"][0]["url"], "")
        self.assertEqual(len(context["sources"][0]["snippet"]), 2000)


class AnalysisTests(unittest.IsolatedAsyncioTestCase):
    async def test_model_json_is_validated(self):
        model = SimpleNamespace(ainvoke=AsyncMock(return_value=SimpleNamespace(content=json.dumps(candidate()))))
        result = await analyze_evidence(ITEM, model)
        self.assertEqual(result["claims"][0]["status"], "supported")
        self.assertFalse(result["truncated"])

    async def test_no_snippets_skips_model(self):
        model = SimpleNamespace(ainvoke=AsyncMock())
        result = await analyze_evidence({"report": CLAIM, "sources": []}, model)
        self.assertEqual(result["claims"], [])
        model.ainvoke.assert_not_called()

    async def test_invalid_model_json_fails(self):
        model = SimpleNamespace(ainvoke=AsyncMock(return_value=SimpleNamespace(content="not JSON")))
        with self.assertRaises(ValueError):
            await analyze_evidence(ITEM, model)


class EndpointTests(unittest.TestCase):
    """Exercise the actual endpoint function without starting research providers."""
    def setUp(self):
        from fastapi import FastAPI, Depends, HTTPException, Request
        from fastapi.testclient import TestClient

        def user_dependency(request: Request):
            if request.headers.get("Authorization") != "Bearer test-user":
                raise HTTPException(status_code=401)
            return SimpleNamespace(id="owner-a")

        self.lookup = Mock(return_value=ITEM)
        tree = ast.parse(Path(__file__).with_name("main.py").read_text(encoding="utf-8"))
        endpoint = next(node for node in tree.body if isinstance(node, ast.AsyncFunctionDef) and node.name == "review_history_evidence")
        endpoint.decorator_list = []
        namespace = {"Request": Request, "User": object, "Depends": Depends, "HTTPException": HTTPException,
                     "get_current_user": user_dependency, "get_history_item": self.lookup,
                     "asyncio": asyncio, "logger": logging.getLogger(__name__), "rate_limited_llm": object()}
        exec(compile(ast.Module(body=[endpoint], type_ignores=[]), "main.py", "exec"), namespace)
        app = FastAPI()
        app.post("/api/history/{item_id}/evidence")(namespace["review_history_evidence"])
        self.client = TestClient(app)

    def test_unauthenticated_request_is_rejected(self):
        response = self.client.post("/api/history/report-1/evidence")
        self.assertEqual(response.status_code, 401)
        self.lookup.assert_not_called()

    def test_ownership_lookup_precedes_analysis(self):
        self.lookup.return_value = None
        with patch("evidence.analyze_evidence", new_callable=AsyncMock) as analyze:
            response = self.client.post("/api/history/other-report/evidence", headers={"Authorization": "Bearer test-user"})
        self.assertEqual(response.status_code, 404)
        self.lookup.assert_called_once_with("owner-a", "other-report")
        analyze.assert_not_called()

    def test_review_success_and_timeout(self):
        with patch("evidence.analyze_evidence", new_callable=AsyncMock, return_value={"claims": []}):
            response = self.client.post("/api/history/report-1/evidence", headers={"Authorization": "Bearer test-user"})
        self.assertEqual(response.status_code, 200)
        with patch("evidence.analyze_evidence", new_callable=AsyncMock, side_effect=asyncio.TimeoutError):
            response = self.client.post("/api/history/report-1/evidence", headers={"Authorization": "Bearer test-user"})
        self.assertEqual(response.status_code, 504)



class ReliabilityTests(unittest.IsolatedAsyncioTestCase):
    async def test_oversize_bucket_fails_instead_of_hanging(self):
        from rate_limiter import TokenBucket
        bucket = TokenBucket(capacity=10, refill_rate=1)
        with self.assertRaises(ValueError):
            await asyncio.wait_for(bucket.acquire(11), timeout=0.1)

    async def test_large_report_fits_real_limiter_before_model_call(self):
        from rate_limiter import GroqRateLimiter
        raw = SimpleNamespace(ainvoke=AsyncMock(return_value=SimpleNamespace(content=json.dumps(candidate()))))
        limiter = GroqRateLimiter(llm=raw, rpm=28, tpm=5500)
        item = {"report": CLAIM + (" More evidence." * 2000),
                "sources": [{"title": "Study", "url": "https://example.org", "snippet": QUOTE + (" detail" * 500)}] * 24}
        result = await asyncio.wait_for(analyze_evidence(item, limiter), timeout=3)
        self.assertEqual(result["claims"][0]["status"], "supported")
        self.assertTrue(result["truncated"])
        messages = raw.ainvoke.call_args.args[0]
        self.assertLess(limiter._estimate_tokens(messages), 5500)

    async def test_formatted_claim_matches_report(self):
        item = {**ITEM, "report": "**Solar generation** increased during the study period."}
        result = validate_review(candidate(), prepare_evidence(item))
        self.assertEqual(result["claims"][0]["status"], "supported")

    async def test_model_prose_and_reasoning_wrappers(self):
        from evidence import parse_review_content
        raw = "<think>considering {data}</think>Here is the review:\n" + json.dumps(candidate()) + "\nEnd."
        self.assertEqual(parse_review_content(raw), candidate())

    async def test_invalid_answer_repaired_once(self):
        raw = SimpleNamespace(ainvoke=AsyncMock(side_effect=[
            SimpleNamespace(content="invalid"),
            SimpleNamespace(content=json.dumps(candidate()))
        ]))
        result = await analyze_evidence(ITEM, raw)
        self.assertEqual(result["claims"][0]["status"], "supported")
        self.assertEqual(raw.ainvoke.await_count, 2)


if __name__ == "__main__":
    unittest.main()
