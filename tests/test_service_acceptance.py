"""Independent blackbox standalone service contract."""
import contextlib
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import tomllib
import unittest

from copier import run_copy
from plumbum import local

SOURCE = Path(__file__).resolve().parents[1]
BASE = dict(description="Проверка", author_name="Tester", project_license="MIT", use_http_api=True, use_mcp=False, database="none", settings_backend="getenv", use_magutils=False, use_http_client=False, install_dependencies=False)


def render(dest: Path, options: dict | None = None, **kwargs: object) -> None:
    with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
        run_copy(str(SOURCE), str(dest), data=BASE | (options or {}), defaults=True, quiet=True, vcs_ref="HEAD", unsafe=True, **kwargs)


def execute(dest: Path, code: str, extra: dict | None = None) -> subprocess.CompletedProcess:
    env = os.environ.copy()
    for key in ("HOST", "PORT", "DATABASE_URL", "PYTHONPATH"):
        env.pop(key, None)
    env.update(extra or {})
    # Python -c has the working directory on sys.path; no package or path injection.
    wrapped = "try:\n" + "\n".join("    " + line for line in code.splitlines()) + "\nexcept BaseException as error:\n    print(type(error).__name__)\n    raise SystemExit(1)\n"
    return subprocess.run([sys.executable, "-c", wrapped], cwd=dest, env=env, text=True, capture_output=True, timeout=60)


class ServiceAcceptance(unittest.TestCase):
    def test_native_settings_matrix_and_dotenv_ignored(self) -> None:
        for backend, optional in (("getenv", False), ("getenv", True), ("pydantic_settings", False), ("pydantic_settings", True), ("magutils", False)):
            with self.subTest(backend=backend, optional=optional), tempfile.TemporaryDirectory() as tmp:
                dest = Path(tmp) / "settings-service"
                render(dest, dict(settings_backend=backend, use_magutils=optional, database="sqlite"))
                (dest / ".env").write_text("HOST=192.0.2.1\nPORT=19999\nDATABASE_URL=sqlite+aiosqlite:///dotenv.db\n")
                result = execute(dest, 'from src.env import Settings\ns = Settings()\nassert s.host == "127.0.0.1"\nassert s.port == 8000\nassert str(s.database_url) != "sqlite+aiosqlite:///dotenv.db"\nprint("ok")')
                self.assertEqual(result.returncode, 0, result.stdout)
                result = execute(dest, 'from src.env import Settings\ns = Settings()\nassert s.host == "127.0.0.2"\nassert s.port == 18765\nassert str(s.database_url) == "sqlite+aiosqlite:///explicit.db"\nprint("ok")', {"HOST":"127.0.0.2", "PORT":"18765", "DATABASE_URL":"sqlite+aiosqlite:///explicit.db"})
                self.assertEqual(result.returncode, 0, result.stdout)
                expected_second = 18081 if backend == "magutils" else 18082
                result = execute(dest, 'import os\nos.environ["PORT"] = "18081"\nfrom src.env import Settings\nfirst = Settings()\nos.environ["PORT"] = "18082"\nsecond = Settings()\nassert first.port == 18081\nassert second.port == ' + str(expected_second))
                self.assertEqual(result.returncode, 0, result.stdout)
                metadata = tomllib.loads((dest / "pyproject.toml").read_text())
                names = [item.split(">=")[0] for item in metadata["project"]["dependencies"]]
                self.assertEqual("magutils" in names, optional or backend == "magutils")
                if optional or backend == "magutils":
                    self.assertEqual(metadata["tool"]["uv"]["sources"]["magutils"]["rev"], "c54820bb9d782c70c6f6be52bf28860e48bfb4fb")

    def test_install_task_boundaries(self) -> None:
        for mode in ("default", "no", "yes", "skip", "pretend", "failure", "guard", "missing"):
            with self.subTest(mode=mode), tempfile.TemporaryDirectory(prefix="service parent ; $() ") as tmp:
                parent = Path(tmp)
                fake = parent / "bin"
                fake.mkdir()
                marker = parent / "calls.json"
                uv = fake / "uv"
                uv.write_text('#!' + sys.executable + '\nimport json,os,sys\nfrom pathlib import Path\nPath(os.environ["UV_PROBE"]).write_text(json.dumps([os.getcwd(),sys.argv[1:]]))\nraise SystemExit(' + ('7' if mode == 'failure' else '0') + ')\n')
                uv.chmod(0o755)
                dest = parent / "task-service"
                options = {} if mode == "default" else {"install_dependencies": mode != "no"}
                kwargs = {"cleanup_on_error": mode == "guard", "skip_tasks": mode == "skip", "pretend": mode == "pretend"}
                old = os.environ.copy()
                os.environ.update(PATH=str(fake) if mode != "missing" else str(parent / "absent"), UV_PROBE=str(marker))
                try:
                    local.env.update(PATH=os.environ["PATH"], UV_PROBE=str(marker))
                    if mode in ("failure", "guard", "missing"):
                        with self.assertRaises(Exception):
                            render(dest, options, **kwargs)
                    else:
                        render(dest, options, **kwargs)
                finally:
                    local.env.update(PATH=old["PATH"])
                    os.environ.clear()
                    os.environ.update(old)
                self.assertEqual(marker.exists(), mode in ("yes", "failure"))
                if marker.exists():
                    self.assertEqual(json.loads(marker.read_text()), [str(dest), ["sync"]])
                if mode in ("yes", "failure", "missing", "default", "no", "skip"):
                    self.assertTrue((dest / "main.py").exists())
                self.assertFalse((dest / ".git").exists())
                self.assertFalse((dest / ".venv").exists())

    def test_database_startup_does_not_connect(self) -> None:
        for db, url in (("postgresql", "postgresql+asyncpg://fixture@127.0.0.1:1/missing"), ("mysql", "mysql+asyncmy://fixture@127.0.0.1:1/missing"), ("sqlite", "sqlite+aiosqlite:////nonexistent-contract-directory/db.sqlite")):
            with self.subTest(db=db), tempfile.TemporaryDirectory() as tmp:
                dest = Path(tmp) / "no-connect-service"
                render(dest, dict(database=db, use_mcp=True, use_http_client=True))
                code = "import asyncio\nfrom main import app\nfrom config import resources\nasync def check():\n    async with app.router.lifespan_context(app):\n        pass\n    async with resources() as state:\n        assert isinstance(state, dict)\nasyncio.run(check())"
                result = execute(dest, code, {"DATABASE_URL": url})
                self.assertEqual(result.returncode, 0, result.stdout)

    def test_install_requires_trust(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            dest = Path(tmp) / "untrusted-service"
            with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
                with self.assertRaises(Exception):
                    run_copy(str(SOURCE), str(dest), data=BASE | {"install_dependencies": True}, defaults=True, quiet=True, vcs_ref="HEAD", unsafe=False, cleanup_on_error=False)
            self.assertFalse((dest / ".venv").exists())
