"""Run generated public contracts in local isolated synthetic environments."""
import hashlib
import re
import os
from pathlib import Path
import subprocess
import tempfile
import unittest

from tests.test_service_acceptance import render
from tests.test_update_contract import fixture_git



SETTINGS_PROBE = """import hashlib
try:
    from src.env import Settings
    settings = Settings()
    token = settings.api_token
    assert token not in repr(settings)
    print(hashlib.sha256(token.encode()).hexdigest())
except BaseException as error:
    print(type(error).__name__, str(error))
    raise SystemExit(7)
"""


def settings_probe(python: str, destination: Path, env: dict) -> subprocess.CompletedProcess:
    return subprocess.run([python, "-c", SETTINGS_PROBE], cwd=destination, env=env, capture_output=True, text=True, timeout=20)


class MiddlewareContract(unittest.TestCase):
    def test_generated_auth_di_all_settings(self) -> None:
        for backend in ("getenv", "pydantic_settings", "magutils"):
            with self.subTest(backend=backend), tempfile.TemporaryDirectory(prefix="middleware-contract-") as tmp:
                destination = Path(tmp) / "service"
                render(destination, dict(use_mcp=True, settings_backend=backend, use_http_client=True, use_magutils=backend != "magutils"))
                # The empty synthetic file bounds native dotenv lookup to this fixture.
                (Path(tmp) / ".env").write_text("")
                env = os.environ.copy()
                for key in ("API_TOKEN", "PYTHONPATH", "HOST", "PORT", "DATABASE_URL"):
                    env.pop(key, None)
                sync = subprocess.run(["uv", "sync", "--offline"], cwd=destination, env=env, capture_output=True, timeout=120)
                self.assertEqual(sync.returncode, 0, "local fixture uv sync --offline failed; prepare dependencies in the active uv cache")
                python = str(destination / ".venv/bin/python")
                self.check_bootstrap(python, destination, env)
                result = subprocess.run([python, "-m", "pytest", "--tb=no", "--show-capture=no", "-o", "log_cli=false", "-q"], cwd=destination, env=env, capture_output=True, text=True, timeout=60)
                self.assertEqual(result.returncode, 0, "generated contract failed: " + "\n".join(result.stdout.splitlines()[-8:]))

    def check_bootstrap(self, python: str, destination: Path, env: dict) -> None:
        dotenv = destination / ".env"
        first = settings_probe(python, destination, env)
        self.assertEqual(first.returncode, 0, "first bootstrap failed")
        self.assertTrue(dotenv.is_file(), "bootstrap must create project/.env")
        content = dotenv.read_text()
        match = re.search(r"API_TOKEN=['\"]?([0-9a-f]{32})", content)
        self.assertIsNotNone(match, "persisted token must contain 32 hex characters")
        token = match.group(1)
        digest = hashlib.sha256(token.encode()).hexdigest()
        self.assertTrue(first.stdout.strip() == digest, "settings token must match persisted token")
        self.assertNotIn(token, first.stderr)
        restart = settings_probe(python, destination, env)
        self.assertEqual(restart.returncode, 0)
        self.assertTrue(restart.stdout.strip() == digest, "restart must reuse persisted token")
        self.assertTrue(dotenv.read_text() == content, "restart must not change .env")
        override = "synthetic-env-override-token"
        priority = settings_probe(python, destination, env | {"API_TOKEN": override})
        self.assertEqual(priority.returncode, 0)
        self.assertTrue(priority.stdout.strip() == hashlib.sha256(override.encode()).hexdigest())
        self.assertTrue(dotenv.read_text() == content, "environment priority must not overwrite file")
        original = "# synthetic preserved comment\nHOST=127.0.0.2\nPORT=18881\nOTHER_VALUE=preserved\n"
        dotenv.write_text(original)
        existing = settings_probe(python, destination, env)
        self.assertEqual(existing.returncode, 0)
        self.assertTrue(dotenv.read_text().startswith(original), "other .env contents must be preserved")
        self.assertRegex(dotenv.read_text(), r"API_TOKEN=['\"]?[0-9a-f]{32}")
        dotenv.write_text("# synthetic readonly target\n")
        dotenv.chmod(0o444)
        try:
            self.assertFalse(os.access(dotenv, os.W_OK), "fixture must be genuinely non-writable")
            failure = settings_probe(python, destination, env)
            self.assertEqual(failure.returncode, 7, "write failure must abort Settings creation")
            self.assertNotIn(token, failure.stdout + failure.stderr)
            self.assertNotRegex(failure.stdout + failure.stderr, r"[0-9a-f]{32}")
            self.assertEqual(dotenv.read_text(), "# synthetic readonly target\n")
        finally:
            dotenv.chmod(0o644)
        # Leave a harmless owned boundary for subsequent generated pytest.
        dotenv.write_text("")
        fixture_git(destination, "init")
        ignored = subprocess.run(["git", "check-ignore", "--no-index", ".env"], cwd=destination, capture_output=True, timeout=10)
        self.assertEqual(ignored.returncode, 0, ".env must be gitignored")
        self.assertNotIn("API_TOKEN", (destination / ".copier-answers.yml").read_text())
