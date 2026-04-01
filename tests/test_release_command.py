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
    assert status_code == os.EX_USAGE


def test_plain_dirs(fixtures_dir: Path) -> None:
    """Scenario #02: releasing a dir with files and subdirs produces the same structure."""
    app = Application()
    fixture = fixtures_dir / "02_plain_dirs"
    expected_dir = fixture / "dst"

    app.add(ReleaseCommand())
    command = app.find("release")
    tester = CommandTester(command)

    with tempfile.TemporaryDirectory() as tmp_dir:
        status_code = tester.execute(f"--src {fixture} --dst {tmp_dir}")
        assert status_code == os.EX_OK

        actual = tmp_dir
        for expected_file in expected_dir.rglob("*"):
            if expected_file.is_dir():
                continue
            rel = expected_file.relative_to(expected_dir)
            actual_file = Path(actual) / rel
            assert actual_file.exists(), f"missing {rel}"
            assert actual_file.read_text() == expected_file.read_text(), f"content mismatch {rel}"

        # no extra files
        actual_files = {p.relative_to(actual) for p in Path(actual).rglob("*") if p.is_file()}
        expected_files = {
            p.relative_to(expected_dir) for p in expected_dir.rglob("*") if p.is_file()
        }
        assert actual_files == expected_files


def test_plain_dirs_no_pyproject(fixtures_dir: Path) -> None:
    """Scenario #03: same as #02 but source has no pyproject.toml — copies tree as-is."""
    app = Application()
    fixture = fixtures_dir / "03_plain_dirs_no_pyproject"
    src_dir = fixture / "src"
    expected_dir = fixture / "dst"

    app.add(ReleaseCommand())
    command = app.find("release")
    tester = CommandTester(command)

    with tempfile.TemporaryDirectory() as tmp_dir:
        status_code = tester.execute(f"--src {src_dir} --dst {tmp_dir}")
        assert status_code == os.EX_OK

        actual = tmp_dir
        for expected_file in expected_dir.rglob("*"):
            if expected_file.is_dir():
                continue
            rel = expected_file.relative_to(expected_dir)
            actual_file = Path(actual) / rel
            assert actual_file.exists(), f"missing {rel}"
            assert actual_file.read_text() == expected_file.read_text(), f"content mismatch {rel}"

        actual_files = {p.relative_to(actual) for p in Path(actual).rglob("*") if p.is_file()}
        expected_files = {
            p.relative_to(expected_dir) for p in expected_dir.rglob("*") if p.is_file()
        }
        assert actual_files == expected_files


def test_common_ignores(fixtures_dir: Path) -> None:
    """Scenario #05: files matching common-ignores patterns are excluded from destination."""
    app = Application()
    fixture = fixtures_dir / "05_common_ignores"

    app.add(ReleaseCommand())
    command = app.find("release")
    tester = CommandTester(command)

    with tempfile.TemporaryDirectory() as tmp_dir:
        status_code = tester.execute(f"--src {fixture} --dst {tmp_dir}")
        assert status_code == os.EX_OK

        dst = Path(tmp_dir)
        # kept
        assert (dst / "keep.txt").exists()
        assert (dst / "subdir" / "nested.txt").exists()
        # ignored by *.log
        assert not (dst / "debug.log").exists(), "*.log should be ignored"
        assert not (dst / "subdir" / "trace.log").exists(), "nested *.log should be ignored"
        # ignored by exact name
        assert not (dst / "secret.txt").exists(), "secret.txt should be ignored"


def test_ignore_git_dir(fixtures_dir: Path) -> None:
    """Scenario #04: .git directory in source must not appear in destination."""
    app = Application()
    app.add(ReleaseCommand())
    command = app.find("release")
    tester = CommandTester(command)

    with tempfile.TemporaryDirectory() as src_dir, tempfile.TemporaryDirectory() as dst_dir:
        src = Path(src_dir)
        (src / "file.txt").write_text("hello")
        (src / "subdir").mkdir()
        (src / "subdir" / "nested.txt").write_text("nested")
        git_dir = src / ".git"
        git_dir.mkdir()
        (git_dir / "HEAD").write_text("ref: refs/heads/main")

        status_code = tester.execute(f"--src {src_dir} --dst {dst_dir}")
        assert status_code == os.EX_OK

        dst = Path(dst_dir)
        assert (dst / "file.txt").read_text() == "hello"
        assert (dst / "subdir" / "nested.txt").read_text() == "nested"
        assert not (dst / ".git").exists(), ".git should not be copied to destination"


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
