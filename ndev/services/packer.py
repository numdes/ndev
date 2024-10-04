import os
import shutil
import subprocess
import tempfile
import tomllib
from fnmatch import fnmatch
from pathlib import Path

from cleo.io.outputs.output import Verbosity
from pydantic import BaseModel
from pydantic import Field

from ndev.services.listener import Listener
from ndev.services.listener import NULL_LISTENER
from ndev.shutil_ext import copytree_from_zip

_SKIP_NUKE_DIRS = {".git", ".idea"}
_BASE_WHEEL_IGNORES = ["*.so", "*.dist-info", "*.so.*", "*.libs"]


class CopyItem(BaseModel):
    origin: str = Field(alias="from")
    destination: str = Field(alias="to")
    ignores: list[str] = Field(default_factory=list)

    ref: str | None = None


class PackerSchema(BaseModel):
    origin: str | Path | None = None
    destination_dir: Path | None = None
    destination_repo: str | None = None

    release_root: str
    common_ignores: list[str] = Field(default_factory=list)
    copy_local: list[CopyItem] = Field(default_factory=list)
    copy_wheel_src: list[CopyItem] = Field(default_factory=list)
    copy_repo_src: list[CopyItem] = Field(default_factory=list)

    file_replace_prefix: str | None = Field(None)
    copy_requirements_txt: bool = Field(False)
    filter_requirements_txt_matches: list[str] = Field(default_factory=list)
    add_version_json: bool = Field(False)
    version_str: str | None = Field(None)

    author_email: str | None = Field(None)
    author_name: str | None = Field(None)

    @staticmethod
    def load_from_dir(from_dir: Path) -> "PackerSchema":
        pyproject_toml = from_dir / "pyproject.toml"
        if not pyproject_toml.exists():
            raise FileNotFoundError(f"pyproject.toml not found in {from_dir}")

        project_dict = tomllib.loads(pyproject_toml.read_text(encoding="utf8"))
        if "tool" not in project_dict or "ndev" not in project_dict["tool"]:
            raise ValueError("ndev section not found in pyproject.toml")

        schema = PackerSchema(
            origin=from_dir,
            release_root=project_dict["tool"]["ndev"]["release-root"],
        )
        if "copy-requirements" in project_dict["tool"]["ndev"]:
            schema.copy_requirements_txt = project_dict["tool"]["ndev"]["copy-requirements"]
        if "file-replace-prefix" in project_dict["tool"]["ndev"]:
            schema.file_replace_prefix = project_dict["tool"]["ndev"]["file-replace-prefix"]
        if "common-ignores" in project_dict["tool"]["ndev"]:
            schema.common_ignores = project_dict["tool"]["ndev"]["common-ignores"]
        if "copy-local" in project_dict["tool"]["ndev"]:
            schema.copy_local = [
                CopyItem(**item) for item in project_dict["tool"]["ndev"]["copy-local"]
            ]
        if "copy-wheel-src" in project_dict["tool"]["ndev"]:
            schema.copy_wheel_src = [
                CopyItem(**item) for item in project_dict["tool"]["ndev"]["copy-wheel-src"]
            ]
        if "copy-repo-src" in project_dict["tool"]["ndev"]:
            schema.copy_repo_src = [
                CopyItem(**item) for item in project_dict["tool"]["ndev"]["copy-repo-src"]
            ]
        if "add-version-json" in project_dict["tool"]["ndev"]:
            schema.add_version_json = project_dict["tool"]["ndev"]["add-version-json"]
            if "tool" in project_dict and "poetry" in project_dict["tool"]:
                schema.version_str = project_dict["tool"]["poetry"]["version"]
            if "project" in project_dict and "version" in project_dict["project"]:
                schema.version_str = project_dict["project"]["version"]
        if "filter-requirements-txt-matches" in project_dict["tool"]["ndev"]:
            schema.filter_requirements_txt_matches = project_dict["tool"]["ndev"][
                "filter-requirements-txt-matches"
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
        self.wheels_dir = tempfile.TemporaryDirectory()

    def pack(self) -> int:
        if self.schema.origin is None:
            raise ValueError("origin is not set in schema")
        if self.schema.destination_dir is None and self.schema.destination_repo is None:
            raise ValueError("both dir and repo is not set")
        _destination_temp_dir = None
        if self.schema.destination_dir is None:
            _destination_temp_dir = tempfile.TemporaryDirectory()
            self.schema.destination_dir = Path(_destination_temp_dir.name)
            result = subprocess.run(
                f"git clone {self.schema.destination_repo} {self.schema.destination_dir}",
                shell=True,
                capture_output=True,
                text=True,
            )
            if result.returncode != os.EX_OK:
                self.out(f"Failed to clone {self.schema.destination_repo}.")
                self.out(result.stdout)
                self.out(result.stderr)
                return result.returncode
            result = subprocess.run(
                f"cd {self.schema.destination_dir} && git checkout -b 'prepare_release_{self.schema.version_str}'",
                shell=True,
                capture_output=True,
                text=True,
            )
            if result.returncode != os.EX_OK:
                self.out(f"Failed to create branch prepare_release_{self.schema.version_str}.")
                self.out(result.stdout)
                self.out(result.stderr)
                return result.returncode

        # remove all files and dirs from to_dir except .git
        for path in self.schema.destination_dir.glob("*"):
            if path.name not in _SKIP_NUKE_DIRS:
                if path.is_file():
                    path.unlink()
                else:
                    shutil.rmtree(path)

        self.copy_root()
        self.copy_local_files()
        self.generate_requirements_txt()
        self.download_wheels()
        self.copy_wheels_sources()
        self.copy_repo_sources()
        self.add_version_json()

        if self.schema.destination_repo is not None:
            if self.schema.author_email is None or self.schema.author_name is None:
                self.out("Author email and name are not set.")
                return os.EX_NOINPUT
            result = subprocess.run(
                f"cd {self.schema.destination_dir} && "
                f"git config user.email '{self.schema.author_email}' && "
                f"git config user.name '{self.schema.author_name}' && "
                f"git add . && "
                f"git commit -m 'Release {self.schema.version_str}' && "
                f"git push --set-upstream origin prepare_release_{self.schema.version_str}",
                shell=True,
                capture_output=True,
                text=True,
            )
            if result.returncode != os.EX_OK:
                self.out("Failed to commit changes.")
                self.out(result.stdout)
                self.out(result.stderr)
                return result.returncode

        if _destination_temp_dir is not None:
            _destination_temp_dir.cleanup()

        return os.EX_OK

    # -- public methods --

    def copy_root(self):
        self.out("Copying root directory.", verbosity=Verbosity.NORMAL.value)
        root_dir = self.schema.origin / self.schema.release_root
        if not root_dir.exists():
            self.out(f"Root directory {root_dir} does not exist.")
            return os.EX_NOINPUT

        # copy root_dir to TEMP_DIR
        shutil.copytree(
            src=root_dir,
            dst=self.schema.destination_dir,
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

            src_path = self.schema.origin / copy_item.origin
            if not src_path.exists():
                self.out(f"Local source {src_path} does not exist.")
                return os.EX_NOINPUT

            dst_path = self.schema.destination_dir / copy_item.destination

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
            for path in self.schema.destination_dir.rglob("*"):
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
        requirements_path = self.schema.origin / "requirements.txt"
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
                cwd=self.schema.origin,
            )
            if not requirements_path.exists() or result.returncode != os.EX_OK:
                self.out("Failed to generate requirements.txt.")
                self.out(result.stdout)
                self.out(result.stderr)
                return os.EX_NOINPUT

        # filter out index-url and empty lines
        requirement_lines = requirements_path.read_text(encoding="utf8").splitlines()
        _filtered_lines = []
        for line in requirement_lines:
            if len(line.strip()) == 0:
                continue
            good_line = True
            for match in self.schema.filter_requirements_txt_matches:
                if fnmatch(line, match):
                    good_line = False
                    break
            if good_line:
                _filtered_lines.append(line)
        (self.schema.destination_dir / "requirements.txt").write_text("\n".join(_filtered_lines))

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

            result = subprocess.run(
                f"pip download "
                "--no-deps "
                "--ignore-requires-python "
                "--exists-action i "
                "--platform manylinux_2_28_x86_64 "
                f" {requirement_spec} "
                f'--dest "{self.wheels_dir.name}" ',
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
            message=f"Copying wheel sources to {self.schema.destination_dir}.",
            verbosity=Verbosity.NORMAL.value,
        )
        wheels_dir_path = Path(self.wheels_dir.name)
        all_wheels_files = list(wheels_dir_path.glob("*.whl")) + list(
            wheels_dir_path.glob("*.tar.gz")
        )

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
                message=f"Copying {wheel_file} to {self.schema.destination_dir / copy_item.destination}.",
                verbosity=Verbosity.VERBOSE.value,
            )
            _ignores = _BASE_WHEEL_IGNORES.copy()
            _ignores += copy_item.ignores
            copytree_from_zip(
                zip_path=wheel_file,
                dst_dir=self.schema.destination_dir / copy_item.destination,
                path_in_zip=".",
                ignore=shutil.ignore_patterns(*_ignores),
            )
        self.wheels_dir.cleanup()

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
            repo_url, repo_ref = copy_item.origin, copy_item.ref
            with tempfile.TemporaryDirectory() as tmp_dir:
                result = subprocess.run(
                    f"git clone --branch {repo_ref} --depth 1 {repo_url} {tmp_dir}",
                    shell=True,
                    capture_output=True,
                    text=True,
                )
                if result.returncode != os.EX_OK:
                    self.out(f"Failed to clone repo {repo_url}.")
                    self.out(result.stdout)
                    self.out(result.stderr)
                    return result.returncode

                schema = PackerSchema.load_from_dir(Path(tmp_dir))
                schema.destination_dir = self.schema.destination_dir / copy_item.destination
                schema.copy_repo_src = []  # prevent recursion
                packer = Packer(
                    schema=schema,
                    listener=self.out,
                )
                packer.pack()

    def add_version_json(self):
        if not self.schema.add_version_json:
            self.out(
                message="add-version-json = false. Skipping version.json generation.",
                verbosity=Verbosity.VERBOSE.value,
            )
            return os.EX_OK

        self.out("Generating version.json.", verbosity=Verbosity.NORMAL.value)

        version_json = self.schema.destination_dir / "version.json"
        major, minor, patch = self.schema.version_str.split(".")
        version_json.write_text(
            f"""{{
  "SemVer": "{self.schema.version_str}",
  "Major": {major},
  "Minor": {minor},
  "Patch": {patch}
}}"""
        )

    # -- private methods --

    def _get_requirements_txt_list(self) -> list[str]:
        requirements_path = self.schema.origin / "requirements.txt"
        if not requirements_path.exists():
            return []
        return requirements_path.read_text(encoding="utf8").splitlines()
