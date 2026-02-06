try:
    from PyQt6 import QtCore, QtGui, QtWidgets
    PYQT6 = True
except ImportError:
    try:
        from PyQt5 import QtCore, QtGui, QtWidgets
        PYQT6 = False
    except ImportError:
        raise SystemExit("需要安装 PyQt6 或 PyQt5")


def context_menu_policy():
    if PYQT6:
        return QtCore.Qt.ContextMenuPolicy.CustomContextMenu
    return QtCore.Qt.CustomContextMenu


def no_frame():
    if PYQT6:
        return QtWidgets.QFrame.Shape.NoFrame
    return QtWidgets.QFrame.NoFrame


def window_flag(name: str):
    if PYQT6:
        return getattr(QtCore.Qt.WindowType, name)
    return getattr(QtCore.Qt, name)


def cursor_shape(name: str):
    if PYQT6:
        return getattr(QtCore.Qt.CursorShape, name)
    return getattr(QtCore.Qt, name)


def mouse_button(name: str):
    if PYQT6:
        return getattr(QtCore.Qt.MouseButton, name)
    return getattr(QtCore.Qt, name)


def event_type(name: str):
    if PYQT6:
        return getattr(QtCore.QEvent.Type, name)
    return getattr(QtCore.QEvent, name)


def key(name: str):
    if PYQT6:
        return getattr(QtCore.Qt.Key, name)
    return getattr(QtCore.Qt, name)


def wrap_mode(name: str):
    if PYQT6:
        return getattr(QtWidgets.QTextEdit.LineWrapMode, name)
    return getattr(QtWidgets.QTextEdit, name)


def global_pos(event) -> QtCore.QPoint:
    if PYQT6:
        return event.globalPosition().toPoint()
    return event.globalPos()


def local_pos(event) -> QtCore.QPoint:
    if PYQT6:
        return event.position().toPoint()
    return event.pos()


def widget_attribute(name: str):
    if PYQT6:
        return getattr(QtCore.Qt.WidgetAttribute, name)
    return getattr(QtCore.Qt, name)
