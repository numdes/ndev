import os
from pathlib import Path

from cleo.commands.command import Command
from cleo.helpers import option

from ndev.services.packer import Packer
from ndev.services.packer import PackerSchema


class ReleaseCommand(Command):
    name = "release"
    description = "Pack sources from one repository to another."

    options = [
        option(
            long_name="destination",
            short_name="O",
            description="Directory to save files to.",
            flag=False,
        ),
        option(
            long_name="origin",
            short_name="I",
            description="Directory to load files from.",
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

        schema.to_dir = Path(self.option("destination"))

        packer = Packer(schema=schema)
        return packer.pack()
