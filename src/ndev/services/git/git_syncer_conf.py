from pydantic import BaseModel

from ndev.types import GitUrl


class GitSyncerConf(BaseModel):
    src_url: GitUrl
    dst_url: GitUrl
