from importlib.metadata import version

from cleo.application import Application

from ndev.commands.git_sync import GitSyncCommand
from ndev.commands.release import ReleaseCommand


def main() -> int:
    app = Application(name="ndev", version=str(version("ndev")))
    app.add(ReleaseCommand())
    app.add(GitSyncCommand())
    exit_code = app.run()
    return exit_code


if __name__ == "__main__":
    main()
