import shutil

from pathlib import Path

import pygit2

from ndev.hx_urllib import extract_basename_from_url
from ndev.protocols.listener import NULL_LISTENER
from ndev.protocols.listener import Listener


class GitSyncer:
    """
    A service that initialized by two git URLs.
    It clones source repository to current working directory,
    adds destination repository as remote, and pushes changes to it.
    The changes should include all commits, branches, and tags from the source repository.
    """

    def __init__(self, src_url: str, dst_url: str, listener: Listener = NULL_LISTENER) -> None:
        self.listener = listener
        self.src = src_url
        self.dst = dst_url

    def sync(self) -> None:
        # Determine a local directory name for cloning based on the src URL.
        repo_name = extract_basename_from_url(self.src)
        clone_path = Path.cwd() / repo_name
        if clone_path.exists():
            self.listener.message(f"Removing existing directory {clone_path}")
            shutil.rmtree(clone_path)

        self.listener.message(f"Cloning {self.src} into {clone_path}")
        repo = pygit2.clone_repository(self.src, clone_path)

        # Add the destination repository as a remote named "destination"
        remote_name = "destination"
        if remote_name in repo.remotes:
            self.listener.message(f"Remote '{remote_name}' already exists. Updating URL.")
            repo.remotes.set_url(remote_name, self.dst)
        else:
            self.listener.message(f"Adding remote '{remote_name}' with URL {self.dst}")
            repo.remotes.create(remote_name, self.dst)

        # Prepare refspecs for all branches and tags.
        refspecs = [
            f"{ref}:{ref}"
            for ref in repo.references
            if ref.startswith(("refs/heads/", "refs/tags/"))
        ]

        self.listener.message(
            f"Pushing the following refspecs to remote '{remote_name}': {refspecs}"
        )
        destination = repo.remotes[remote_name]

        keypair = pygit2.Keypair(
            username="git",
            pubkey=Path.home() / ".ssh/id_rsa.pub",
            privkey=Path.home() / ".ssh/id_rsa",
            passphrase="",
        )
        callbacks = pygit2.RemoteCallbacks(credentials=keypair)
        destination.push(refspecs, callbacks=callbacks)
        self.listener.message("Push completed successfully.")
