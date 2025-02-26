import os
import tempfile

from pathlib import Path

import pytest

from ndev.services.releaser import Releaser
from ndev.services.releaser import ReleaserConf


@pytest.mark.xfail
def test_packer_copy_repo_sources(fixtures_dir: Path) -> None:
    with tempfile.TemporaryDirectory() as tmp_dir:
        conf = ReleaserConf.load_from_dir(fixtures_dir / "05_project_with_copy_repo")
        conf.destination_dir = Path(tmp_dir)
        releaser = Releaser(schema=conf)
        releaser.copy_repo_sources()
        assert releaser.copy_repo_sources() == os.EX_OK
