import os
import shutil
import subprocess
import tomllib
from pathlib import Path

from cleo.io.outputs.output import Verbosity
from pydantic import BaseModel
from pydantic import Field

from ndev.services.listener import Listener
from ndev.services.listener import NULL_LISTENER
from ndev.shutil_ext import copytree_from_zip


class CopyItem(BaseModel):
    origin: str = Field(alias="from")
    destination: str = Field(alias="to")
    ignores: list[str] = Field(default_factory=list)


class PackerSchema(BaseModel):
    from_dir: Path | None = None
    to_dir: Path | None = None

    release_root: str
    common_ignores: list[str] = Field(default_factory=list)
    copy_local: list[CopyItem] = Field(default_factory=list)
    copy_wheel_src: list[CopyItem] = Field(default_factory=list)
    copy_repo_src: list[CopyItem] = Field(default_factory=list)

    file_replace_prefix: str | None = Field(None)
    copy_requirements_txt: bool = Field(False)

    @staticmethod
    def load_from_dir(from_dir: Path) -> "PackerSchema":
        pyproject_toml = from_dir / "pyproject.toml"
        if not pyproject_toml.exists():
            raise FileNotFoundError(f"pyproject.toml not found in {from_dir}")

        project_dict = tomllib.loads(pyproject_toml.read_text(encoding="utf8"))
        if "tool" not in project_dict or "ndev" not in project_dict["tool"]:
            raise ValueError("ndev section not found in pyproject.toml")

        schema = PackerSchema(
            from_dir=from_dir,
            release_root=project_dict["tool"]["ndev"]["release_root"],
        )
        if "common_ignores" in project_dict["tool"]["ndev"]:
            schema.common_ignores = project_dict["tool"]["ndev"]["common_ignores"]
        if "copy_local" in project_dict["tool"]["ndev"]:
            schema.copy_local = [
                CopyItem(**item) for item in project_dict["tool"]["ndev"]["copy_local"]
            ]
        if "copy_wheel_src" in project_dict["tool"]["ndev"]:
            schema.copy_wheel_src = [
                CopyItem(**item) for item in project_dict["tool"]["ndev"]["copy_wheel_src"]
            ]
        if "copy_repo_src" in project_dict["tool"]["ndev"]:
            schema.copy_repo_src = [
                CopyItem(**item) for item in project_dict["tool"]["ndev"]["copy_repo_src"]
            ]
        return schema


