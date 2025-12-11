import logging
import shutil
import tarfile
import tempfile
import zipfile

from collections.abc import Callable
from pathlib import Path


logger = logging.getLogger(__name__)


def copytree_from_zip(
    zip_path: Path,
    dst_dir: Path,
    path_in_zip: str = ".",
    ignore: Callable | None = None,
) -> None:
    """Extracts a directory from a ZIP or TAR.GZ archive to the destination directory.

    Supported formats:
    - .zip
    - .tar.gz
    - .tgz

    Args:
        zip_path: Path to the archive.
        dst_dir: Destination directory.
        path_in_zip: Path inside the archive to copy.
        ignore: Ignore callable (same semantics as shutil.copytree).
    """
    suffixes = zip_path.suffixes

    with tempfile.TemporaryDirectory() as tmp_dir_str:
        tmp_dir = Path(tmp_dir_str)

        if suffixes[-1] == ".zip" or suffixes[-1] == ".whl":
            with zipfile.ZipFile(zip_path, "r") as archive:
                archive.extractall(tmp_dir)

        elif suffixes[-2:] == [".tar", ".gz"] or suffixes[-1] == ".tgz":
            with tarfile.open(zip_path, "r:gz") as archive:
                archive.extractall(tmp_dir)

            for child in tmp_dir.iterdir():
                if child.is_dir() and "-" in child.name:
                    shutil.move(str(child), str(tmp_dir / child.name.split("-", 1)[0]))

        else:
            raise ValueError(f"Unsupported archive format: {zip_path.name}")

        src_dir = tmp_dir / path_in_zip
        if not src_dir.exists():
            raise FileNotFoundError(f"Path '{path_in_zip}' not found in archive '{zip_path.name}'")

        shutil.copytree(
            src=src_dir,
            dst=dst_dir,
            dirs_exist_ok=True,
            ignore=ignore,
        )
