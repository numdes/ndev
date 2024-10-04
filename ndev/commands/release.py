import os
from pathlib import Path

from cleo.commands.command import Command
from cleo.helpers import option
from cleo.io.io import IO
from cleo.io.outputs.output import Verbosity

from ndev.services.listener import Listener
from ndev.services.packer import Packer
from ndev.services.packer import PackerSchema


class CommandListener(Listener):
    def __init__(self, io: IO) -> None:
        super().__init__()
        self.io = io

    def message(self, message: str, verbosity: int = 32) -> None:
        self.io.write_line(message, Verbosity(verbosity))


class ReleaseCommand(Command):
    name = "release"
    description = "Pack sources from one repository to another."

    options = [
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
            schema = PackerSchema.load_from_dir(current_dir)
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

        packer = Packer(schema=schema, listener=CommandListener(self.io))
        return packer.pack()
