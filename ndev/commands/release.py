import os
import tomllib
from pathlib import Path

from cleo.commands.command import Command


class ReleaseCommand(Command):
    name = "release"

    def handle(self) -> int:
        cur_dir = Path.cwd()
        project_file = cur_dir / "pyproject.toml"
        if not project_file.exists():
            self.line_error(f"Project file {project_file} is not found.")
            return os.EX_NOINPUT

        project_dict = tomllib.loads(project_file.read_text(encoding="utf8"))
        if "tool" not in project_dict:
            self.line_error(
                f"Project file {project_file} does not contain a [tool] section."
            )
            return os.EX_NOINPUT
        if "ndev" not in project_dict["tool"]:
            self.line_error(
                f"Project file {project_file} does not contain a [tool.ndev] section."
            )
            return os.EX_NOINPUT
        return os.EX_OK
