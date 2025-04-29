import tempfile

from pathlib import Path

from _pytest.monkeypatch import MonkeyPatch
from cleo.application import Application
from cleo.testers.command_tester import CommandTester

from ndev.commands.release import ReleaseCommand


def test_files_patching(fixtures_dir: Path, monkeypatch: MonkeyPatch) -> None:
    project_path = fixtures_dir / "21_patch_files"

    assert project_path.exists()
    assert project_path.is_dir()

    monkeypatch.chdir(project_path)
    assert Path.cwd() == project_path

    # Check all files in project directory
    for file_path in project_path.rglob("*"):
        if file_path.is_file():
            content = file_path.read_text()

            # Check no PLACEHOLDER exists except in pyproject.toml
            if file_path.name != "pyproject.toml":
                assert "PLACEHOLDER" not in content, f"Found PLACEHOLDER in {file_path}"

    app = Application()
    app.add(ReleaseCommand())
    command = app.find("release")
    tester = CommandTester(command)

    # Create temporary directory and run release command

    with tempfile.TemporaryDirectory() as temp_dir:
        tester.execute(f"--destination {temp_dir}")

        # Check all Python files in temp directory have no URLs after patching
        for file_path in Path(temp_dir).rglob("*.py"):
            assert file_path.is_file()
            content = file_path.read_text()

            assert "http://" not in content
            assert "https://" not in content
