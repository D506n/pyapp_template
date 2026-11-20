"""Black-box acceptance tests; no template source inspection is required."""
import contextlib
import io
import os
from pathlib import Path
import re
import tempfile
import tomllib
import unittest

from copier import run_copy

SOURCE = Path(__file__).resolve().parents[1]
BASE = dict(description="Contract service", author_name="Contract Author", project_license="MIT", use_http_api=True, http_framework="fastapi", use_mcp=False, mcp_transport="http", database="none", use_alembic=False, settings_backend="getenv", use_magutils=False, use_http_client=False)
DRIVERS = {"postgresql": "asyncpg", "sqlite": "aiosqlite", "mysql": "asyncmy"}


def render(destination: Path, **answers: object) -> None:
    data = BASE | answers
    with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
        run_copy(str(SOURCE), str(destination), data=data, defaults=True, vcs_ref="HEAD", unsafe=True, quiet=True)


class GeneratorContract(unittest.TestCase):
    def test_matrix(self) -> None:
        cases = [(True, False, "http", "none", False, True, False, "MIT"), (False, True, "http", "none", False, False, True, "none"), (False, True, "stdio", "none", False, True, False, "MIT"), (True, True, "http", "none", False, False, False, "none")]
        cases += [(True, True, "http", db, alembic, alembic, not alembic, "MIT" if alembic else "none") for db in DRIVERS for alembic in (False, True)]
        for http, mcp, transport, db, alembic, settings, client, license_name in cases:
            with self.subTest(http=http, mcp=mcp, transport=transport, db=db, alembic=alembic), tempfile.TemporaryDirectory() as tmp:
                dest = Path(tmp) / "out"
                render(dest, use_http_api=http, use_mcp=mcp, mcp_transport=transport, database=db, use_alembic=alembic, settings_backend="pydantic_settings" if settings else "getenv", use_http_client=client, project_license=license_name)
                metadata = tomllib.loads((dest / "pyproject.toml").read_text())
                names = {re.split(r"[\[<>=!~ ;]", dep)[0].lower().replace("_", "-") for dep in metadata["project"]["dependencies"]}
                for dep, expected in {"fastapi": http, "uvicorn": http or (mcp and transport == "http"), "fastmcp": mcp, "sqlalchemy": db != "none", "alembic": alembic, "pydantic-settings": settings, "httpx": client}.items():
                    self.assertEqual(dep in names, expected, dep)
                for database, driver in DRIVERS.items():
                    self.assertEqual(driver in names, db == database)
                self.assertTrue({"copier", "redis", "psycopg", "pymysql", "loguru"}.isdisjoint(names))
                self.assertIn("3.14", metadata["project"]["requires-python"])
                paths = {str(path.relative_to(dest)) for path in dest.rglob("*")}
                for forbidden in ("uv.lock", ".venv", ".git", "Dockerfile", ".github", ".gitlab-ci.yml", "routers", "src/models", "src/out"):
                    self.assertNotIn(forbidden, paths)
                self.assertEqual("migrations" in paths, alembic)
                self.assertEqual("LICENSE" in paths, license_name == "MIT")
                self.assertIn("THIRD_PARTY_NOTICES.md", paths)
                for name in ("README.md", "AGENTS.md", "AGENTS.project.md", "CODESTYLE.md"):
                    document = (dest / name).read_text()
                    self.assertNotIn("/home/", document)
                    self.assertNotIn("mag-infra", document)
                readme = (dest / "README.md").read_text()
                self.assertIn("uv lock", readme)
                self.assertIn("uv sync --locked", readme)
                self.assertEqual(metadata["project"]["name"], "out")
                self.assertFalse(metadata["tool"]["uv"]["package"])
                self.assertNotIn("build-system", metadata)
                self.assertNotIn("scripts", metadata["project"])
                for required in ("main.py", "config.py", "src/env.py"):
                    self.assertIn(required, paths)
                for path, enabled in {"src/api/v1/health.py": http, "src/mcp/tools/ping.py": mcp, "src/connectors/db/conn.py": db != "none", "src/connectors/http.py": client}.items():
                    self.assertEqual(path in paths, enabled)

    def test_free_text_round_trip(self) -> None:
        value = 'Кавычки " и \' \\ newline\nemoji 😀\n$(touch NEVER_EXECUTE)'
        with tempfile.TemporaryDirectory() as tmp:
            dest = Path(tmp) / "out"
            render(dest, description=value, author_name=value)
            project = tomllib.loads((dest / "pyproject.toml").read_text())["project"]
            self.assertEqual(project["description"], value)
            self.assertEqual(project["authors"][0]["name"], value)
            self.assertFalse((dest / "NEVER_EXECUTE").exists())

    def test_reject_bad_names(self) -> None:
        for value in ('bad"name', 'bad\nname', 'bad\\name', '123bad', 'тест', 'bad--name', 'bad_name', 'fastapi', 'magutils', 'pydantic-settings', 'a' * 65):
            with self.subTest(value=value), tempfile.TemporaryDirectory() as tmp:
                with self.assertRaises(Exception):
                    render(Path(tmp) / value)
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaises(Exception):
                render(Path(tmp) / "out", project_name="different")

    def test_invalid_answers(self) -> None:
        for answers in (dict(use_http_api=False, use_mcp=False), dict(use_http_api=True, use_mcp=True, mcp_transport="stdio"), dict(database="oracle"), dict(project_license="Apache-2.0"), dict(http_framework="django"), dict(settings_backend="unknown"), dict(use_http_api=False, use_mcp=True, mcp_transport="udp")):
            with self.subTest(answers=answers), tempfile.TemporaryDirectory() as tmp:
                with self.assertRaises(Exception):
                    render(Path(tmp) / "out", **answers)

    def test_alembic_without_sql_is_not_broken(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            dest = Path(tmp) / "out"
            try:
                render(dest, database="none", use_alembic=True)
            except Exception:
                return
            project = tomllib.loads((dest / "pyproject.toml").read_text())["project"]
            self.assertFalse((dest / "migrations").exists())
            self.assertFalse(any(dep.startswith("alembic") for dep in project["dependencies"]))

    def test_license_requires_explicit_selection(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            data = BASE.copy()
            del data["project_license"]
            with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
                with self.assertRaises(Exception):
                    run_copy(str(SOURCE), str(Path(tmp) / "out"), data=data, defaults=True, vcs_ref="HEAD", unsafe=True, quiet=True)
