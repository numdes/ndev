import shutil
import tempfile
import zipfile
from pathlib import Path


def copytree_from_zip(
    zip_path: Path,
    dst_dir: Path,
    path_in_zip: str = ".",
) -> None:
    """Extracts a directory from a ZIP archive to the destination directory.

    Args:
        zip_path: Path to the ZIP archive.
        dst_dir: Destination directory.
        path_in_zip: Path to the directory in the ZIP archive.
    """
    with zipfile.ZipFile(zip_path, "r") as zip_file:
        with tempfile.TemporaryDirectory() as tmp_dir:
            zip_file.extractall(tmp_dir)
            src_dir = Path(tmp_dir) / path_in_zip
            shutil.copytree(src=src_dir, dst=dst_dir, dirs_exist_ok=True)
