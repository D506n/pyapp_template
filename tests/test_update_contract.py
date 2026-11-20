"""Opaque template fixture verifies copy/update public contracts."""
import contextlib
import io
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import tomllib
import unittest

from copier import run_copy, run_update
from plumbum import local
import yaml

SOURCE = Path(__file__).resolve().parents[1]
ANSWERS = dict(project_license="MIT", use_http_api=True, use_mcp=False, database="none", settings_backend="getenv", use_magutils=False, use_http_client=False, install_dependencies=True)


def fixture_git(directory: Path, *arguments: str) -> None:
    result = subprocess.run(
        ["git", "-c", "core.hooksPath=/dev/null", "-c", "commit.gpgsign=false", "-c", "user.name=Contract Fixture", "-c", "user.email=fixture@example.invalid", *arguments],
        cwd=directory, capture_output=True, timeout=30,
    )
    if result.returncode:
        raise AssertionError("synthetic git fixture operation failed: " + arguments[0])


def snapshot(source: Path, destination: Path) -> None:
    # Opaque fixture copy: no template source is inspected by the test or tester.
    destination.mkdir()
    shutil.copy2(source / "copier.yml", destination / "copier.yml")
    shutil.copytree(source / "template", destination / "template")
    fixture_git(destination, "init")
    fixture_git(destination, "add", ".")
    fixture_git(destination, "commit", "-m", "Synthetic fixture v1")
    fixture_git(destination, "tag", "v1.0.0")
    # A synthetic file ensures that update actually advances the generated tree.
    (destination / "template" / "README_UPDATE_MARKER.txt").write_text("contract update v2\n")
    fixture_git(destination, "add", ".")
    fixture_git(destination, "commit", "-m", "Synthetic fixture v2")
    fixture_git(destination, "tag", "v2.0.0")


class UpdateContract(unittest.TestCase):
    def test_update_keeps_name_and_never_installs(self) -> None:
        with tempfile.TemporaryDirectory(prefix="update-contract-") as tmp:
            root = Path(tmp)
            source = root / "template-fixture"
            snapshot(SOURCE, source)
            fake = root / "bin"
            fake.mkdir()
            calls = root / "calls.txt"
            uv = fake / "uv"
            uv.write_text("#!" + sys.executable + "\nfrom pathlib import Path\nPath(" + repr(str(calls)) + ").write_text('called')\n")
            uv.chmod(0o755)
            for cleanup in (True, False):
                with self.subTest(cleanup_on_error=cleanup):
                    destination = root / ("updated-default" if cleanup else "updated-retained")
                    with local.env(PATH=str(fake) + os.pathsep + os.environ["PATH"]):
                        with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
                            run_copy(str(source), str(destination), data=ANSWERS, defaults=True, quiet=True, vcs_ref="v1.0.0", unsafe=True, cleanup_on_error=False)
                        self.assertTrue(calls.exists(), "copy consent must invoke actual task")
                        calls.unlink()
                        saved = yaml.safe_load((destination / ".copier-answers.yml").read_text())
                        self.assertEqual(saved["project_name"], destination.name)
                        self.assertIs(saved["install_dependencies"], True)
                        fixture_git(destination, "init")
                        fixture_git(destination, "add", ".")
                        fixture_git(destination, "commit", "-m", "Synthetic generated fixture")
                        kwargs = {} if cleanup else {"cleanup_on_error": False}
                        with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
                            run_update(str(destination), defaults=True, quiet=True, unsafe=True, vcs_ref="v2.0.0", overwrite=True, **kwargs)
                    self.assertFalse(calls.exists(), "update must never execute uv sync")
                    self.assertEqual((destination / "README_UPDATE_MARKER.txt").read_text(), "contract update v2\n")
                    saved = yaml.safe_load((destination / ".copier-answers.yml").read_text())
                    self.assertEqual(saved["project_name"], destination.name)
                    self.assertIs(saved["install_dependencies"], True)
                    metadata = tomllib.loads((destination / "pyproject.toml").read_text())
                    self.assertEqual(metadata["project"]["name"], destination.name)
