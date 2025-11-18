import os
import re
import shutil
import subprocess
import tempfile
import tomllib

from functools import partial
from pathlib import Path

from cleo.io.outputs.output import Verbosity
from pydantic import BaseModel
from pydantic import Field

from ndev.protocols.listener import NULL_LISTENER
from ndev.protocols.listener import Listener
from ndev.services.releaser.requirements import add_dependencies_to_pyproject_toml
from ndev.services.releaser.requirements import filter_requirements_txt
from ndev.services.releaser.requirements import get_requirements_txt
from ndev.shutil_ext import copytree_from_zip


_SKIP_NUKE_DIRS = {".git", ".idea"}
_BASE_WHEEL_IGNORES = ["*.so", "*.dist-info", "*.so.*", "*.libs"]


class CopyItem(BaseModel):
    origin: str = Field(alias="from")
    destination: str = Field(alias="to")
    ignores: list[str] = Field(default_factory=list)

    ref: str | None = None
    package_name: str | None = None
    platform: str | None = None


class PatchItem(BaseModel):
    glob: str = Field(title="Glob Pattern", description="The glob pattern to match files.")
    regex: str = Field(
        title="Regular Expression", description="The regular expression to search for in files."
    )
    subst: str = Field(
        title="Substitution String", description="The string to replace matches of the regex."
    )


class ReleaserConf(BaseModel):
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
    manage_pyproject: bool = Field(False)
    generate_poetry_lock: bool = Field(False)
    remove_todo: bool = Field(False)
    filter_requirements_txt_matches: list[str] = Field(default_factory=list)
    install_dependencies_with_groups: list[str] = Field(default_factory=list)
    patches: list[PatchItem] = Field(default_factory=list)
    add_version_json: bool = Field(False)
    version_str: str | None = Field(None)

    author_email: str | None = Field(None)
    author_name: str | None = Field(None)

    @staticmethod
    def load_from_dir(from_dir: Path) -> "ReleaserConf":
        pyproject_toml = from_dir / "pyproject.toml"
        if not pyproject_toml.exists():
            raise FileNotFoundError(f"pyproject.toml not found in {from_dir}")

        project_dict = tomllib.loads(pyproject_toml.read_text(encoding="utf8"))
        if "tool" not in project_dict or "ndev" not in project_dict["tool"]:
            print(pyproject_toml.read_text(encoding="utf8"))
            raise ValueError(f"ndev section not found in pyproject.toml, path: {from_dir}")

        schema = ReleaserConf(
            origin=from_dir,
            release_root=project_dict["tool"]["ndev"]["release-root"],
        )
        if "copy-requirements" in project_dict["tool"]["ndev"]:
            schema.copy_requirements_txt = project_dict["tool"]["ndev"]["copy-requirements"]
        if "manage-pyproject" in project_dict["tool"]["ndev"]:
            schema.manage_pyproject = project_dict["tool"]["ndev"]["manage-pyproject"]
        if "generate-poetry-lock" in project_dict["tool"]["ndev"]:
            schema.generate_poetry_lock = project_dict["tool"]["ndev"]["generate-poetry-lock"]
        if "remove-todo" in project_dict["tool"]["ndev"]:
            schema.remove_todo = project_dict["tool"]["ndev"]["remove-todo"]
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
        if "install-dependencies-with-groups" in project_dict["tool"]["ndev"]:
            schema.install_dependencies_with_groups = project_dict["tool"]["ndev"][
                "install-dependencies-with-groups"
            ]
        if "patches" in project_dict["tool"]["ndev"]:
            schema.patches = [PatchItem(**item) for item in project_dict["tool"]["ndev"]["patches"]]
        return schema


