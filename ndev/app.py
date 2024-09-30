from cleo.application import Application

from ndev.commands.release import ReleaseCommand


def main() -> int:
    app = Application()
    app.add(ReleaseCommand())
    exit_code = app.run()
    return exit_code


if __name__ == "__main__":
    main()
