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
BASE = dict(project_name="contract-service", package_name="contract_service", description="Contract service", author_name="Contract Author", project_license="MIT", use_http_api=True, http_framework="fastapi", use_mcp=False, mcp_transport="http", database="none", use_alembic=False, use_settings=True, use_http_client=False)
DRIVERS = {"postgresql": "asyncpg", "sqlite": "aiosqlite", "mysql": "asyncmy"}


def render(destination: Path, **answers: object) -> None:
    data = BASE | answers
    with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
        run_copy(str(SOURCE), str(destination), data=data, defaults=True, vcs_ref="HEAD", quiet=True)


class GeneratorContract(unittest.TestCase):
    def test_matrix(self) -> None:
        cases = [(True, False, "http", "none", False, True, False, "MIT"), (False, True, "http", "none", False, False, True, "none"), (False, True, "stdio", "none", False, True, False, "MIT"), (True, True, "http", "none", False, False, False, "none")]
        cases += [(True, True, "http", db, alembic, alembic, not alembic, "MIT" if alembic else "none") for db in DRIVERS for alembic in (False, True)]
        for http, mcp, transport, db, alembic, settings, client, license_name in cases:
            with self.subTest(http=http, mcp=mcp, transport=transport, db=db, alembic=alembic), tempfile.TemporaryDirectory() as tmp:
                dest = Path(tmp) / "out"
                render(dest, use_http_api=http, use_mcp=mcp, mcp_transport=transport, database=db, use_alembic=alembic, use_settings=settings, use_http_client=client, project_license=license_name)
                metadata = tomllib.loads((dest / "pyproject.toml").read_text())
                names = {re.split(r"[\[<>=!~ ;]", dep)[0].lower().replace("_", "-") for dep in metadata["project"]["dependencies"]}
                for dep, expected in {"fastapi": http, "uvicorn": http or (mcp and transport == "http"), "fastmcp": mcp, "sqlalchemy": db != "none", "alembic": alembic, "pydantic-settings": settings, "httpx": client}.items():
                    self.assertEqual(dep in names, expected, dep)
                for database, driver in DRIVERS.items():
                    self.assertEqual(driver in names, db == database)
                self.assertTrue({"copier", "redis", "psycopg", "pymysql", "loguru"}.isdisjoint(names))
                self.assertIn("3.14", metadata["project"]["requires-python"])
                paths = {str(path.relative_to(dest)) for path in dest.rglob("*")}
                for forbidden in ("uv.lock", ".venv", ".git", "Dockerfile", ".github", ".gitlab-ci.yml", "routers", "src/env.py", "src/models"):
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
                self.assertIn("contract_service", readme)

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
        for field in ("project_name", "package_name"):
            for value in ("../escape", "/tmp/escape", "a/b", "a\\b", "", 'bad"name', "bad\nname"):
                with self.subTest(field=field, value=value), tempfile.TemporaryDirectory() as tmp:
                    with self.assertRaises(Exception):
                        render(Path(tmp) / "out", **{field: value})
        for value in ("os", "json", "asyncio", "logging", "fastapi", "httpx", "sqlalchemy", "pydantic", "pytest", "class", "123bad", "a-b"):
            with self.subTest(package=value), tempfile.TemporaryDirectory() as tmp:
                with self.assertRaises(Exception):
                    render(Path(tmp) / "out", package_name=value)

    def test_distribution_and_selected_import_collisions(self) -> None:
        cases = [
            dict(project_name="fastapi", package_name="service_app", use_http_api=True),
            dict(package_name="pydantic_core", use_settings=True),
            dict(package_name="greenlet", database="sqlite"),
            dict(project_name="valid-service\n"),
            dict(package_name="valid_service\n"),
        ]
        for answers in cases:
            with self.subTest(answers=answers), tempfile.TemporaryDirectory() as tmp:
                dest = Path(tmp) / "out"
                with self.assertRaises(ValueError):
                    render(dest, **answers)
                for artifact in ("uv.lock", ".venv", ".git"):
                    self.assertFalse((dest / artifact).exists())

    def test_invalid_answers(self) -> None:
        for answers in (dict(use_http_api=False, use_mcp=False), dict(use_http_api=True, use_mcp=True, mcp_transport="stdio"), dict(database="oracle"), dict(project_license="Apache-2.0"), dict(http_framework="django"), dict(use_http_api=False, use_mcp=True, mcp_transport="udp")):
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
                    run_copy(str(SOURCE), str(Path(tmp) / "out"), data=data, defaults=True, vcs_ref="HEAD", quiet=True)
