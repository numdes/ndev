import os
import tempfile

from pathlib import Path

from cleo.application import Application
from cleo.testers.command_tester import CommandTester

from ndev.commands.release import ReleaseCommand


def test_no_pyproject_toml(fixtures_dir: Path) -> None:
    app = Application()
    origin_dir = fixtures_dir / "00_no_pyproject_toml"
    assert origin_dir.exists()

    app.add(ReleaseCommand())

    command = app.find("release")
    tester = CommandTester(command)
    status_code = tester.execute(f"--origin {origin_dir}")
    assert status_code == os.EX_NOINPUT


def test_simple_project(fixtures_dir: Path) -> None:
    app = Application()
    origin_dir = fixtures_dir / "01_simple_project"
    assert origin_dir.exists()

    app.add(ReleaseCommand())

    command = app.find("release")
    tester = CommandTester(command)
    with tempfile.TemporaryDirectory() as tmp_dir:
        status_code = tester.execute(f" --origin {origin_dir} --destination={tmp_dir}")
    assert status_code == os.EX_OK


def test_remove_todo(fixtures_dir: Path) -> None:
    app = Application()
    origin_dir = fixtures_dir / "10_project_with_code_no_todo"
    assert origin_dir.exists()

    app.add(ReleaseCommand())

    command = app.find("release")
    tester = CommandTester(command)
    with tempfile.TemporaryDirectory() as tmp_dir:
        status_code = tester.execute(f" --origin {origin_dir} --destination={tmp_dir}")
        for py_file in Path(tmp_dir).rglob("*.py"):
            content = py_file.read_text()
            assert "TODO" not in content

    assert status_code == os.EX_OK


def test_leave_todo(fixtures_dir: Path) -> None:
    app = Application()
    origin_dir = fixtures_dir / "11_project_with_code_with_todo"
    assert origin_dir.exists()

    app.add(ReleaseCommand())

    command = app.find("release")
    tester = CommandTester(command)
    at_least_one_todo = False
    with tempfile.TemporaryDirectory() as tmp_dir:
        tester.execute(f" --origin {origin_dir} --destination={tmp_dir}")
        for py_file in Path(tmp_dir).rglob("*.py"):
            if "TODO" in py_file.read_text():
                at_least_one_todo = True
    assert at_least_one_todo, "At least one TODO should be left in the code"
