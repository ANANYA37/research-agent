import asyncio
import sys
import time
import types
import unittest
from unittest.mock import patch, AsyncMock
from sqlalchemy import create_engine, select, func
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient
from database import Base
from db_models import User, ResearchHistory, Watchlist, WatchlistRun
import watchlists as service
from watchlist_routes import router
from auth import get_current_user


class WatchlistTests(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
        Base.metadata.create_all(self.engine)
        self.sessions = sessionmaker(self.engine, expire_on_commit=False)
        self.mock_db = patch.object(service, "SessionLocal", self.sessions)
        self.mock_db.start()
        with self.sessions.begin() as db:
            db.add_all([User(id="alice", email="a@example.test", password_hash="x"), User(id="bob", email="b@example.test", password_hash="x")])
            db.flush()
            db.add(ResearchHistory(id="report", user_id="alice", topic="Solar", normalized_topic="solar", depth=2,
                                  report="Original finding.", sources=[{"url": "https://example.test/a", "title": "A"}]))
        self.watch = service.create_watch("alice", "report", "weekly")
        self.wid = self.watch["id"]
        app = FastAPI()
        app.include_router(router)
        app.dependency_overrides[get_current_user] = lambda: User(id="alice")
        self.app = app
        self.client = TestClient(app)

    def tearDown(self):
        self.client.close()
        self.mock_db.stop()
        self.engine.dispose()

    def ready(self):
        with self.sessions.begin() as db:
            row = db.get(Watchlist, self.wid)
            row.last_check = 0

    def test_baseline_is_immutable_and_create_is_idempotent(self):
        same = service.create_watch("alice", "report", "monthly")
        self.assertEqual(same["id"], self.wid)
        with self.sessions.begin() as db:
            db.get(ResearchHistory, "report").report = "Overwritten library report"
        run = service.get_watch("alice", self.wid)["runs"][0]
        snapshot = service.get_run("alice", self.wid, run["id"])
        self.assertEqual(snapshot["result"]["report"], "Original finding.")

    def test_ownership_and_api_validation(self):
        baseline = service.get_watch("alice", self.wid)["runs"][0]["id"]
        self.assertEqual(self.client.patch(f"/api/watchlists/{self.wid}", json={"frequency": "hourly"}).status_code, 422)
        self.app.dependency_overrides[get_current_user] = lambda: User(id="bob")
        self.assertEqual(self.client.get("/api/watchlists").json(), [])
        for method, path, data in [
            ("post", "/api/watchlists", {"report_id": "report"}),
            ("get", f"/api/watchlists/{self.wid}", None),
            ("patch", f"/api/watchlists/{self.wid}", {"paused": True}),
            ("delete", f"/api/watchlists/{self.wid}", None),
            ("post", f"/api/watchlists/{self.wid}/check", None),
            ("get", f"/api/watchlists/{self.wid}/runs/{baseline}", None)]:
            response = self.client.request(method, path, **({"json": data} if data else {}))
            self.assertEqual(response.status_code, 404, response.text)

    def test_changes_unread_and_failed_run_baseline(self):
        run = service.reserve_run("alice", self.wid)
        result = {"report": "A new finding.", "sources": [{"url": "https://example.test/b"}]}
        service.finish_run(self.wid, run, result)
        watch = service.get_watch("alice", self.wid)
        self.assertEqual(watch["unread"], 1)
        changes = watch["runs"][0]["changes"]
        self.assertEqual(len(changes["added_sources"]), 1)
        self.assertEqual(len(changes["removed_sources"]), 1)
        service.update_watch("alice", self.wid, {"mark_read": True})
        self.ready()
        failed = service.reserve_run("alice", self.wid)
        service.finish_run(self.wid, failed, error="Failed")
        self.ready()
        retry = service.reserve_run("alice", self.wid)
        service.finish_run(self.wid, retry, result)
        watch = service.get_watch("alice", self.wid)
        self.assertFalse(watch["runs"][0]["changes"]["changed"])
        self.assertEqual(watch["unread"], 0)
        self.assertEqual(len(watch["runs"]), 4)

    def test_no_change_normalizes_whitespace(self):
        result = service.compare_versions({"report": "one  two\n", "sources": []}, {"report": "one two", "sources": []})
        self.assertFalse(result["changed"])

    def test_pause_schedule_cooldown_and_duplicate_reservation(self):
        self.assertIsNone(service.reserve_run("alice", self.wid, scheduled=True))
        service.update_watch("alice", self.wid, {"paused": True})
        with self.assertRaises(HTTPException) as raised:
            service.reserve_run("alice", self.wid)
        self.assertEqual(raised.exception.status_code, 409)
        resumed = service.update_watch("alice", self.wid, {"paused": False, "frequency": "monthly"})
        self.assertAlmostEqual(resumed["next_check"] - time.time(), 30 * 86400, delta=3)
        run = service.reserve_run("alice", self.wid)
        with self.assertRaises(HTTPException):
            service.reserve_run("alice", self.wid)
        with self.assertRaises(HTTPException):
            service.delete_watch("alice", self.wid)
        service.finish_run(self.wid, run, error="failed")
        with self.assertRaises(HTTPException) as raised:
            service.reserve_run("alice", self.wid)
        self.assertEqual(raised.exception.status_code, 429)

    def test_expired_run_recovery_and_overdue_schedule(self):
        run = service.reserve_run("alice", self.wid)
        with self.sessions.begin() as db:
            db.get(WatchlistRun, run).created_at = time.time() - service.RUN_TIMEOUT - 70
            db.get(Watchlist, self.wid).next_check = time.time() - 1
        self.assertIn(("alice", self.wid), service.recover_and_due())
        watch = service.get_watch("alice", self.wid)
        self.assertIsNone(watch["active_run_id"])
        self.assertEqual(next(r for r in watch["runs"] if r["id"] == run)["status"], "failed")

    def test_deletion_preserves_library_report(self):
        self.assertEqual(self.client.delete(f"/api/watchlists/{self.wid}").status_code, 204)
        with self.sessions() as db:
            self.assertIsNotNone(db.get(ResearchHistory, "report"))
            self.assertEqual(db.scalar(select(func.count()).select_from(WatchlistRun)), 0)

    def test_fresh_research_execution_and_empty_failure(self):
        run = service.reserve_run("alice", self.wid)
        fake = types.ModuleType("agent")
        fake.run_research = AsyncMock(return_value={"report": "Fresh result", "sources": []})
        with patch.dict(sys.modules, {"agent": fake}):
            asyncio.run(service.execute_run(self.wid, run))
        fake.run_research.assert_awaited_once_with(topic="Solar", depth=2)
        self.assertEqual(service.get_run("alice", self.wid, run)["status"], "success")
        self.ready()
        run = service.reserve_run("alice", self.wid)
        fake.run_research = AsyncMock(return_value={"report": "", "sources": []})
        with patch.dict(sys.modules, {"agent": fake}), self.assertLogs("watchlists", level="ERROR"):
            asyncio.run(service.execute_run(self.wid, run))
        self.assertEqual(service.get_run("alice", self.wid, run)["status"], "failed")


if __name__ == "__main__":
    unittest.main()
