import os
import tempfile
from pathlib import Path

from ndev.services.packer import Packer
from ndev.services.packer import PackerSchema


def test_packer_copy_repo_sources(fixtures_dir: Path) -> None:
    with tempfile.TemporaryDirectory() as tmp_dir:
        schema = PackerSchema.load_from_dir(fixtures_dir / "05_project_with_copy_repo")
        schema.destination_dir = Path(tmp_dir)
        packer = Packer(schema=schema)
        packer.copy_repo_sources()
        assert packer.copy_repo_sources() == os.EX_OK
