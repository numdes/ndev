import csv
import json
import os
import subprocess
import sys
import tomllib

from pathlib import Path
from typing import ClassVar
from typing import cast

from cleo.commands.command import Command
from cleo.helpers import option
from pydantic import BaseModel

from ndev.deps.licenses import CustomNamespace
from ndev.deps.licenses import FromArg
from ndev.deps.licenses import get_packages
from ndev.deps.licenses import normalize_pkg_name
from ndev.deps.licenses import select_license_by_source


class Package(BaseModel):
    name: str
    version: str
    license: str


def _find_venv_python(cwd: Path, manager: str) -> str | None:
    if manager == "uv":
        venv_python = cwd / ".venv" / "bin" / "python"
        if venv_python.exists():
            return str(venv_python)
    else:
        result = subprocess.run(
            ["poetry", "env", "info", "-e"],
            check=False,
            cwd=cwd,
            capture_output=True,
            text=True,
        )
        if result.returncode == 0 and result.stdout.strip():
            return result.stdout.strip()
    return None


def _sync_env(cwd: Path, manager: str) -> bool:
    if manager == "uv":
        result = subprocess.run(
            ["uv", "sync", "--quiet"],
            check=False,
            cwd=cwd,
            capture_output=True,
            text=True,
        )
    else:
        result = subprocess.run(
            ["poetry", "install", "--quiet"],
            check=False,
            cwd=cwd,
            capture_output=True,
            text=True,
        )
    return result.returncode == 0


def _collect_licenses(python_path: str) -> dict[str, Package]:
    args = CustomNamespace()
    args.python = python_path
    args.from_ = FromArg.MIXED
    args.ignore_packages = []
    args.packages = []
    args.with_system = False
    args.filter_strings = False
    args.filter_code_page = "latin1"
    args.fail_on = None
    args.allow_only = None
    args.partial_match = False

    result: dict[str, Package] = {}
    for pkg_info in get_packages(args):
        name = cast("str", pkg_info["name"])
        version = cast("str", pkg_info["version"])
        license_set = select_license_by_source(
            FromArg.MIXED,
            cast("list[str]", pkg_info["license_classifier"]),
            cast("str", pkg_info["license"]),
            cast("str", pkg_info["license_expression"]),
        )
        license_str = "; ".join(sorted(license_set))
        license_str = license_str.split("\n", 1)[0].strip()
        key = normalize_pkg_name(name)
        result[key] = Package(name=name, version=version, license=license_str)

    return result


def _parse_lock_packages(lock_path: Path) -> list[tuple[str, str]]:
    with open(lock_path, "rb") as f:
        lock_data = tomllib.load(f)
    return [(pkg.get("name", ""), pkg.get("version", "")) for pkg in lock_data.get("package", [])]


def _parse_uv_lock(lock_path: Path) -> list[Package]:
    cwd = lock_path.parent
    if not _sync_env(cwd, "uv"):
        return []
    python_path = _find_venv_python(cwd, "uv")
    if python_path is None:
        return []
    license_map = _collect_licenses(python_path)
    lock_packages = _parse_lock_packages(lock_path)

    project_name = _get_project_name(cwd)
    result = []
    for name, version in lock_packages:
        key = normalize_pkg_name(name)
        if project_name and key == normalize_pkg_name(project_name):
            continue
        if key in license_map:
            result.append(license_map[key])
        else:
            result.append(Package(name=name, version=version, license="UNKNOWN"))
    return result


def _parse_poetry_lock(lock_path: Path) -> list[Package]:
    cwd = lock_path.parent
    if not _sync_env(cwd, "poetry"):
        return []
    python_path = _find_venv_python(cwd, "poetry")
    if python_path is None:
        return []
    license_map = _collect_licenses(python_path)
    lock_packages = _parse_lock_packages(lock_path)

    project_name = _get_project_name(cwd)
    result = []
    for name, version in lock_packages:
        key = normalize_pkg_name(name)
        if project_name and key == normalize_pkg_name(project_name):
            continue
        if key in license_map:
            result.append(license_map[key])
        else:
            result.append(Package(name=name, version=version, license="UNKNOWN"))
    return result


