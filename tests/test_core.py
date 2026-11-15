"""Dependency-light regression tests for the local Server Bot revision."""
from __future__ import annotations

import importlib
import os
import sqlite3
import sys
import tempfile
import types
import unittest
from contextlib import closing
from datetime import date
from pathlib import Path
from types import SimpleNamespace
from unittest import mock


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def install_docker_sdk_stub() -> None:
    if "docker" in sys.modules:
        return
    docker = types.ModuleType("docker")
    errors = types.ModuleType("docker.errors")

    class DockerException(Exception):
        pass

    class APIError(DockerException):
        pass

    class NotFound(DockerException):
        pass

    errors.DockerException = DockerException
    errors.APIError = APIError
    errors.NotFound = NotFound
    docker.errors = errors
    docker.DockerClient = object
    class DockerClientStub:
        def ping(self):
            return True

    docker.from_env = lambda **kwargs: DockerClientStub()
    sys.modules["docker"] = docker
    sys.modules["docker.errors"] = errors


with mock.patch.dict(os.environ, {
    "TELEGRAM_TOKEN": "unit-test-token",
    "ALLOWED_USER_ID": "42",
    "TZ": "Europe/Rome",
}, clear=True), mock.patch("dotenv.load_dotenv"):
    install_docker_sdk_stub()
    from modules import alea, db, docker_mgr, keyboards, metrics, omniroute_mgr, system
    from modules.authorization import authorized_user
    from modules.settings import SETTINGS


class AleaRegressionTests(unittest.TestCase):
    def test_easter_monday_2026(self) -> None:
        self.assertEqual(alea.get_easter_monday(2026), date(2026, 4, 6))

    def test_weekly_collection_rules(self) -> None:
        self.assertEqual(set(alea.get_base_collection(date(2026, 11, 12))), {"Umido", "Secco/Vegetale"})
        self.assertEqual(set(alea.get_base_collection(date(2026, 11, 9))), {"Umido", "Carta"})


class SettingsAndAuthorizationTests(unittest.TestCase):
    def test_settings_read_global_variable_names_without_copying_env(self) -> None:
        self.assertEqual(SETTINGS.telegram_token, "unit-test-token")
        self.assertEqual(SETTINGS.allowed_user_id, 42)
        self.assertEqual(SETTINGS.timezone, "Europe/Rome")

    def test_authorization_requires_exact_configured_user(self) -> None:
        self.assertTrue(authorized_user(SimpleNamespace(effective_user=SimpleNamespace(id=42))))
        self.assertFalse(authorized_user(SimpleNamespace(effective_user=SimpleNamespace(id=43))))
        self.assertFalse(authorized_user(SimpleNamespace(effective_user=None)))


class SystemAndOmniRouteTests(unittest.TestCase):
    def test_host_status_returns_all_dashboard_fields(self) -> None:
        result = system.get_host_status()
        self.assertEqual(set(result), {"uptime", "memory", "root_disk", "storage_disk", "load"})
        self.assertTrue(all(isinstance(value, str) for value in result.values()))

    def test_omniroute_does_not_report_mock_success_without_endpoint(self) -> None:
        with mock.patch.dict(os.environ, {"OMNIROUTE_HEALTH_URL": ""}, clear=False):
            self.assertIn("non configurato", omniroute_mgr.get_status())


