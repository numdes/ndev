from abc import abstractmethod
from typing import Protocol


class Listener(Protocol):
    @abstractmethod
    def message(self, message: str, verbosity: int = 32) -> None:
        pass

    def __call__(self, message: str, verbosity: int = 32) -> None:
        self.message(message, verbosity)


class NullListener(Listener):
    def message(self, message: str, verbosity: int = 32) -> None:
        pass


NULL_LISTENER = NullListener()
