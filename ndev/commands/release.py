import os
import shutil
import subprocess
import tomllib
from pathlib import Path
from typing import Any

from cleo.commands.command import Command
from cleo.io.outputs.output import Verbosity

from ndev.shutil_ext import copytree_from_zip

SOURCES_DIR = Path(os.getenv("TEMP_DIR", "/tmp")) / "dist-sources"
WHEELS_DIR = Path(os.getenv("TEMP_DIR", "/tmp")) / "dist-wheels"
CURRENT_DIR = Path.cwd()


class ReleaseCommand(Command):
    name = "release"

    def __init__(self) -> None:
        super().__init__()
        self.ndev_config: dict[str, Any] = {}
        self.project_file = CURRENT_DIR / "pyproject.toml"
        self.requirements_txt_list: list[str] = []

    def handle(self) -> int:
        self._validate_env()
        self.ndev_config = self.load_ndev_config()
        self.copy_root()
        self.copy_local_files()
        self.generate_requirements_txt()
        self.download_wheels()
        self.copy_wheels_sources()
        return os.EX_OK

    def load_ndev_config(self):
        _project_dict = tomllib.loads(self.project_file.read_text(encoding="utf8"))
        self._validate_settings(_project_dict)
        return _project_dict["tool"]["ndev"]

    def copy_root(self):
        self.line("Copying root directory.", verbosity=Verbosity.NORMAL)
        root_dir = CURRENT_DIR / self.ndev_config["release_root"]
        if not root_dir.exists():
            self.line_error(f"Root directory {root_dir} does not exist.")
            return os.EX_NOINPUT

        # copy root_dir to TEMP_DIR
        shutil.copytree(
            src=root_dir,
            dst=SOURCES_DIR,
            dirs_exist_ok=True,
            ignore=shutil.ignore_patterns("__pycache__"),
            copy_function=shutil.copy2,
        )

    def copy_local_files(self):
        self.line("Copying local files.", verbosity=Verbosity.NORMAL)
        for copy_item in self.ndev_config["copy-local"]:
            self.line(
                f"Copying {copy_item['from']} to {copy_item['to']}.", verbosity=Verbosity.VERBOSE
            )

            src_path = CURRENT_DIR / copy_item["from"]
            if not src_path.exists():
                self.line_error(f"Local source {src_path} does not exist.")
                return os.EX_NOINPUT

            dst_path = SOURCES_DIR / copy_item["to"]
            shutil.copytree(
                src=src_path,
                dst=dst_path,
                dirs_exist_ok=True,
                ignore=shutil.ignore_patterns("__pycache__"),
                copy_function=shutil.copy2,
            )

    def generate_requirements_txt(self):
        self.line("Generating requirements.txt.", verbosity=Verbosity.NORMAL)
        requirements_path = CURRENT_DIR / "requirements.txt"
        if not requirements_path.exists():
            result = subprocess.run(
                "poetry export "
                "--without-hashes "
                "--with dev "
                "--format requirements.txt "
                "--output requirements.txt",
                shell=True,
                capture_output=True,
                text=True,
            )
            if not requirements_path.exists() or result.returncode != os.EX_OK:
                self.line_error("Failed to generate requirements.txt.")
                self.line_error(result.stdout)
                self.line_error(result.stderr)
                return os.EX_NOINPUT
            else:
                requirement_lines = requirements_path.read_text(encoding="utf8").splitlines()
                requirement_lines = [
                    line
                    for line in requirement_lines
                    if (not line.startswith("--") and len(line) > 0)
                ]
                requirements_path.write_text("\n".join(requirement_lines))
        if self.ndev_config["copy_requirements"]:
            shutil.copy2(src=requirements_path, dst=SOURCES_DIR / "requirements.txt")

        self.requirements_txt_list = requirements_path.read_text(encoding="utf8").splitlines()

    def download_wheels(self):
        self.line(text="Downloading wheels: ", verbosity=Verbosity.NORMAL)

        for copy_item in self.ndev_config["copy-wheel-src"]:
            wheel_name = copy_item["from"]
            wheel_name = wheel_name.replace("_", "-")
            requirement_spec = next(
                (line for line in self.requirements_txt_list if f"{wheel_name}==" in line),
                None,
            )
            if ";" in requirement_spec:
                requirement_spec = requirement_spec.split(";")[0]
            self.line(
                f"Downloading wheel: {wheel_name}, spec: {requirement_spec}",
                verbosity=Verbosity.VERBOSE,
            )
            if requirement_spec is None:
                self.line_error(f"Requirement {copy_item['from']} not found in requirements.txt.")
                return os.EX_NOINPUT

            result = subprocess.run(
                f"pip download "
                "--no-deps "
                "--ignore-requires-python "
                "--exists-action i "
                "--platform manylinux_2_28_x86_64 "
                f" {requirement_spec} "
                f'--dest "{WHEELS_DIR}" ',
                capture_output=True,
                text=True,
                shell=True,
            )

            if result.returncode != os.EX_OK:
                self.line_error(f"Failed to download wheels. Status: {result.returncode}")
                self.line_error(f"stdout: [{result.stdout}]")
                self.line_error(f"stderr: [{result.stderr}]")
                return result.returncode

            if self.io.is_verbose():
                self.line(result.stderr)
                self.line(result.stdout)

    def copy_wheels_sources(self):
        self.line(text=f"Copying wheel sources to {SOURCES_DIR}.", verbosity=Verbosity.NORMAL)
        all_wheels_files = list(WHEELS_DIR.glob("*.whl")) + list(WHEELS_DIR.glob("*.tar.gz"))

        for copy_item in self.ndev_config["copy-wheel-src"]:
            self.line(
                f"Copying wheel {copy_item['from']} to {copy_item['to']}.",
                verbosity=Verbosity.VERBOSE,
            )
            wheel_file = next(
                (f for f in all_wheels_files if f.name.startswith(copy_item["from"] + "-")),
                None,
            )
            self.line(
                f"Copying {wheel_file} to {SOURCES_DIR / copy_item['to']}.",
                verbosity=Verbosity.VERBOSE,
            )
            copytree_from_zip(
                zip_path=wheel_file,
                dst_dir=SOURCES_DIR / copy_item["to"],
                path_in_zip=copy_item["from"],
                ignore=shutil.ignore_patterns("*.so"),
            )

    def _validate_env(self):
        if not self.project_file.exists():
            self.line_error(f"Project file {self.project_file} is not found.")
            return os.EX_NOINPUT

    def _validate_settings(self, project_dict):
        if "tool" not in project_dict:
            self.line_error("No 'tool' section in pyproject.toml.")
            return os.EX_DATAERR
        if "ndev" not in project_dict["tool"]:
            self.line_error("No 'ndev' section in pyproject.toml.")
            return os.EX_DATAERR