class DatabaseMigrationTests(unittest.TestCase):
    def test_old_audit_schema_is_migrated_without_losing_history(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "bot.db"
            conn = sqlite3.connect(path)
            conn.execute("CREATE TABLE audit_logs (id INTEGER PRIMARY KEY, action TEXT, details TEXT, timestamp TEXT DEFAULT CURRENT_TIMESTAMP)")
            conn.execute("INSERT INTO audit_logs(action,details) VALUES('legacy','preserve')")
            conn.commit()
            conn.close()

            with mock.patch.object(db, "_db_path", return_value=str(path)):
                db.init_db()
                db.log_action(42, "restart", "immich_server", "ok")
                check = sqlite3.connect(path)
                rows = check.execute("SELECT action,details,actor_id,target,result FROM audit_logs ORDER BY id").fetchall()
                check.close()

        self.assertEqual(rows[0][0:2], ("legacy", "preserve"))
        self.assertEqual(rows[1][0], "restart")
        self.assertEqual(rows[1][2:], (42, "immich_server", "ok"))


class DockerManagerTests(unittest.TestCase):
    def setUp(self) -> None:
        self.container = SimpleNamespace(
            name="svc", status="running", attrs={"State": {"Status": "running", "Running": True, "Health": {"Status": "healthy"}}},
            image=SimpleNamespace(tags=["example/svc:1"], short_id="sha256:123"),
            calls=[],
        )
        self.container.reload = lambda: None
        self.container.start = lambda: self.container.calls.append(("start",))
        self.container.stop = lambda timeout: self.container.calls.append(("stop", timeout))
        self.container.restart = lambda timeout: self.container.calls.append(("restart", timeout))
        self.container.logs = lambda tail, timestamps: b"recent log\n"
        self.client = SimpleNamespace(
            containers=SimpleNamespace(
                list=lambda all: [self.container],
                get=lambda name: self.container if name == "svc" else (_ for _ in ()).throw(KeyError(name)),
            )
        )

    def test_inventory_and_details(self) -> None:
        with mock.patch.object(docker_mgr, "get_client", return_value=self.client):
            items = docker_mgr.list_containers()
            detail = docker_mgr.get_container("svc")
        self.assertEqual(items[0]["name"], "svc")
        self.assertTrue(items[0]["running"])
        self.assertEqual(detail["health"], "healthy")

    def test_operations_use_sdk_and_stop_with_timeout(self) -> None:
        with mock.patch.object(docker_mgr, "get_client", return_value=self.client):
            docker_mgr.perform("stop", "svc")
            docker_mgr.perform("restart", "svc")
        self.assertEqual(self.container.calls, [("stop", 15), ("restart", 15)])

    def test_unsupported_action_is_rejected_before_docker_access(self) -> None:
        with mock.patch.object(docker_mgr, "get_client", side_effect=AssertionError("should not connect")):
            with self.assertRaises(ValueError):
                docker_mgr.perform("prune", "svc")

    def test_logs_are_bounded_and_decoded(self) -> None:
        with mock.patch.object(docker_mgr, "get_client", return_value=self.client):
            self.assertEqual(docker_mgr.get_logs("svc", lines=40), "recent log\n")
            with self.assertRaises(ValueError):
                docker_mgr.get_logs("svc", lines=201)


class KeyboardTests(unittest.TestCase):
    def test_container_callbacks_are_short_and_reference_only(self) -> None:
        refs = {"abc123": {"name": "svc", "expires": 9999999999}}
        markup = keyboards.container_list([{"name": "svc", "running": True, "health": "healthy"}], refs)
        callbacks = [button.callback_data for row in markup.inline_keyboard for button in row]
        self.assertIn("container:abc123", callbacks)
        self.assertTrue(all(len(value.encode("utf-8")) <= 64 for value in callbacks))


class MetricsTests(unittest.TestCase):
    def test_numeric_metrics_returns_all_keys(self) -> None:
        result = metrics.get_numeric_metrics()
        self.assertEqual(set(result), {"uptime_sec", "mem_used_pct", "root_disk_pct", "storage_disk_pct", "load_1m"})
        self.assertTrue(all(isinstance(value, float) for value in result.values()))

    def test_check_thresholds_no_alert_below_thresholds(self) -> None:
        metrics_data = {"uptime_sec": 0, "mem_used_pct": 50, "root_disk_pct": 50, "storage_disk_pct": 50, "load_1m": 1.0}
        self.assertEqual(metrics.check_thresholds(metrics_data), [])

    def test_check_thresholds_alerts_above_thresholds(self) -> None:
        metrics_data = {"uptime_sec": 0, "mem_used_pct": 95, "root_disk_pct": 95, "storage_disk_pct": 50, "load_1m": 10.0}
        alerts = metrics.check_thresholds(metrics_data)
        self.assertTrue(any("RAM" in a for a in alerts))
        self.assertTrue(any("Disco root" in a for a in alerts))
        self.assertTrue(any("Load" in a for a in alerts))

    def test_save_and_retrieve_metrics_sample(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "bot.db"
            with mock.patch.object(db, "_db_path", return_value=str(path)):
                db.init_db()
                sample = {"uptime_sec": 100.0, "mem_used_pct": 50.0, "root_disk_pct": 60.0, "storage_disk_pct": 70.0, "load_1m": 1.5}
                db.save_metrics_sample(sample)
                history = db.get_metrics_history(minutes=60)
            self.assertEqual(len(history), 1)
            self.assertEqual(history[0]["mem_used_pct"], 50.0)
            self.assertEqual(history[0]["root_disk_pct"], 60.0)

    def test_prune_metrics_history_removes_old_samples(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "bot.db"
            with mock.patch.object(db, "_db_path", return_value=str(path)):
                db.init_db()
                db.save_metrics_sample({"uptime_sec": 0, "mem_used_pct": 50, "root_disk_pct": 50, "storage_disk_pct": 50, "load_1m": 1.0})
                # days=0 keeps samples from now; verify recent sample survives
                db.prune_metrics_history(days=0)
                history = db.get_metrics_history(minutes=60)
            self.assertEqual(len(history), 1)  # recent sample kept

    def test_prune_metrics_history_removes_very_old_samples(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "bot.db"
            with mock.patch.object(db, "_db_path", return_value=str(path)):
                db.init_db()
                db.save_metrics_sample({"uptime_sec": 0, "mem_used_pct": 50, "root_disk_pct": 50, "storage_disk_pct": 50, "load_1m": 1.0})
                # Backdate the sample to 31 days ago
                with mock.patch.object(db, "_connect") as mock_conn:
                    conn = mock_conn.return_value.__enter__.return_value
                    conn.execute.return_value = None
                # Direct SQL to backdate
                with closing(db._connect()) as conn:
                    conn.execute("UPDATE metrics_history SET timestamp = datetime('now', '-31 days')")
                    conn.commit()
                db.prune_metrics_history(days=30)
                history = db.get_metrics_history(minutes=60 * 24 * 31)
            self.assertEqual(len(history), 0)  # old sample pruned

    def test_format_metrics_report_contains_current_values(self) -> None:
        metrics_data = {"uptime_sec": 3600.0, "mem_used_pct": 50.0, "root_disk_pct": 60.0, "storage_disk_pct": 70.0, "load_1m": 1.5}
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "bot.db"
            with mock.patch.object(db, "_db_path", return_value=str(path)):
                db.init_db()
                report = metrics.format_metrics_report(metrics_data, history_minutes=60)
        self.assertIn("METRICHE SERVER", report)
        self.assertIn("50.0%", report)
        self.assertIn("60.0%", report)

    def test_parse_percent_extracts_value(self) -> None:
        self.assertEqual(metrics._parse_percent("45.2%"), 45.2)
        self.assertEqual(metrics._parse_percent("45%"), 45.0)
        self.assertIsNone(metrics._parse_percent("no value"))


if __name__ == "__main__":
    unittest.main()
