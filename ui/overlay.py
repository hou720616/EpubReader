from qt_compat import PYQT6, QtCore, QtGui, QtWidgets, cursor_shape, key, local_pos, mouse_button, window_flag


class RegionSelectionOverlay(QtWidgets.QWidget):
    def __init__(self, parent: QtWidgets.QWidget | None = None) -> None:
        super().__init__(parent)
        self._origin = QtCore.QPoint()
        self._selected_rect: QtCore.QRect | None = None
        self._loop = QtCore.QEventLoop(self)
        shape = QtWidgets.QRubberBand.Shape.Rectangle if PYQT6 else QtWidgets.QRubberBand.Rectangle
        self._rubber_band = QtWidgets.QRubberBand(shape, self)
        flags = window_flag("FramelessWindowHint") | window_flag("WindowStaysOnTopHint") | window_flag("Tool")
        self.setWindowFlags(flags)
        self.setCursor(cursor_shape("CrossCursor"))
        self.setWindowOpacity(0.25)
        self.setStyleSheet("background-color: black;")
        self._set_virtual_geometry()

    def _set_virtual_geometry(self) -> None:
        screen = QtGui.QGuiApplication.primaryScreen()
        if screen is None:
            return
        geo = screen.virtualGeometry()
        self.setGeometry(geo)

    def select_region(self) -> QtCore.QRect | None:
        self.show()
        self.raise_()
        self.activateWindow()
        if PYQT6:
            self._loop.exec()
        else:
            self._loop.exec_()
        return self._selected_rect

    def mousePressEvent(self, event) -> None:
        if event.button() != mouse_button("LeftButton"):
            return
        self._origin = local_pos(event)
        self._rubber_band.setGeometry(QtCore.QRect(self._origin, QtCore.QSize()))
        self._rubber_band.show()

    def mouseMoveEvent(self, event) -> None:
        if self._rubber_band.isVisible():
            self._rubber_band.setGeometry(QtCore.QRect(self._origin, local_pos(event)).normalized())

    def mouseReleaseEvent(self, event) -> None:
        if event.button() != mouse_button("LeftButton"):
            return
        rect = self._rubber_band.geometry().normalized()
        self._rubber_band.hide()
        if rect.width() > 2 and rect.height() > 2:
            top_left = self.geometry().topLeft()
            self._selected_rect = QtCore.QRect(rect.topLeft() + top_left, rect.size())
        else:
            self._selected_rect = None
        self.close()
        self._loop.quit()

    def keyPressEvent(self, event) -> None:
        if event.key() == key("Key_Escape"):
            self._selected_rect = None
            self.close()
            self._loop.quit()
            return
        super().keyPressEvent(event)
