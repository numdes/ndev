import logging
import os
import subprocess
import tempfile

from fnmatch import fnmatch
from pathlib import Path


logger = logging.getLogger(__name__)


def generate_requirements_txt(
    working_dir: Path,
    args: str,
    output_file_path: Path,
) -> None:
    if (working_dir / "poetry.lock").exists():
        logger.info("poetry.lock found, using poetry to generate requirements.txt")
        result = subprocess.run(
            "poetry export "
            "--without-hashes "
            f"{args}"
            "--format requirements.txt "
            f"--output {output_file_path}",
            shell=True,
            capture_output=True,
            text=True,
            cwd=working_dir,
            check=False,
        )

        if result.returncode != os.EX_OK:
            raise RuntimeError(
                f"poetry export failed with exit code {result.returncode}\n"
                f"stdout: [{result.stdout}]\n"
                f"stderr: [{result.stderr}]"
            )
        else:
            return

    if (working_dir / "uv.lock").exists():
        logger.info("uv.lock found, using uv to generate requirements.txt")
        result = subprocess.run(
            "uv export "
            "--format requirements.txt "
            "--locked "
            "--no-hashes "
            f"--output-file {output_file_path}",
            shell=True,
            capture_output=True,
            text=True,
            cwd=working_dir,
            check=False,
        )

        if result.returncode != os.EX_OK:
            raise RuntimeError(
                f"uv export failed with exit code {result.returncode}\n"
                f"stdout: [{result.stdout}]\n"
                f"stderr: [{result.stderr}]"
            )
        else:
            return

    raise FileNotFoundError(
        "No poetry.lock or uv.lock file found in the working directory. "
        "Cannot generate requirements.txt."
    )


def get_requirements_txt(working_dir: Path, groups: list[str] | None = None) -> str:
    if groups is None:
        groups = []

    groups_txt = ",".join(groups)
    with_groups = f"--with {groups_txt} " if groups_txt else ""

    with tempfile.NamedTemporaryFile() as requirements_file:
        logger.debug(f"Writing requirements file to {requirements_file.name}")
        generate_requirements_txt(
            working_dir=working_dir,
            args=with_groups,
            output_file_path=Path(requirements_file.name),
        )

        return Path(requirements_file.name).read_text(encoding="utf-8")


def filter_requirements_txt(requirements_txt: str, filtered_matches: list[str]) -> str:
    requirements_lines = requirements_txt.splitlines()
    good_lines = []
    for line in requirements_lines:
        if len(line) == 0:
            good_lines.append(line)
            continue
        line_is_good = True
        for match in filtered_matches:
            if fnmatch(line, match):
                line_is_good = False
                break

        if line_is_good:
            good_lines.append(line)

    return "\n".join(good_lines)


def add_dependencies_to_pyproject_toml(pyproject_toml: str, requirements_txt: str) -> str:
    if "dependencies = []" not in pyproject_toml:
        raise ValueError(
            f"pyproject.toml does not contain 'dependencies = []'. Can't handle this.\n"
            f"pyproject.toml: {pyproject_toml}"
        )
    dependencies_txt = "dependencies = [\n"
    for line in requirements_txt.splitlines():
        if not line:
            continue
        declaration = line.split(";")[0].strip()
        dependencies_txt += f'    "{declaration}",\n'
    dependencies_txt += "]"
    pyproject_toml = pyproject_toml.replace("dependencies = []", dependencies_txt)
    return pyproject_toml
