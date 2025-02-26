import os

from typing import ClassVar

from cleo.commands.command import Command
from cleo.helpers import option

from ndev.impl.listener import CommandListener
from ndev.services.git.git_syncer import GitSyncer
from ndev.services.git.git_syncer_conf import GitSyncerConf


class GitSyncCommand(Command):
    name = "git sync"
    description = "Sync changes between two git repositories."

    options: ClassVar = [
        option(
            long_name="src",
            description="Source git repository.",
            flag=False,
        ),
        option(
            long_name="dst",
            description="Destination git repository.",
            flag=False,
        ),
        option(
            long_name="branches",
            description="Branches to sync.",
            flag=False,
        ),
    ]

    def handle(self) -> int:
        src = self.option("src")
        dst = self.option("dst")

        if src is None or dst is None:
            self.line(
                "<error>Both source and destination " "git repositories must be specified.</error>"
            )
            return os.EX_USAGE

        branches = self.option("branches")
        branches_list = branches.split(",") if branches else []

        git_sync_conf = GitSyncerConf(
            src_url=src,
            dst_url=dst,
            branches_list=branches_list,
        )

        git_syncer = GitSyncer(conf=git_sync_conf, listener=CommandListener(self.io))
        git_syncer.sync()
        return os.EX_OK
