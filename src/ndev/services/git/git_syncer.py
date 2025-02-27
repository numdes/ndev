import shutil

from pathlib import Path
from typing import Final

import pygit2

from pygit2 import Remote
from pygit2 import Repository

from ndev.hx_urllib import extract_basename_from_url
from ndev.protocols.listener import NULL_LISTENER
from ndev.protocols.listener import Listener
from ndev.protocols.verbosity import VERBOSE
from ndev.protocols.verbosity import VERY_VERBOSE
from ndev.services.git.git_syncer_conf import GitSyncerConf


SOURCE_NAME: Final[str] = "origin"
DESTINATION_NAME: Final[str] = "dest"


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

        src_repo = self._clone_src_repo()
        dst_repo = self._add_remote(src_repo, self.conf.dst_url)
        all_src_refs = self._select_refs_to_push(src_repo)

        self.listener.message(f"Pushing refs: {all_src_refs}", VERBOSE)

        dst_repo.push(all_src_refs, callbacks=self._get_dst_callback())
        self.listener.message("Push completed successfully.")

    def _clone_src_repo(self) -> Repository:
        repo_name = extract_basename_from_url(self.conf.src_url)
        clone_path = Path.cwd() / repo_name
        if clone_path.exists():
            self.listener.message(f"Removing existing directory {clone_path}", VERBOSE)
            shutil.rmtree(clone_path)

        self.listener.message(f"Cloning {self.conf.src_url} into {clone_path}")

        return pygit2.clone_repository(
            url=self.conf.src_url, bare=True, path=clone_path, callbacks=self._get_src_callback()
        )

    def _add_remote(self, src_repo: Repository, dst_url: str) -> Remote:
        if DESTINATION_NAME in src_repo.remotes:
            self.listener.message(f"Remote '{DESTINATION_NAME}' already exists. Updating URL.")
            src_repo.remotes.set_url(DESTINATION_NAME, dst_url)
        else:
            self.listener.message(f"Adding remote '{DESTINATION_NAME}' with URL {dst_url}")
            src_repo.remotes.create(DESTINATION_NAME, dst_url)

        dst_repo = src_repo.remotes[DESTINATION_NAME]
        dst_repo.fetch(callbacks=self._get_dst_callback())
        return dst_repo

    def _get_dst_callback(self) -> pygit2.RemoteCallbacks:
        dst_keypair = pygit2.Keypair(
            username=self.conf.dst_git_user,
            pubkey=self.conf.dst_public_key_path,
            privkey=self.conf.dst_private_key_path,
            passphrase=self.conf.dst_passphrase,
        )
        return pygit2.RemoteCallbacks(credentials=dst_keypair)

    def _get_src_callback(self) -> pygit2.RemoteCallbacks:
        src_keypair = pygit2.Keypair(
            username=self.conf.src_git_user,
            pubkey=self.conf.src_public_key_path,
            privkey=self.conf.src_private_key_path,
            passphrase=self.conf.src_passphrase,
        )
        return pygit2.RemoteCallbacks(credentials=src_keypair)

    def _select_refs_to_push(self, src_repo: Repository) -> list[str]:
        refs_to_push = []
        all_refs = set(src_repo.references)
        for ref in all_refs:
            self.listener.message(f"Processing ref: {ref}", VERBOSE)

            # tags are always included
            if ref.startswith("refs/tags/"):
                refs_to_push.append(f"{ref}:{ref}")

            # active branches are always included
            if ref.startswith("refs/heads/"):
                refs_to_push.append(f"{ref}:{ref}")

            # remote branches
            if ref.startswith(f"refs/remotes/{SOURCE_NAME}"):
                ref_tokens = ref.split("/")
                ref_tokens[2] = DESTINATION_NAME
                dst_ref = "/".join(ref_tokens)

                if dst_ref in all_refs:
                    # Force update existing ref
                    refs_to_push.append(f"+{ref}:{dst_ref}")
                else:
                    # Normal push for new ref
                    refs_to_push.append(f"{ref}:{dst_ref}")

        # Prepare refs_to_push for all branches and tags.
        if self.conf.branches_list:
            self.listener.message(
                f"Filtering refs_to_push to include only branches in {self.conf.branches_list}",
                VERBOSE,
            )
            _filtered_refs_to_push = []
            for branch in self.conf.branches_list:
                for ref in refs_to_push:
                    if branch in ref:
                        _filtered_refs_to_push.append(ref)
            refs_to_push = _filtered_refs_to_push
            self.listener.message(f"Filtered refs_to_push: {refs_to_push}", VERBOSE)

        return refs_to_push
