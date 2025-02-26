import os

from pathlib import Path
from typing import ClassVar

from cleo.commands.command import Command
from cleo.helpers import option

from ndev.impl.listener import CommandListener
from ndev.services.releaser import Releaser
from ndev.services.releaser import ReleaserConf


class ReleaseCommand(Command):
    name = "release"
    description = "Pack sources from one repository to another."

    options: ClassVar = [
        option(
            long_name="destination",
            short_name="O",
            description="Directory or git repo to save files to.",
            flag=False,
        ),
        option(
            long_name="origin",
            short_name="I",
            description="Directory to load files from.",
            flag=False,
        ),
        option(
            long_name="author_email",
            short_name="A",
            description="Author email.",
            flag=False,
        ),
        option(
            long_name="author_name",
            short_name="N",
            description="Author name.",
            flag=False,
        ),
    ]

    def __init__(self) -> None:
        super().__init__()

    def handle(self) -> int:
        if self.option("origin") is not None:
            current_dir = Path(self.option("origin"))
        else:
            current_dir = Path.cwd()

        try:
            schema = ReleaserConf.load_from_dir(current_dir)
        except FileNotFoundError:
            return os.EX_NOINPUT

        destination = self.option("destination")
        if destination.startswith("git@"):
            schema.destination_repo = destination
        else:
            schema.destination_dir = Path(destination)

        if self.option("author_email") is not None:
            schema.author_email = self.option("author_email")
        if self.option("author_name") is not None:
            schema.author_name = self.option("author_name")

        packer = Releaser(schema=schema, listener=CommandListener(self.io))
        return packer.pack()