def _get_project_name(cwd: Path) -> str | None:
    pyproject_path = cwd / "pyproject.toml"
    if not pyproject_path.exists():
        return None
    with open(pyproject_path, "rb") as f:
        pyproject = tomllib.load(f)
    return pyproject.get("project", {}).get("name") or pyproject.get("tool", {}).get(
        "poetry", {}
    ).get("name")


def _extract_license(pkg_json: dict) -> str:
    lic = pkg_json.get("license")
    if isinstance(lic, str):
        return lic
    if isinstance(lic, dict):
        return lic.get("type", "UNKNOWN")
    licenses = pkg_json.get("licenses")
    if isinstance(licenses, list) and licenses:
        parts = [entry.get("type", "UNKNOWN") for entry in licenses if isinstance(entry, dict)]
        return "; ".join(parts) if parts else "UNKNOWN"
    return "UNKNOWN"


def _parse_package_json(package_json_path: Path) -> list[Package]:
    cwd = package_json_path.parent
    yarn_lock = cwd / "yarn.lock"
    if yarn_lock.exists():
        install_cmd = ["yarn", "install", "--frozen-lockfile"]
    else:
        install_cmd = ["npm", "install"]

    result = subprocess.run(
        install_cmd,
        check=False,
        cwd=cwd,
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        return []

    node_modules = cwd / "node_modules"
    if not node_modules.is_dir():
        return []

    packages: list[Package] = []
    seen: set[str] = set()

    for pkg_json_path in node_modules.glob("*/package.json"):
        _read_node_package(pkg_json_path, packages, seen)
    for pkg_json_path in node_modules.glob("@*/*/package.json"):
        _read_node_package(pkg_json_path, packages, seen)

    return packages


def _read_node_package(pkg_json_path: Path, packages: list[Package], seen: set[str]) -> None:
    try:
        with open(pkg_json_path, encoding="utf-8") as f:
            data = json.load(f)
    except (json.JSONDecodeError, OSError):
        return
    name = data.get("name")
    version = data.get("version", "0.0.0")
    if not name or name in seen:
        return
    seen.add(name)
    packages.append(Package(name=name, version=version, license=_extract_license(data)))


class SbomCommand(Command):
    name = "sbom"
    description = "Print SBOM as CSV with dependency, version and license."

    options: ClassVar = [
        option(
            long_name="output",
            short_name="o",
            description="Output file path (default: stdout).",
            flag=False,
        ),
    ]

    def handle(self) -> int:
        cwd = Path.cwd()
        uv_lock = cwd / "uv.lock"
        poetry_lock = cwd / "poetry.lock"
        package_json = cwd / "package.json"

        if uv_lock.exists():
            self.line("Syncing environment and collecting license metadata...")
            packages = _parse_uv_lock(uv_lock)
        elif poetry_lock.exists():
            self.line("Syncing environment and collecting license metadata...")
            packages = _parse_poetry_lock(poetry_lock)
        elif package_json.exists():
            self.line("Installing dependencies and collecting license metadata...")
            packages = _parse_package_json(package_json)
        else:
            self.line(
                "<error>No uv.lock, poetry.lock, or package.json found in current directory.</error>"
            )
            return os.EX_NOINPUT

        packages.sort(key=lambda p: p.name.lower())

        output_path = self.option("output")
        if output_path:
            with open(output_path, "w", newline="", encoding="utf-8") as f:
                writer = csv.writer(f)
                writer.writerow(["dependency", "version", "license"])
                for p in packages:
                    writer.writerow([p.name, p.version, p.license])
        else:
            writer = csv.writer(sys.stdout)
            writer.writerow(["dependency", "version", "license"])
            for p in packages:
                writer.writerow([p.name, p.version, p.license])

        return os.EX_OK
