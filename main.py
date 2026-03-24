import argparse
import sys

from qt_compat import PYQT6, QtGui, QtWidgets
from reader_window import ReaderWindow
from services.config_service import get_icon_path, normalize_existing_file
from ui.home_window import HomeWindow

WINDOW_REFS: list[QtWidgets.QWidget] = []


def keep_window_ref(window: QtWidgets.QWidget) -> None:
    WINDOW_REFS.append(window)
    window.destroyed.connect(lambda *_: WINDOW_REFS.remove(window) if window in WINDOW_REFS else None)


def apply_app_icon(app: QtWidgets.QApplication) -> None:
    icon_path = get_icon_path()
    if not icon_path.exists():
        return
    app.setWindowIcon(QtGui.QIcon(str(icon_path)))


def open_home_window() -> HomeWindow:
    window = HomeWindow(open_home_window=open_home_window, keep_window_ref=keep_window_ref)
    keep_window_ref(window)
    window.show()
    return window


def run_app(app: QtWidgets.QApplication) -> int:
    if PYQT6:
        return app.exec()
    return app.exec_()


def main() -> int:
    parser = argparse.ArgumentParser(description="简易阅读器")
    parser.add_argument("--file", default="", help="启动时加载的文件路径")
    args = parser.parse_args()

    app = QtWidgets.QApplication(sys.argv)
    apply_app_icon(app)
    if args.file:
        path = normalize_existing_file(args.file)
        window = ReaderWindow(on_back_home=open_home_window)
        keep_window_ref(window)
        if path:
            window.load_file(path)
        window.show()
    else:
        open_home_window()
    return run_app(app)


if __name__ == "__main__":
    raise SystemExit(main())
