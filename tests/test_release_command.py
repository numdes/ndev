import os
import tempfile
from pathlib import Path

from cleo.application import Application
from cleo.testers.command_tester import CommandTester
from pytest import MonkeyPatch

from ndev.commands.release import ReleaseCommand


def test_no_pyproject_toml(fixtures_dir: Path):
    app = Application()
    origin_dir = fixtures_dir / "00_no_pyproject_toml"
    app.add(ReleaseCommand())

    command = app.find("release")
    tester = CommandTester(command)
    status_code = tester.execute(f"--origin {origin_dir}")
    assert status_code == os.EX_NOINPUT


def test_simple_project(fixtures_dir: Path, monkeypatch: MonkeyPatch):
    app = Application()
    origin_dir = fixtures_dir / "01_simple_project"
    app.add(ReleaseCommand())

    command = app.find("release")
    tester = CommandTester(command)
    with tempfile.TemporaryDirectory() as tmp_dir:
        status_code = tester.execute(f" --origin {origin_dir} --destination={tmp_dir}")
    assert status_code == os.EX_OK
