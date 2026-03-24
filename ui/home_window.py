import os

from qt_compat import PYQT6, QtCore, QtGui, QtWidgets
from reader_window import ReaderWindow
from services.config_service import (
    DEFAULT_CONFIG,
    load_config_data,
    normalize_existing_file,
    save_config_data,
    update_recent_paths,
)
from ui.settings_dialog import SettingsDialog


class HomeWindow(QtWidgets.QMainWindow):
    def __init__(self, open_home_window, keep_window_ref) -> None:
        super().__init__()
        self.setWindowTitle("EpubReader")
        self.resize(920, 620)
        self.reader: ReaderWindow | None = None
        self.config_data = load_config_data()
        self._open_home_window = open_home_window
        self._keep_window_ref = keep_window_ref
        root = QtWidgets.QWidget()
        root_layout = QtWidgets.QVBoxLayout(root)
        root_layout.setContentsMargins(28, 28, 28, 28)
        root_layout.setSpacing(16)
        title = QtWidgets.QLabel("EpubReader")
        title.setStyleSheet("font-size: 28px; font-weight: 600; color: #1F2937;")
        subtitle = QtWidgets.QLabel("轻阅读 · 低打扰 · 可摸鱼")
        subtitle.setStyleSheet("font-size: 14px; color: #6B7280;")
        root_layout.addWidget(title)
        root_layout.addWidget(subtitle)
        action_row = QtWidgets.QHBoxLayout()
        action_row.setSpacing(10)
        self.open_btn = QtWidgets.QPushButton("打开本地书籍")
        self.open_btn.clicked.connect(self.open_local_file)
        self.continue_btn = QtWidgets.QPushButton("继续阅读")
        self.continue_btn.clicked.connect(self.continue_reading)
        self.settings_btn = QtWidgets.QPushButton("阅读设置")
        self.settings_btn.clicked.connect(self.open_settings)
        for btn in (self.open_btn, self.continue_btn, self.settings_btn):
            btn.setMinimumHeight(42)
            action_row.addWidget(btn)
        root_layout.addLayout(action_row)
        card = QtWidgets.QFrame()
        card.setObjectName("recentCard")
        card_layout = QtWidgets.QVBoxLayout(card)
        card_layout.setContentsMargins(16, 16, 16, 16)
        card_layout.setSpacing(12)
        list_title = QtWidgets.QLabel("最近书籍")
        list_title.setStyleSheet("font-size: 15px; font-weight: 600; color: #374151;")
        self.recent_list = QtWidgets.QListWidget()
        self.recent_list.itemDoubleClicked.connect(self.open_recent_item)
        self.empty_label = QtWidgets.QLabel("暂无记录，先打开一本书吧")
        self.empty_label.setStyleSheet("color: #9CA3AF; font-size: 13px;")
        card_layout.addWidget(list_title)
        card_layout.addWidget(self.recent_list)
        card_layout.addWidget(self.empty_label)
        root_layout.addWidget(card)
        shortcut_card = QtWidgets.QFrame()
        shortcut_card.setObjectName("shortcutCard")
        shortcut_layout = QtWidgets.QVBoxLayout(shortcut_card)
        shortcut_layout.setContentsMargins(16, 14, 16, 14)
        shortcut_layout.setSpacing(10)
        shortcut_title = QtWidgets.QLabel("快捷键设置")
        shortcut_title.setStyleSheet("font-size: 15px; font-weight: 600; color: #374151;")
        shortcut_layout.addWidget(shortcut_title)
        self.shortcut_grid = QtWidgets.QGridLayout()
        self.shortcut_grid.setHorizontalSpacing(10)
        self.shortcut_grid.setVerticalSpacing(8)
        self.shortcut_grid.addWidget(QtWidgets.QLabel("动作"), 0, 0)
        self.shortcut_grid.addWidget(QtWidgets.QLabel("按键"), 0, 1)
        self.shortcut_grid.addWidget(QtWidgets.QLabel("上一页"), 1, 0)
        self.shortcut_grid.addWidget(QtWidgets.QLabel("下一页"), 2, 0)
        self.shortcut_grid.addWidget(QtWidgets.QLabel("隐藏"), 3, 0)
        self.shortcut_grid.addWidget(QtWidgets.QLabel("关闭窗口"), 4, 0)
        self.prev_primary_edit = QtWidgets.QKeySequenceEdit()
        self.next_primary_edit = QtWidgets.QKeySequenceEdit()
        self.toggle_visible_edit = QtWidgets.QKeySequenceEdit()
        self.close_app_edit = QtWidgets.QKeySequenceEdit()
        self.shortcut_grid.addWidget(self.prev_primary_edit, 1, 1)
        self.shortcut_grid.addWidget(self.next_primary_edit, 2, 1)
        self.shortcut_grid.addWidget(self.toggle_visible_edit, 3, 1)
        self.shortcut_grid.addWidget(self.close_app_edit, 4, 1)
        shortcut_layout.addLayout(self.shortcut_grid)
        self.shortcut_tip_label = QtWidgets.QLabel("修改后点击“保存快捷键”生效。")
        self.shortcut_tip_label.setStyleSheet("color: #6B7280; font-size: 12px;")
        shortcut_layout.addWidget(self.shortcut_tip_label)
        self.shortcut_save_btn = QtWidgets.QPushButton("保存快捷键")
        self.shortcut_save_btn.clicked.connect(self.save_shortcuts)
        self.shortcut_save_btn.setMinimumHeight(34)
        shortcut_layout.addWidget(self.shortcut_save_btn)
        root_layout.addWidget(shortcut_card)
        root_layout.addStretch(1)
        self.setCentralWidget(root)
        self.setStyleSheet(
            "QMainWindow { background: #ECEFF3; }"
            "QPushButton { background: #DDE2E8; border: 1px solid #C7CED8; border-radius: 10px; color: #1F2937; font-size: 14px; padding: 8px 12px; }"
            "QPushButton:hover { background: #D2D8E1; }"
            "QPushButton:disabled { background: #E5E7EB; color: #9CA3AF; border: 1px solid #D1D5DB; }"
            "QFrame#recentCard { background: #F7F8FA; border: 1px solid #D8DEE7; border-radius: 12px; }"
            "QFrame#shortcutCard { background: #F7F8FA; border: 1px solid #D8DEE7; border-radius: 12px; }"
            "QListWidget { background: #FFFFFF; border: 1px solid #E5E7EB; border-radius: 10px; outline: none; color: #1F2937; }"
            "QListWidget::item { padding: 8px 10px; border-radius: 6px; }"
            "QListWidget::item:selected { background: #E8EDF3; color: #111827; }"
            "QListWidget::item:hover { background: #F2F4F7; }"
            "QKeySequenceEdit { background: #FFFFFF; border: 1px solid #D1D5DB; border-radius: 8px; padding: 4px 6px; }"
            "QPushButton#shortcutSaveBtn { background: #D7E3F3; border: 1px solid #AFC4DE; color: #0F2742; font-weight: 600; }"
            "QPushButton#shortcutSaveBtn:hover { background: #C9DAEF; }"
        )
        self.shortcut_save_btn.setObjectName("shortcutSaveBtn")
        self._load_shortcut_editors()
        self.refresh_recent_view()

    def refresh_recent_view(self) -> None:
        self.config_data = load_config_data()
        self.recent_list.clear()
        recent_paths = self.config_data.get("recent_paths", [])
        valid_paths: list[str] = []
        if isinstance(recent_paths, list):
            for p in recent_paths:
                if not isinstance(p, str):
                    continue
                normalized = normalize_existing_file(p)
                if normalized is None:
                    continue
                if normalized in valid_paths:
                    continue
                valid_paths.append(normalized)
        if valid_paths != recent_paths:
            self.config_data["recent_paths"] = valid_paths
            save_config_data(self.config_data)
        for p in valid_paths:
            name = os.path.basename(p)
            item = QtWidgets.QListWidgetItem(f"{name}\n{p}")
            item.setData(QtCore.Qt.ItemDataRole.UserRole if PYQT6 else QtCore.Qt.UserRole, p)
            self.recent_list.addItem(item)
        last_path = normalize_existing_file(str(self.config_data.get("last_path", "")))
        if last_path:
            self.continue_btn.setEnabled(True)
            self.continue_btn.setText(f"继续阅读：{os.path.basename(last_path)}")
        else:
            self.continue_btn.setEnabled(False)
            self.continue_btn.setText("继续阅读")
        is_empty = len(valid_paths) == 0
        self.empty_label.setVisible(is_empty)
        self.recent_list.setVisible(not is_empty)
        self._load_shortcut_editors()

    def _key_sequence_text(self, sequence: QtGui.QKeySequence) -> str:
        fmt = QtGui.QKeySequence.SequenceFormat.PortableText if PYQT6 else QtGui.QKeySequence.PortableText
        return sequence.toString(fmt)

    def _load_shortcut_editors(self) -> None:
        shortcuts = self.config_data.get("shortcuts", DEFAULT_CONFIG["shortcuts"])
        self.prev_primary_edit.setKeySequence(QtGui.QKeySequence(shortcuts.get("prev_page", "A")))
        self.next_primary_edit.setKeySequence(QtGui.QKeySequence(shortcuts.get("next_page", "D")))
        self.toggle_visible_edit.setKeySequence(QtGui.QKeySequence(shortcuts.get("toggle_visible", "Alt+V")))
        self.close_app_edit.setKeySequence(QtGui.QKeySequence(shortcuts.get("close_app", "Alt+Esc")))

    def save_shortcuts(self) -> None:
        prev_primary = self._key_sequence_text(self.prev_primary_edit.keySequence()) or "A"
        next_primary = self._key_sequence_text(self.next_primary_edit.keySequence()) or "D"
        toggle_visible = self._key_sequence_text(self.toggle_visible_edit.keySequence()) or "Alt+V"
        close_app = self._key_sequence_text(self.close_app_edit.keySequence()) or "Alt+Esc"
        self.config_data["shortcuts"] = {
            "prev_page": prev_primary,
            "next_page": next_primary,
            "toggle_visible": toggle_visible,
            "close_app": close_app,
        }
        save_config_data(self.config_data)
        if close_app.strip().lower() == "alt+esc":
            QtWidgets.QMessageBox.information(self, "快捷键设置", "快捷键已保存。注意 Alt+Esc 可能被系统占用，已支持 Alt+Q 作为关闭兜底。")
        else:
            QtWidgets.QMessageBox.information(self, "快捷键设置", "快捷键已保存")

    def open_local_file(self) -> None:
        file_path, _ = QtWidgets.QFileDialog.getOpenFileName(
            self,
            "选择文件",
            "",
            "电子书 (*.txt *.epub);;文本 (*.txt);;EPUB (*.epub);;所有文件 (*.*)",
        )
        if not file_path:
            return
        normalized = normalize_existing_file(file_path)
        if normalized is None:
            QtWidgets.QMessageBox.warning(self, "打开失败", "文件不存在或不可访问")
            return
        self.open_reader(normalized)

    def continue_reading(self) -> None:
        last_path = normalize_existing_file(str(self.config_data.get("last_path", "")))
        if last_path is None:
            QtWidgets.QMessageBox.information(self, "继续阅读", "最近阅读文件不存在，请重新选择")
            self.refresh_recent_view()
            return
        self.open_reader(last_path)

    def open_recent_item(self, item: QtWidgets.QListWidgetItem) -> None:
        data_role = QtCore.Qt.ItemDataRole.UserRole if PYQT6 else QtCore.Qt.UserRole
        file_path = item.data(data_role)
        normalized = normalize_existing_file(str(file_path))
        if normalized is None:
            QtWidgets.QMessageBox.information(self, "提示", "该文件已不存在，已从列表移除")
            self.refresh_recent_view()
            return
        self.open_reader(normalized)

    def open_settings(self) -> None:
        dialog = SettingsDialog(self)
        if PYQT6:
            accepted = dialog.exec()
        else:
            accepted = dialog.exec_()
        if accepted:
            self.refresh_recent_view()

    def open_reader(self, file_path: str) -> None:
        self.config_data = load_config_data()
        update_recent_paths(self.config_data, file_path)
        save_config_data(self.config_data)
        self.reader = ReaderWindow(on_back_home=self._open_home_window)
        self._keep_window_ref(self.reader)
        self.reader.load_file(file_path)
        self.reader.show()
        self.close()
