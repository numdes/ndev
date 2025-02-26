import shutil

from pathlib import Path

import pygit2

from pygit2 import Repository

from ndev.hx_urllib import extract_basename_from_url
from ndev.protocols.listener import NULL_LISTENER
from ndev.protocols.listener import Listener
from ndev.protocols.verbosity import VERBOSE
from ndev.protocols.verbosity import VERY_VERBOSE
from ndev.services.git.git_syncer_conf import GitSyncerConf


class GitSyncer:
    """
    A service that initialized by two git URLs.
    It clones source repository to current working directory,
    adds destination repository as remote, and pushes changes to it.
    The changes should include all commits, branches, and tags from the source repository.
    """

    def __init__(self, conf: GitSyncerConf, listener: Listener = NULL_LISTENER) -> None:
        self.listener = listener
        self.conf = conf

        if not (pygit2.features & pygit2.GIT_FEATURE_SSH):
            raise RuntimeError("pygit2 was not built with SSH support.")

    def sync(self) -> None:
        self.listener.message(
            f"Syncing repo {self.conf.src_url} to {self.conf.dst_url}", VERY_VERBOSE
        )

        repo = self._clone_src_repo()

        # Add the destination repository as a remote named "destination"
        remote_name = "destination"
        if remote_name in repo.remotes:
            self.listener.message(f"Remote '{remote_name}' already exists. Updating URL.")
            repo.remotes.set_url(remote_name, self.conf.dst_url)
        else:
            self.listener.message(f"Adding remote '{remote_name}' with URL {self.conf.dst_url}")
            repo.remotes.create(remote_name, self.conf.dst_url)

        # Prepare all_src_refs for all branches and tags.
        all_src_refs = [
            f"{ref}:{ref}"
            for ref in repo.references
            if ref.startswith(("refs/heads/", "refs/tags/"))
        ]
        if self.conf.branches_list:
            self.listener.message(
                f"Filtering all_src_refs to include only branches in {self.conf.branches_list}",
                VERBOSE,
            )
            all_src_refs = [
                ref for ref in all_src_refs if ref.split("/")[2] in self.conf.branches_list
            ]
            self.listener.message(f"Filtered all_src_refs: {all_src_refs}", VERBOSE)

        self.listener.message(
            f"Pushing the following all_src_refs to remote '{remote_name}': {all_src_refs}"
        )
        destination = repo.remotes[remote_name]

        keypair = pygit2.Keypair(
            username="git",
            pubkey=Path.home() / ".ssh/id_rsa.pub",
            privkey=Path.home() / ".ssh/id_rsa",
            passphrase="",
        )
        callbacks = pygit2.RemoteCallbacks(credentials=keypair)
        destination.push(all_src_refs, callbacks=callbacks)
        self.listener.message("Push completed successfully.")

    def _clone_src_repo(self) -> Repository:
        repo_name = extract_basename_from_url(self.conf.src_url)
        clone_path = Path.cwd() / repo_name
        if clone_path.exists():
            self.listener.message(f"Removing existing directory {clone_path}", VERBOSE)
            shutil.rmtree(clone_path)

        self.listener.message(f"Cloning {self.conf.src_url} into {clone_path}")

        src_keypair = pygit2.Keypair(
            username=self.conf.src_git_user,
            pubkey=self.conf.src_public_key_path,
            privkey=self.conf.src_private_key_path,
            passphrase=self.conf.src_passphrase,
        )
        src_callback = pygit2.RemoteCallbacks(credentials=src_keypair)
        return pygit2.clone_repository(
            url=self.conf.src_url, path=clone_path, callbacks=src_callback
        )
