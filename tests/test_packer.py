import os
import tempfile

from pathlib import Path

import pytest

from ndev.services.packer import PackerConf
from ndev.services.packer import Releaser


@pytest.mark.xfail
def test_packer_copy_repo_sources(fixtures_dir: Path) -> None:
    with tempfile.TemporaryDirectory() as tmp_dir:
        schema = PackerConf.load_from_dir(fixtures_dir / "05_project_with_copy_repo")
        schema.destination_dir = Path(tmp_dir)
        packer = Releaser(schema=schema)
        packer.copy_repo_sources()
        assert packer.copy_repo_sources() == os.EX_OK
