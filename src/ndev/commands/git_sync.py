import os

from typing import ClassVar

from cleo.commands.command import Command
from cleo.helpers import option

from ndev.impl.listener import CommandListener
from ndev.services.git.git_syncer import GitSyncer


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
    ]

    def handle(self) -> int:
        src = self.option("src")
        dst = self.option("dst")

        if src is None or dst is None:
            self.line(
                "<error>Both source and destination " "git repositories must be specified.</error>"
            )
            return os.EX_USAGE

        git_syncer = GitSyncer(src, dst, listener=CommandListener(self.io))
        git_syncer.sync()
        return os.EX_OK
