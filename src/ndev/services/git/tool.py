from pathlib import Path

from git import Repo


def push(repo_path: Path, remote: str, refspec: str | list[str]):
    repo = Repo(repo_path)
    remote = repo.remote(remote)
    remote.push(refspec)