class Releaser:
    """
    Service that packs data according given schema
    """

    def __init__(self, schema: ReleaserConf, listener: Listener = NULL_LISTENER) -> None:
        super().__init__()
        self.schema = schema
        self.out = listener
        self.wheels_dir = tempfile.TemporaryDirectory()

    def pack(self) -> int:  # noqa: PLR0911 many returns is ok here
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
                check=False,
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
                check=False,
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

        if (_ret_code := self.manage_requirements()) != os.EX_OK:
            self.out(f"Failed to generate requirements.txt. Return code: {_ret_code}")
            return _ret_code

        if (_ret_code := self.download_wheels()) != os.EX_OK:
            self.out(f"Failed to make release. Status code: {_ret_code}.")
            return _ret_code

        if (_ret_code := self.copy_wheels_sources()) != os.EX_OK:
            self.out(f"Failed to copy wheel sources. Return code: {_ret_code}")
            return _ret_code

        if (_ret_code := self.copy_repo_sources()) != os.EX_OK:
            self.out(f"Failed to copy repo sources. Return code: {_ret_code}")
            return _ret_code

        if (_ret_code := self.remove_todo()) != os.EX_OK:
            self.out(f"Failed to remove TODOs. Return code: {_ret_code}")
            return _ret_code

        if (_ret_code := self.add_version()) != os.EX_OK:
            self.out(f"Failed to add version. Return code: {_ret_code}")
            return _ret_code

        self.apply_patches()
        self.generate_poetry_lock()

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
                check=False,
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

            if src_path.is_file():
                os.makedirs(dst_path, exist_ok=True)
                shutil.copy2(src_path, dst_path)
            else:
                shutil.copytree(
                    src=src_path,
                    dst=dst_path,
                    dirs_exist_ok=True,
                    ignore=shutil.ignore_patterns(*item_ignores),
                    copy_function=shutil.copy2,
                )

        if self.schema.file_replace_prefix:
            for path in self.schema.destination_dir.rglob("*"):
                if path.is_file() and path.name.startswith(self.schema.file_replace_prefix):
                    new_name = path.name.replace(self.schema.file_replace_prefix, "")
                    new_path = path.parent / new_name
                    shutil.move(path, new_path)

        return os.EX_OK

    def manage_requirements(self) -> int:
        if not self.schema.copy_requirements_txt and not self.schema.manage_pyproject:
            self.out(
                message="Management of requirements is not required. Skipping",
                verbosity=Verbosity.VERBOSE.value,
            )
            return os.EX_OK

        requirements_txt = get_requirements_txt(
            working_dir=self.schema.origin, groups=self.schema.install_dependencies_with_groups
        )
        filtered_requirements_txt = filter_requirements_txt(
            requirements_txt=requirements_txt,
            filtered_matches=self.schema.filter_requirements_txt_matches,
        )

        if self.schema.copy_requirements_txt:
            (self.schema.destination_dir / "requirements.txt").write_text(filtered_requirements_txt)

        if self.schema.manage_pyproject:
            pyproject_toml = (
                self.schema.origin / self.schema.release_root / "pyproject.toml"
            ).read_text()
            pyproject_toml = add_dependencies_to_pyproject_toml(
                pyproject_toml=pyproject_toml,
                requirements_txt=filtered_requirements_txt,
            )
            (self.schema.destination_dir / "pyproject.toml").write_text(pyproject_toml)
        return os.EX_OK

    def remove_todo(self):
        if not self.schema.remove_todo:
            self.out(
                message="remove_todo = false. Skipping todo removing.",
                verbosity=Verbosity.VERBOSE.value,
            )
            return os.EX_OK

        self.out(message="removing todo", verbosity=Verbosity.NORMAL.value)

        for root, _, files in os.walk(self.schema.destination_dir):
            for filename in filter(lambda x: x.endswith(".py"), files):
                filepath = os.path.join(root, filename)
                with open(filepath, encoding="utf-8") as file:
                    lines = file.readlines()

                with open(filepath, "w", encoding="utf-8") as file:
                    sub = partial(re.sub, r"(#.*)TODO.*$", r"\1")
                    file.writelines(list(map(sub, lines)))

    def download_wheels(self):
        if not self.schema.copy_wheel_src:
            self.out(
                message="No 'copy-wheel-src' section in ndev configuration. Skipping wheels downloading.",
                verbosity=Verbosity.VERBOSE.value,
            )
            return os.EX_OK

        self.out(message="Downloading wheels: ", verbosity=Verbosity.NORMAL.value)

        for copy_item in self.schema.copy_wheel_src:
            wheel_name = copy_item.origin
            wheel_name = wheel_name.replace("_", "-")
            self.out(message=f"Downloading wheel: {wheel_name}", verbosity=Verbosity.VERBOSE.value)
            requirement_spec = next(
                (line for line in self._get_requirements_txt_list() if f"{wheel_name}==" in line),
                None,
            )
            if requirement_spec is None:
                self.out(
                    message=f"ERROR: wheel {wheel_name} is not found in requirements.txt.",
                    verbosity=Verbosity.NORMAL.value,
                )
                return os.EX_UNAVAILABLE

            if ";" in requirement_spec:
                requirement_spec = requirement_spec.split(";")[0]
            self.out(
                message=f"Downloading wheel: {wheel_name}, spec: {requirement_spec}",
                verbosity=Verbosity.VERBOSE.value,
            )
            if requirement_spec is None:
                self.out(f"Requirement {copy_item['from']} not found in requirements.txt.")
                return os.EX_NOINPUT

            platform = f"--platform {copy_item.platform}" if copy_item.platform else ""
            command = (
                f"pip download "
                "--no-deps "
                "--disable-pip-version-check "
                "--ignore-requires-python "
                "--exists-action i "
                f"{platform} "
                f" {requirement_spec} "
                f'--dest "{self.wheels_dir.name}" '
            )
            result = subprocess.run(
                command,
                capture_output=True,
                text=True,
                shell=True,
                check=False,
            )

            if result.returncode != os.EX_OK:
                self.out(f"Failed to download wheels. Status: {result.returncode}")
                self.out(f"Command: [{command}]")
                self.out(f"stdout: [{result.stdout.strip()}]")
                self.out(f"stderr: [{result.stderr.strip()}]")
                return result.returncode
            else:
                self.out(
                    message=f"Downloaded wheel: [{wheel_name}]\n"
                    f"spec: [{requirement_spec}]\n"
                    f"stdout: [{result.stdout}]\n"
                    f"stderr: [{result.stderr}]",
                    verbosity=Verbosity.VERY_VERBOSE.value,
                )

        return os.EX_OK

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
            if wheel_file is None:
                self.out(
                    f"Wheel {copy_item.origin} not found in downloaded wheels: {all_wheels_files}."
                )
                return os.EX_NOINPUT

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
        return os.EX_OK

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

            repo_url, repo_ref, package_name = (
                copy_item.origin,
                copy_item.ref,
                copy_item.package_name,
            )
            if package_name:
                package_name_dep = package_name.replace("_", "-")
                requirement_line = next(
                    x for x in self._get_requirements_txt_list() if f"{package_name_dep}==" in x
                )
                if not requirement_line:
                    self.out(f"Failed to find requirement {package_name_dep}.")
                    return os.EX_NOINPUT
                requirement_spec = requirement_line.split(";")[0].strip()
                package_version = requirement_spec.split("==")[1]
                repo_ref = repo_ref.replace("$NAME$", package_name)
                repo_ref = repo_ref.replace("$VERSION$", package_version)

            if "$" in repo_ref:
                self.out(f"Failed to define branch {copy_item.ref}.")
                return os.EX_NOINPUT

            with tempfile.TemporaryDirectory() as tmp_dir:
                result = subprocess.run(
                    f"git clone --branch {repo_ref} --depth 1 {repo_url} {tmp_dir}",
                    shell=True,
                    capture_output=True,
                    text=True,
                    check=False,
                )
                if result.returncode != os.EX_OK:
                    self.out(f"Failed to clone repo {repo_url}.")
                    self.out(result.stdout)
                    self.out(result.stderr)
                    return result.returncode

                schema = ReleaserConf.load_from_dir(Path(tmp_dir))
                schema.destination_dir = self.schema.destination_dir / copy_item.destination
                schema.copy_repo_src = []  # prevent recursion
                packer = Releaser(
                    schema=schema,
                    listener=self.out,
                )
                packer.pack()

    def add_version(self):
        if self.schema.add_version_json:
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
        else:
            self.out(
                message="add-version-json = false. Skipping version.json generation.",
                verbosity=Verbosity.VERBOSE.value,
            )
        if self.schema.manage_pyproject:
            pyproject_toml_file = self.schema.destination_dir / "pyproject.toml"
            pyproject_toml = pyproject_toml_file.read_text()
            if "VERSION-NDEV-SUBST-HERE" not in pyproject_toml:
                self.out(
                    message="no version substitution defined in pyproject.toml",
                    verbosity=Verbosity.NORMAL.value,
                )
                return os.EX_DATAERR
            pyproject_toml = pyproject_toml.replace(
                "VERSION-NDEV-SUBST-HERE", self.schema.version_str
            )
            pyproject_toml_file.write_text(pyproject_toml)
        return os.EX_OK

    def apply_patches(self):
        if not self.schema.patches:
            self.out(
                message="No patches to apply.",
                verbosity=Verbosity.VERY_VERBOSE.value,
            )
            return os.EX_OK

        self.out("Applying patches...", verbosity=Verbosity.NORMAL.value)

        for patch_item in self.schema.patches:
            self.out(
                message=f"Applying patch {patch_item.regex} to {patch_item.glob}.",
                verbosity=Verbosity.VERBOSE.value,
            )
            for path in self.schema.destination_dir.rglob(patch_item.glob):
                if path.is_file():
                    content = path.read_text(encoding="utf-8")
                    content = re.sub(
                        patch_item.regex,
                        patch_item.subst,
                        content,
                        flags=re.MULTILINE | re.IGNORECASE,
                    )
                    path.write_text(content, encoding="utf-8")

    def generate_poetry_lock(self):
        if self.schema.generate_poetry_lock:
            result = subprocess.run(
                "uv tool run poetry@2.1.3 lock",
                shell=True,
                capture_output=True,
                text=True,
                cwd=self.schema.destination_dir,
                check=False,
            )
            if result.returncode != os.EX_OK:
                raise RuntimeError(
                    f"generating poetry lock is failed with code: {result.returncode}\n"
                    f"stdout: [{result.stdout}]\n"
                    f"stderr: [{result.stderr}]"
                )

    # -- private methods --

    def _get_requirements_txt_list(self) -> list[str]:
        return get_requirements_txt(
            working_dir=self.schema.origin, groups=self.schema.install_dependencies_with_groups
        ).splitlines()
