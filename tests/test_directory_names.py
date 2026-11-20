"""Filesystem names remain unchanged; uv receives separate technical metadata."""
from pathlib import Path
import tempfile
import tomllib
import unittest
import yaml

from tests.test_generator import render

EXACT = dict(use_http_api=True, use_mcp=True, mcp_transport="http", database="postgresql", use_alembic=True, settings_backend="magutils", use_http_client=True, install_dependencies=False)
CASES = (
    ("new_pyproject", "app-new-pyproject"),
    ("UpperCASE", "app-uppercase"),
    ("a" * 100, "app-" + "a" * 100),
    ("fastapi", "app-fastapi"),
    ("anyio", "app-anyio"),
    ("magutils", "app-magutils"),
    ("Русский", "app-app"),
    ("Service с пробелами", "app-service"),
    (" service with spaces ", "app-service-with-spaces"),
    ('bad"name', "app-bad-name"),
    ("bad\nname", "app-bad-name"),
    ("bad\\name", "app-bad-name"),
    ("123name", "app-123name"),
    ("bad--name", "app-bad-name"),
    ("---", "app-app"),
)


class DirectoryNames(unittest.TestCase):
    def test_names_are_preserved_and_metadata_is_valid(self) -> None:
        for dirname, metadata_name in CASES:
            with self.subTest(dirname=dirname), tempfile.TemporaryDirectory() as tmp:
                destination = Path(tmp) / dirname
                render(destination, **EXACT)
                self.assertTrue(destination.is_dir())
                self.assertEqual([entry.name for entry in Path(tmp).iterdir()], [dirname])
                metadata = tomllib.loads((destination / "pyproject.toml").read_text())
                self.assertEqual(metadata["project"]["name"], metadata_name)
                saved = yaml.safe_load((destination / ".copier-answers.yml").read_text())
                self.assertEqual(saved["project_name"], dirname)
                self.assertFalse(saved["install_dependencies"])
                self.assertTrue(saved["use_http_api"])
                self.assertTrue(saved["use_mcp"])
                self.assertEqual(saved["database"], "postgresql")
                self.assertEqual(saved["settings_backend"], "magutils")
                self.assertTrue(saved["use_alembic"])
                self.assertTrue(saved["use_http_client"])
                for artifact in ("uv.lock", ".venv", ".git"):
                    self.assertFalse((destination / artifact).exists())
