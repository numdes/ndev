from pathlib import Path

from pydantic import BaseModel
from pydantic import Field

from ndev.types import GitUrl


class GitSyncerConf(BaseModel):
    src_url: GitUrl
    dst_url: GitUrl

    src_git_user: str = Field(default="git")
    src_private_key_path: Path = Field(default_factory=lambda: Path("~/.ssh/id_rsa").expanduser())
    src_public_key_path: Path = Field(
        default_factory=lambda: Path("~/.ssh/id_rsa.pub").expanduser()
    )
    src_passphrase: str = Field(default="")

    dst_git_user: str = Field(default="git")
    dst_private_key_path: Path = Field(default_factory=lambda: Path("~/.ssh/id_rsa").expanduser())
    dst_public_key_path: Path = Field(
        default_factory=lambda: Path("~/.ssh/id_rsa.pub").expanduser()
    )
    dst_passphrase: str = Field(default="")

    branches_list: list[str] = Field(default_factory=list)

    dry_run: bool = Field(default=False)
    keep_src_repo_dir: bool = Field(default=False)
