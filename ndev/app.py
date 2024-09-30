from cleo.application import Application

def main() -> int:
    app = Application()
    exit_code = app.run()
    return exit_code