class Packer:
    """
    Service that packs data according given schema
    """

    def __init__(self, schema: PackerSchema, listener: Listener = NULL_LISTENER) -> None:
        super().__init__()
        self.schema = schema
        self.out = listener

    def pack(self) -> int:
        if self.schema.from_dir is None:
            raise ValueError("from_dir is not set in schema")
        if self.schema.to_dir is None:
            raise ValueError("to_dir is not set in schema")

        self.copy_root()
        self.copy_local_files()
        self.generate_requirements_txt()
        self.download_wheels()
        self.copy_wheels_sources()
        self.copy_repo_sources()
        return os.EX_OK

    # -- public methods --

    def copy_root(self):
        self.out("Copying root directory.", verbosity=Verbosity.NORMAL.value)
        root_dir = self.schema.from_dir / self.schema.release_root
        if not root_dir.exists():
            self.out(f"Root directory {root_dir} does not exist.")
            return os.EX_NOINPUT

        # copy root_dir to TEMP_DIR
        shutil.copytree(
            src=root_dir,
            dst=self.schema.to_dir,
            dirs_exist_ok=True,
            ignore=shutil.ignore_patterns("__pycache__"),
            copy_function=shutil.copy2,
        )

    def copy_local_files(self):
        if not self.schema.copy_local:
            self.out("No local files to copy.", verbosity=Verbosity.VERY_VERBOSE.value)
            return

        self.out("Copying local files.", verbosity=Verbosity.NORMAL.value)

        for copy_item in self.schema.copy_local:
            self.out(
                message=f"Copying {copy_item.origin} to {copy_item.destination}.",
                verbosity=Verbosity.VERBOSE.value,
            )

            src_path = self.schema.from_dir / copy_item.origin
            if not src_path.exists():
                self.out(f"Local source {src_path} does not exist.")
                return os.EX_NOINPUT

            dst_path = self.schema.to_dir / copy_item.destination

            item_ignores = self.schema.common_ignores.copy()
            item_ignores += copy_item.ignores

            shutil.copytree(
                src=src_path,
                dst=dst_path,
                dirs_exist_ok=True,
                ignore=shutil.ignore_patterns(*item_ignores),
                copy_function=shutil.copy2,
            )

        if self.schema.file_replace_prefix:
            for path in self.schema.to_dir.rglob("*"):
                if path.is_file():
                    if path.name.startswith(self.schema.file_replace_prefix):
                        new_name = path.name.replace(self.schema.file_replace_prefix, "")
                        new_path = path.parent / new_name
                        shutil.move(path, new_path)

        return os.EX_OK

    def generate_requirements_txt(self):
        if not self.schema.copy_requirements_txt:
            self.out(
                message="copy_requirements = false. Skipping requirements.txt generation.",
                verbosity=Verbosity.VERBOSE.value,
            )
            return os.EX_OK

        self.out("Generating requirements.txt.", verbosity=Verbosity.NORMAL.value)
        requirements_path = self.schema.from_dir / "requirements.txt"
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
                self.out("Failed to generate requirements.txt.")
                self.out(result.stdout)
                self.out(result.stderr)
                return os.EX_NOINPUT
            else:
                # filter out index-url and empty lines
                requirement_lines = requirements_path.read_text(encoding="utf8").splitlines()
                requirement_lines = [
                    line
                    for line in requirement_lines
                    if (not line.startswith("--") and len(line) > 0)
                ]
                requirements_path.write_text("\n".join(requirement_lines))

        shutil.copy2(src=requirements_path, dst=self.schema.to_dir / "requirements.txt")

    def download_wheels(self):
        if not self.schema.copy_wheel_src:
            self.out(
                message="No 'copy-wheel-src' section in ndev configuration. Skipping wheels downloading.",
                verbosity=Verbosity.VERBOSE.value,
            )
            return

        self.out(message="Downloading wheels: ", verbosity=Verbosity.NORMAL.value)

        for copy_item in self.schema.copy_wheel_src:
            wheel_name = copy_item.origin
            wheel_name = wheel_name.replace("_", "-")
            requirement_spec = next(
                (line for line in self._get_requirements_txt_list() if f"{wheel_name}==" in line),
                None,
            )
            if ";" in requirement_spec:
                requirement_spec = requirement_spec.split(";")[0]
            self.out(
                message=f"Downloading wheel: {wheel_name}, spec: {requirement_spec}",
                verbosity=Verbosity.VERBOSE.value,
            )
            if requirement_spec is None:
                self.out(f"Requirement {copy_item['from']} not found in requirements.txt.")
                return os.EX_NOINPUT

            wheels_dir = self._get_wheels_dir()
            result = subprocess.run(
                f"pip download "
                "--no-deps "
                "--ignore-requires-python "
                "--exists-action i "
                "--platform manylinux_2_28_x86_64 "
                f" {requirement_spec} "
                f'--dest "{wheels_dir}" ',
                capture_output=True,
                text=True,
                shell=True,
            )

            if result.returncode != os.EX_OK:
                self.out(f"Failed to download wheels. Status: {result.returncode}")
                self.out(f"stdout: [{result.stdout}]")
                self.out(f"stderr: [{result.stderr}]")
                return result.returncode
            else:
                self.out(
                    message=f"Downloaded wheel: {wheel_name}, spec: {requirement_spec}, "
                    f"stdout: {result.stdout}, stderr: {result.stderr}",
                    verbosity=Verbosity.VERY_VERBOSE.value,
                )

    def copy_wheels_sources(self) -> int:
        if not self.schema.copy_wheel_src:
            self.out(
                message="No 'copy-wheel-src' section in ndev configuration. Skipping wheel sources copying.",
                verbosity=Verbosity.VERBOSE.value,
            )
            return os.EX_OK
        self.out(
            message=f"Copying wheel sources to {self.schema.to_dir}.",
            verbosity=Verbosity.NORMAL.value,
        )
        wheels_dir = self._get_wheels_dir()
        all_wheels_files = list(wheels_dir.glob("*.whl")) + list(wheels_dir.glob("*.tar.gz"))

        for copy_item in self.schema.copy_wheel_src:
            self.out(
                message=f"Copying wheel {copy_item.origin} to {copy_item.destination}.",
                verbosity=Verbosity.VERBOSE.value,
            )
            wheel_file = next(
                (f for f in all_wheels_files if f.name.startswith(copy_item.origin + "-")),
                None,
            )
            self.out(
                message=f"Copying {wheel_file} to {self.schema.to_dir / copy_item.destination}.",
                verbosity=Verbosity.VERBOSE.value,
            )
            copytree_from_zip(
                zip_path=wheel_file,
                dst_dir=self.schema.to_dir / copy_item.destination,
                path_in_zip=copy_item.origin,
                ignore=shutil.ignore_patterns("*.so"),
            )

    def copy_repo_sources(self):
        if not self.schema.copy_repo_src:
            self.out(
                message="No 'copy-repo-src' section in ndev configuration. Skipping repo sources copying.",
                verbosity=Verbosity.VERBOSE.value,
            )
            return os.EX_OK

        self.out(message="Copying repo sources.", verbosity=Verbosity.NORMAL.value)

        for copy_item in self.schema.copy_repo_src:
            self.out(
                message=f"Copying repo source {copy_item.origin} to {copy_item.destination}.",
                verbosity=Verbosity.VERBOSE.value,
            )

    # -- private methods --

    def _get_requirements_txt_list(self) -> list[str]:
        requirements_path = self.schema.from_dir / "requirements.txt"
        if not requirements_path.exists():
            return []
        return requirements_path.read_text(encoding="utf8").splitlines()

    def _get_wheels_dir(self) -> Path:
        return self.schema.to_dir.parent / "_wheels"
