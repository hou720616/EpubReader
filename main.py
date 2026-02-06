import argparse
import pathlib
import sys

from qt_compat import PYQT6, QtWidgets
from reader_window import ReaderWindow


def run_app(app: QtWidgets.QApplication) -> int:
    if PYQT6:
        return app.exec()
    return app.exec_()


def main() -> int:
    parser = argparse.ArgumentParser(description="简易阅读器")
    parser.add_argument("--file", default="", help="启动时加载的文件路径")
    args = parser.parse_args()

    app = QtWidgets.QApplication(sys.argv)
    window = ReaderWindow()
    if args.file:
        path = pathlib.Path(args.file).expanduser().resolve()
        if path.is_file():
            window.load_file(str(path))
    else:
        window.load_last_file()
    window.show()
    return run_app(app)


if __name__ == "__main__":
    raise SystemExit(main())
