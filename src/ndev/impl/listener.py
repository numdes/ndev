from cleo.io.io import IO
from cleo.io.outputs.output import Verbosity

from ndev.protocols.listener import Listener


class CommandListener(Listener):
    def __init__(self, io: IO) -> None:
        super().__init__()
        self.io = io

    def message(self, message: str, verbosity: int = 32) -> None:
        self.io.write_line(message, Verbosity(verbosity))
