import argparse
import copy
import json
import os
import pathlib
import sys
from collections import defaultdict

from qt_compat import PYQT6, QtCore, QtGui, QtWidgets, cursor_shape, local_pos, mouse_button, window_flag
from reader_window import ReaderWindow

WINDOW_REFS: list[QtWidgets.QWidget] = []

DEFAULT_CONFIG = {
    "last_path": "",
    "recent_paths": [],
    "font_family": "微软雅黑",
    "font_size": 18,
    "font_color": "#000000",
    "font_alpha": 1.0,
    "font_spacing": 0.0,
    "line_spacing": 1.0,
    "bg_color": "#F2F2F2",
    "bg_alpha": 1.0,
    "shortcuts": {
        "prev_page": "A",
        "next_page": "D",
        "toggle_visible": "Alt+V",
        "close_app": "Alt+Esc",
    },
}


def get_base_path() -> pathlib.Path:
    if getattr(sys, "frozen", False):
        return pathlib.Path(sys.executable).parent
    return pathlib.Path(__file__).resolve().parent


def get_config_path() -> pathlib.Path:
    return get_base_path() / "reader_config.json"


def get_icon_path() -> pathlib.Path:
    base = get_base_path() / "ico"
    ico_path = base / "yu.ico"
    if ico_path.exists():
        return ico_path
    return base / "yu.svg"


def keep_window_ref(window: QtWidgets.QWidget) -> None:
    WINDOW_REFS.append(window)
    window.destroyed.connect(lambda *_: WINDOW_REFS.remove(window) if window in WINDOW_REFS else None)


def apply_app_icon(app: QtWidgets.QApplication) -> None:
    icon_path = get_icon_path()
    if not icon_path.exists():
        return
    app.setWindowIcon(QtGui.QIcon(str(icon_path)))


def load_config_data() -> dict:
    config = copy.deepcopy(DEFAULT_CONFIG)
    path = get_config_path()
    try:
        if path.exists():
            raw = json.loads(path.read_text(encoding="utf-8"))
            if isinstance(raw, dict):
                config.update(raw)
    except Exception:
        pass
    if not isinstance(config.get("recent_paths"), list):
        config["recent_paths"] = []
    shortcuts = config.get("shortcuts")
    if not isinstance(shortcuts, dict):
        config["shortcuts"] = copy.deepcopy(DEFAULT_CONFIG["shortcuts"])
    else:
        normalized_shortcuts: dict[str, str] = {}
        for action, default_value in DEFAULT_CONFIG["shortcuts"].items():
            action_value = shortcuts.get(action)
            if isinstance(action_value, str) and action_value.strip():
                normalized_shortcuts[action] = action_value.strip()
                continue
            if isinstance(action_value, dict):
                legacy_primary = action_value.get("primary")
                if isinstance(legacy_primary, str) and legacy_primary.strip():
                    normalized_shortcuts[action] = legacy_primary.strip()
                    continue
            normalized_shortcuts[action] = default_value
        config["shortcuts"] = normalized_shortcuts
    return config


def save_config_data(config_data: dict) -> None:
    path = get_config_path()
    try:
        path.write_text(json.dumps(config_data, ensure_ascii=False, indent=2), encoding="utf-8")
    except Exception:
        pass


def normalize_existing_file(path_text: str) -> str | None:
    try:
        path = pathlib.Path(path_text).expanduser().resolve()
    except Exception:
        return None
    if not path.is_file():
        return None
    return str(path)


def update_recent_paths(config_data: dict, file_path: str) -> None:
    recent = config_data.get("recent_paths", [])
    if not isinstance(recent, list):
        recent = []
    normalized = [str(pathlib.Path(p).expanduser().resolve()) for p in recent if isinstance(p, str)]
    if file_path in normalized:
        normalized.remove(file_path)
    normalized.insert(0, file_path)
    config_data["recent_paths"] = normalized[:20]
    config_data["last_path"] = file_path


class SettingsDialog(QtWidgets.QDialog):
    def __init__(self, parent: QtWidgets.QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("阅读设置")
        self.setModal(True)
        self.resize(480, 430)
        self._debug("初始化设置弹窗")
        self.config_data = load_config_data()
        self.font_family = str(self.config_data.get("font_family", DEFAULT_CONFIG["font_family"]))
        self.font_size = int(self.config_data.get("font_size", DEFAULT_CONFIG["font_size"]))
        self.font_color = str(self.config_data.get("font_color", DEFAULT_CONFIG["font_color"]))
        self.bg_color = str(self.config_data.get("bg_color", DEFAULT_CONFIG["bg_color"]))
        self.font_alpha = float(self.config_data.get("font_alpha", DEFAULT_CONFIG["font_alpha"]))
        self.font_spacing = float(self.config_data.get("font_spacing", DEFAULT_CONFIG["font_spacing"]))
        self.line_spacing = float(self.config_data.get("line_spacing", DEFAULT_CONFIG["line_spacing"]))
        self.font_spacing = min(20.0, max(0.0, self.font_spacing))
        self.line_spacing = min(2.2, max(1.0, self.line_spacing))
        self.bg_alpha = float(self.config_data.get("bg_alpha", DEFAULT_CONFIG["bg_alpha"]))
        adaptive_targets = self.config_data.get("adaptive_targets", {})
        self.use_adaptive_font_color = bool(adaptive_targets.get("font_color", True)) if isinstance(adaptive_targets, dict) else True
        self.use_adaptive_font_size = bool(adaptive_targets.get("font_size", True)) if isinstance(adaptive_targets, dict) else True
        self.use_adaptive_bg_color = bool(adaptive_targets.get("bg_color", True)) if isinstance(adaptive_targets, dict) else True
        self.use_adaptive_font_spacing = bool(adaptive_targets.get("font_spacing", False)) if isinstance(adaptive_targets, dict) else False
        self.use_adaptive_line_spacing = bool(adaptive_targets.get("line_spacing", False)) if isinstance(adaptive_targets, dict) else False
        self._bg_alpha_disabled_tip = "鼠标穿透问题，暂时置灰“0%”选项"
        self._bg_alpha_zero_index = -1
        layout = QtWidgets.QVBoxLayout(self)
        form = QtWidgets.QFormLayout()
        self.font_btn = QtWidgets.QPushButton()
        self.font_btn.clicked.connect(self.pick_font)
        form.addRow("字体", self.font_btn)
        self.font_color_btn = QtWidgets.QPushButton()
        self.font_color_btn.clicked.connect(self.pick_font_color)
        form.addRow("字体颜色", self.font_color_btn)
        self.bg_color_btn = QtWidgets.QPushButton()
        self.bg_color_btn.clicked.connect(self.pick_bg_color)
        form.addRow("背景颜色", self.bg_color_btn)
        self.font_alpha_combo = QtWidgets.QComboBox()
        for val in (1.0, 0.85, 0.7, 0.5, 0.3, 0.1, 0.0):
            self.font_alpha_combo.addItem(f"{int(val * 100)}%", val)
        form.addRow("字体不透明度", self.font_alpha_combo)
        self.bg_alpha_combo = QtWidgets.QComboBox()
        for val in (1.0, 0.85, 0.7, 0.5, 0.3, 0.0):
            text = "0% (仅文字)" if val == 0.0 else f"{int(val * 100)}%"
            self.bg_alpha_combo.addItem(text, val)
        form.addRow("背景不透明度", self.bg_alpha_combo)
        self.font_spacing_slider = QtWidgets.QSlider(QtCore.Qt.Orientation.Horizontal if PYQT6 else QtCore.Qt.Horizontal)
        self.font_spacing_slider.setRange(0, 20)
        self.font_spacing_slider.setSingleStep(1)
        self.font_spacing_value = QtWidgets.QLabel()
        self.font_spacing_reset_btn = QtWidgets.QPushButton("默认")
        self.font_spacing_reset_btn.clicked.connect(self._reset_font_spacing)
        self.font_spacing_slider.valueChanged.connect(self._on_font_spacing_changed)
        font_spacing_row = QtWidgets.QWidget()
        font_spacing_layout = QtWidgets.QHBoxLayout(font_spacing_row)
        font_spacing_layout.setContentsMargins(0, 0, 0, 0)
        font_spacing_layout.setSpacing(8)
        font_spacing_layout.addWidget(self.font_spacing_slider)
        font_spacing_layout.addWidget(self.font_spacing_value)
        font_spacing_layout.addWidget(self.font_spacing_reset_btn)
        form.addRow("字体间距", font_spacing_row)
        self.line_spacing_slider = QtWidgets.QSlider(QtCore.Qt.Orientation.Horizontal if PYQT6 else QtCore.Qt.Horizontal)
        self.line_spacing_slider.setRange(100, 220)
        self.line_spacing_slider.setSingleStep(5)
        self.line_spacing_value = QtWidgets.QLabel()
        self.line_spacing_reset_btn = QtWidgets.QPushButton("默认")
        self.line_spacing_reset_btn.clicked.connect(self._reset_line_spacing)
        self.line_spacing_slider.valueChanged.connect(self._on_line_spacing_changed)
        line_spacing_row = QtWidgets.QWidget()
        line_spacing_layout = QtWidgets.QHBoxLayout(line_spacing_row)
        line_spacing_layout.setContentsMargins(0, 0, 0, 0)
        line_spacing_layout.setSpacing(8)
        line_spacing_layout.addWidget(self.line_spacing_slider)
        line_spacing_layout.addWidget(self.line_spacing_value)
        line_spacing_layout.addWidget(self.line_spacing_reset_btn)
        form.addRow("行距", line_spacing_row)
        self._disable_zero_bg_alpha_option()
        self.bg_alpha_combo.highlighted.connect(self._on_bg_alpha_highlighted)
        layout.addLayout(form)
        self.section_divider = QtWidgets.QFrame()
        self.section_divider.setObjectName("sectionDivider")
        self.section_divider.setFrameShape(QtWidgets.QFrame.Shape.HLine if PYQT6 else QtWidgets.QFrame.HLine)
        self.section_divider.setFrameShadow(QtWidgets.QFrame.Shadow.Plain if PYQT6 else QtWidgets.QFrame.Plain)
        layout.addWidget(self.section_divider)
        self.adaptive_btn = QtWidgets.QPushButton("自适应识别字体与背景")
        self.adaptive_btn.setObjectName("adaptiveBtn")
        self.adaptive_btn.clicked.connect(self.adaptive_detect_style)
        self.adaptive_btn.setMinimumHeight(40)
        layout.addWidget(self.adaptive_btn)
        self.adaptive_targets_row = QtWidgets.QHBoxLayout()
        self.adaptive_targets_row.setSpacing(12)
        self.adaptive_font_color_check = QtWidgets.QCheckBox("字体颜色")
        self.adaptive_font_color_check.setChecked(self.use_adaptive_font_color)
        self.adaptive_font_size_check = QtWidgets.QCheckBox("字体字号")
        self.adaptive_font_size_check.setChecked(self.use_adaptive_font_size)
        self.adaptive_bg_color_check = QtWidgets.QCheckBox("背景色")
        self.adaptive_bg_color_check.setChecked(self.use_adaptive_bg_color)
        self.adaptive_font_spacing_check = QtWidgets.QCheckBox("字距")
        self.adaptive_font_spacing_check.setChecked(self.use_adaptive_font_spacing)
        self.adaptive_line_spacing_check = QtWidgets.QCheckBox("行距")
        self.adaptive_line_spacing_check.setChecked(self.use_adaptive_line_spacing)
        self.adaptive_targets_row.addWidget(self.adaptive_font_color_check)
        self.adaptive_targets_row.addWidget(self.adaptive_font_size_check)
        self.adaptive_targets_row.addWidget(self.adaptive_bg_color_check)
        self.adaptive_targets_row.addWidget(self.adaptive_font_spacing_check)
        self.adaptive_targets_row.addWidget(self.adaptive_line_spacing_check)
        self.adaptive_targets_row.addStretch(1)
        layout.addLayout(self.adaptive_targets_row)
        self.status_label = QtWidgets.QLabel("")
        self.status_label.setStyleSheet("color: #4B5563; font-size: 12px;")
        self.status_label.setWordWrap(True)
        layout.addWidget(self.status_label)
        self.button_box = QtWidgets.QDialogButtonBox(
            QtWidgets.QDialogButtonBox.StandardButton.Ok | QtWidgets.QDialogButtonBox.StandardButton.Cancel
            if PYQT6
            else QtWidgets.QDialogButtonBox.Ok | QtWidgets.QDialogButtonBox.Cancel
        )
        self.button_box.accepted.connect(self.accept)
        self.button_box.rejected.connect(self.reject)
        layout.addWidget(self.button_box)
        self.setStyleSheet(
            "QDialog { background: #F3F4F6; color: #1F2937; }"
            "QLabel { color: #374151; }"
            "QPushButton { background: #E5E7EB; border: 1px solid #D1D5DB; border-radius: 8px; padding: 6px 10px; color: #111827; }"
            "QPushButton:hover { background: #DDE1E6; }"
            "QComboBox { background: #FFFFFF; border: 1px solid #D1D5DB; border-radius: 8px; padding: 6px 8px; }"
            "QFrame#sectionDivider { background: #D1D5DB; min-height: 1px; max-height: 1px; border: none; margin-top: 6px; margin-bottom: 6px; }"
            "QPushButton#adaptiveBtn { background: #D7E3F3; border: 1px solid #AFC4DE; color: #0F2742; font-weight: 600; }"
            "QPushButton#adaptiveBtn:hover { background: #C9DAEF; }"
            "QPushButton#adaptiveBtn:pressed { background: #BCD1EA; }"
            "QCheckBox { color: #374151; spacing: 6px; }"
        )
        self._sync_controls()

    def _debug(self, message: str) -> None:
        print(f"[SettingsDebug] {message}", flush=True)

    def _sync_controls(self) -> None:
        self.font_btn.setText(f"{self.font_family} {self.font_size}pt")
        self.font_color_btn.setText(self.font_color)
        self.font_color_btn.setStyleSheet(
            f"QPushButton {{ background: {self.font_color}; color: {'#111827' if self._light_color(self.font_color) else '#F9FAFB'}; "
            "border: 1px solid #9CA3AF; border-radius: 8px; padding: 6px 10px; }"
        )
        self.bg_color_btn.setText(self.bg_color)
        self.bg_color_btn.setStyleSheet(
            f"QPushButton {{ background: {self.bg_color}; color: {'#111827' if self._light_color(self.bg_color) else '#F9FAFB'}; "
            "border: 1px solid #9CA3AF; border-radius: 8px; padding: 6px 10px; }"
        )
        self._set_combo_value(self.font_alpha_combo, self.font_alpha)
        self._set_combo_value(self.bg_alpha_combo, self.bg_alpha)
        self.font_spacing_slider.setValue(int(round(self.font_spacing)))
        self.line_spacing_slider.setValue(int(round(self.line_spacing * 100)))
        self.font_spacing_value.setText(f"{int(round(self.font_spacing))} px")
        self.line_spacing_value.setText(f"{int(round(self.line_spacing * 100))}%")

    def _set_combo_value(self, combo: QtWidgets.QComboBox, value: float) -> None:
        for i in range(combo.count()):
            data = combo.itemData(i)
            if abs(float(data) - value) < 1e-6:
                model = combo.model()
                item = model.item(i) if hasattr(model, "item") else None
                if item is not None and not item.isEnabled():
                    continue
                combo.setCurrentIndex(i)
                return
        if combo.count() > 0:
            combo.setCurrentIndex(0)

    def _disable_zero_bg_alpha_option(self) -> None:
        self._bg_alpha_zero_index = self._find_combo_data_index(self.bg_alpha_combo, 0.0)
        if self._bg_alpha_zero_index < 0:
            return
        tool_tip_role = QtCore.Qt.ItemDataRole.ToolTipRole if PYQT6 else QtCore.Qt.ToolTipRole
        self.bg_alpha_combo.setItemData(self._bg_alpha_zero_index, self._bg_alpha_disabled_tip, tool_tip_role)
        model = self.bg_alpha_combo.model()
        item = model.item(self._bg_alpha_zero_index) if hasattr(model, "item") else None
        if item is not None:
            item.setEnabled(False)
        self.bg_alpha_combo.setToolTip(self._bg_alpha_disabled_tip)
        if abs(self.bg_alpha - 0.0) < 1e-6:
            self.bg_alpha = 1.0

    def _find_combo_data_index(self, combo: QtWidgets.QComboBox, target: float) -> int:
        for i in range(combo.count()):
            try:
                data = float(combo.itemData(i))
            except Exception:
                continue
            if abs(data - target) < 1e-6:
                return i
        return -1

    def _on_bg_alpha_highlighted(self, index: int) -> None:
        if index == self._bg_alpha_zero_index:
            QtWidgets.QToolTip.showText(QtGui.QCursor.pos(), self._bg_alpha_disabled_tip, self.bg_alpha_combo)

    def _on_font_spacing_changed(self, value: int) -> None:
        self.font_spacing = float(value)
        self.font_spacing_value.setText(f"{value} px")

    def _on_line_spacing_changed(self, value: int) -> None:
        self.line_spacing = max(1.0, value / 100.0)
        self.line_spacing_value.setText(f"{value}%")

    def _reset_font_spacing(self) -> None:
        self.font_spacing_slider.setValue(0)

    def _reset_line_spacing(self) -> None:
        self.line_spacing_slider.setValue(100)

    def _light_color(self, hex_color: str) -> bool:
        color = QtGui.QColor(hex_color)
        if not color.isValid():
            return True
        luma = 0.2126 * color.red() + 0.7152 * color.green() + 0.0722 * color.blue()
        return luma >= 140

    def pick_font(self) -> None:
        font, ok = QtWidgets.QFontDialog.getFont(QtGui.QFont(self.font_family, self.font_size), self)
        if ok:
            self.font_family = font.family()
            self.font_size = font.pointSize()
            self._sync_controls()

    def pick_font_color(self) -> None:
        color = QtWidgets.QColorDialog.getColor(QtGui.QColor(self.font_color), self)
        if color.isValid():
            self.font_color = color.name()
            self._sync_controls()

    def pick_bg_color(self) -> None:
        color = QtWidgets.QColorDialog.getColor(QtGui.QColor(self.bg_color), self)
        if color.isValid():
            self.bg_color = color.name()
            self._sync_controls()

    def adaptive_detect_style(self) -> None:
        self._debug("点击自适应识别按钮")
        use_font_color = self.adaptive_font_color_check.isChecked()
        use_font_size = self.adaptive_font_size_check.isChecked()
        use_bg_color = self.adaptive_bg_color_check.isChecked()
        use_font_spacing = self.adaptive_font_spacing_check.isChecked()
        use_line_spacing = self.adaptive_line_spacing_check.isChecked()
        if not (use_font_color or use_font_size or use_bg_color or use_font_spacing or use_line_spacing):
            QtWidgets.QMessageBox.information(self, "自适应识别", "请至少勾选一个识别项")
            return
        self.hide()
        self._debug("设置弹窗已隐藏，准备圈选区域")
        QtWidgets.QApplication.processEvents()
        selector = RegionSelectionOverlay(self)
        selected_rect = selector.select_region()
        if selected_rect is None:
            self._debug("圈选取消或区域无效，恢复设置弹窗")
            self._restore_dialog_after_detect()
            return
        self._debug(f"圈选完成 rect=({selected_rect.x()}, {selected_rect.y()}, {selected_rect.width()}, {selected_rect.height()})")
        image = self._capture_region_image(selected_rect)
        if image is None or image.isNull():
            self._debug("截图失败，恢复设置弹窗并提示")
            self._restore_dialog_after_detect()
            QtWidgets.QMessageBox.warning(self, "自适应识别", "识别失败：无法获取圈选区域图像")
            return
        bg_hex, font_hex = self._detect_style_colors(image)
        if bg_hex is None or font_hex is None:
            self._debug("颜色识别失败，恢复设置弹窗并提示")
            self._restore_dialog_after_detect()
            QtWidgets.QMessageBox.warning(self, "自适应识别", "识别失败：未能提取有效颜色")
            return
        font_size = self._estimate_font_size(image, bg_hex, font_hex) if use_font_size else None
        font_spacing = self._estimate_font_spacing(image, bg_hex, font_hex) if use_font_spacing else None
        line_spacing = self._estimate_line_spacing(image, bg_hex, font_hex) if use_line_spacing else None
        self._debug(
            f"识别结果 bg={bg_hex}, font={font_hex}, size={font_size}, font_spacing={font_spacing}, "
            f"line_spacing={line_spacing}, targets={use_font_color}/{use_font_size}/{use_bg_color}/{use_font_spacing}/{use_line_spacing}"
        )
        self._restore_dialog_after_detect(disable_ms=0)
        self.button_box.setEnabled(False)
        self.adaptive_btn.setEnabled(False)
        self._debug("确认弹窗显示期间保持设置弹窗按钮禁用")
        msg = QtWidgets.QMessageBox(self)
        msg.setWindowTitle("确认应用识别结果")
        msg.setIcon(QtWidgets.QMessageBox.Icon.Question if PYQT6 else QtWidgets.QMessageBox.Question)
        result_lines = ["识别完成："]
        if use_bg_color:
            result_lines.append(f"背景色：{bg_hex}")
        if use_font_color:
            result_lines.append(f"字体颜色：{font_hex}")
        if use_font_size and font_size is not None:
            result_lines.append(f"建议字号：{font_size}pt")
        if use_font_spacing and font_spacing is not None:
            result_lines.append(f"建议字距：{font_spacing:.0f}px")
        if use_line_spacing and line_spacing is not None:
            result_lines.append(f"建议行距：{int(round(line_spacing * 100))}%")
        result_lines.append("\n是否应用到当前设置？")
        msg.setText("\n".join(result_lines))
        yes_button = msg.addButton("应用", QtWidgets.QMessageBox.ButtonRole.AcceptRole)
        msg.addButton("取消", QtWidgets.QMessageBox.ButtonRole.RejectRole)
        msg.setDefaultButton(yes_button)
        
        # 使用 open() 非阻塞显示，并通过信号处理结果，彻底避免 exec() 事件循环嵌套导致的模态窗口关闭异常
        msg.open()
        
        def handle_msg_finished():
            should_apply = msg.clickedButton() == yes_button
            if should_apply:
                if use_bg_color:
                    self.bg_color = bg_hex
                if use_font_color:
                    self.font_color = font_hex
                if use_font_size and font_size is not None:
                    self.font_size = font_size
                if use_font_spacing and font_spacing is not None:
                    self.font_spacing = font_spacing
                if use_line_spacing and line_spacing is not None:
                    self.line_spacing = line_spacing
                self._sync_controls()
                self._save_current_settings()
                self.status_label.setText("已应用并保存识别结果")
            QtCore.QTimer.singleShot(100, self._enable_dialog_actions)

        msg.finished.connect(handle_msg_finished)

    def _restore_dialog_after_detect(self, disable_ms: int = 200) -> None:
        self.show()
        self.raise_()
        self.activateWindow()
        self._debug("设置弹窗已恢复显示")
        if disable_ms > 0:
            self.button_box.setEnabled(False)
            self.adaptive_btn.setEnabled(False)
            QtCore.QTimer.singleShot(disable_ms, self._enable_dialog_actions)
            self._debug("设置弹窗按钮已短暂禁用，防止点击穿透")

    def _enable_dialog_actions(self) -> None:
        self.button_box.setEnabled(True)
        self.adaptive_btn.setEnabled(True)
        self._debug("设置弹窗按钮已恢复可点击")

    def _save_current_settings(self) -> None:
        self.config_data["font_family"] = self.font_family
        self.config_data["font_size"] = self.font_size
        self.config_data["font_color"] = self.font_color
        self.config_data["bg_color"] = self.bg_color
        self.config_data["font_alpha"] = self.font_alpha
        self.config_data["font_spacing"] = self.font_spacing
        self.config_data["line_spacing"] = self.line_spacing
        self.config_data["bg_alpha"] = self.bg_alpha
        self.config_data["adaptive_targets"] = {
            "font_color": self.adaptive_font_color_check.isChecked(),
            "font_size": self.adaptive_font_size_check.isChecked(),
            "bg_color": self.adaptive_bg_color_check.isChecked(),
            "font_spacing": self.adaptive_font_spacing_check.isChecked(),
            "line_spacing": self.adaptive_line_spacing_check.isChecked(),
        }
        save_config_data(self.config_data)
        self._debug(
            f"即时保存设置 font={self.font_family}/{self.font_size}, font_color={self.font_color}, "
            f"bg_color={self.bg_color}, font_alpha={self.font_alpha}, bg_alpha={self.bg_alpha}, "
            f"font_spacing={self.font_spacing}, line_spacing={self.line_spacing}"
        )

    def _capture_region_image(self, rect: QtCore.QRect) -> QtGui.QImage | None:
        if rect.width() <= 1 or rect.height() <= 1:
            return None
        center = rect.center()
        screen = QtGui.QGuiApplication.screenAt(center)
        if screen is None:
            screen = QtGui.QGuiApplication.primaryScreen()
        if screen is None:
            return None
        geo = screen.geometry()
        x = rect.x() - geo.x()
        y = rect.y() - geo.y()
        pixmap = screen.grabWindow(0, x, y, rect.width(), rect.height())
        if pixmap.isNull():
            return None
        return pixmap.toImage()

    def _detect_style_colors(self, image: QtGui.QImage) -> tuple[str | None, str | None]:
        w = image.width()
        h = image.height()
        if w <= 0 or h <= 0:
            return None, None
        max_samples = 60000
        step = max(1, int(((w * h) / max_samples) ** 0.5))
        bins: dict[tuple[int, int, int], int] = {}
        sums: dict[tuple[int, int, int], list[int]] = defaultdict(lambda: [0, 0, 0, 0])
        total = 0
        for y in range(0, h, step):
            for x in range(0, w, step):
                color = QtGui.QColor(image.pixel(x, y))
                if color.alpha() < 10:
                    continue
                r, g, b = color.red(), color.green(), color.blue()
                key_bin = (r // 16, g // 16, b // 16)
                bins[key_bin] = bins.get(key_bin, 0) + 1
                data = sums[key_bin]
                data[0] += r
                data[1] += g
                data[2] += b
                data[3] += 1
                total += 1
        if total == 0 or not bins:
            return None, None
        sorted_bins = sorted(bins.items(), key=lambda item: item[1], reverse=True)
        bg_bin = sorted_bins[0][0]
        bg_rgb = self._avg_rgb_from_bin(bg_bin, sums)
        bg_luma = self._luminance(*bg_rgb)
        font_rgb = None
        best_score = -1.0
        for key_bin, count in sorted_bins[1:20]:
            rgb = self._avg_rgb_from_bin(key_bin, sums)
            contrast = abs(self._luminance(*rgb) - bg_luma)
            score = contrast * ((count / total) ** 0.35)
            if contrast >= 35 and score > best_score:
                font_rgb = rgb
                best_score = score
        if font_rgb is None:
            if bg_luma >= 140:
                font_rgb = (0, 0, 0)
            else:
                font_rgb = (255, 255, 255)
        bg_hex = "#{:02x}{:02x}{:02x}".format(*bg_rgb)
        font_hex = "#{:02x}{:02x}{:02x}".format(*font_rgb)
        if bg_hex == font_hex:
            font_hex = "#000000" if self._luminance(*bg_rgb) >= 128 else "#ffffff"
        return bg_hex, font_hex

    def _avg_rgb_from_bin(self, key_bin: tuple[int, int, int], sums: dict[tuple[int, int, int], list[int]]) -> tuple[int, int, int]:
        data = sums[key_bin]
        count = max(1, data[3])
        return (data[0] // count, data[1] // count, data[2] // count)

    def _estimate_font_size(self, image: QtGui.QImage, bg_hex: str, font_hex: str) -> int | None:
        w = image.width()
        h = image.height()
        if w < 10 or h < 10:
            return None
        bg = QtGui.QColor(bg_hex)
        fg = QtGui.QColor(font_hex)
        bg_rgb = (bg.red(), bg.green(), bg.blue())
        fg_rgb = (fg.red(), fg.green(), fg.blue())
        step_x = max(1, w // 120)
        runs: list[int] = []
        for x in range(0, w, step_x):
            run = 0
            for y in range(h):
                c = QtGui.QColor(image.pixel(x, y))
                rgb = (c.red(), c.green(), c.blue())
                to_fg = self._rgb_distance_sq(rgb, fg_rgb)
                to_bg = self._rgb_distance_sq(rgb, bg_rgb)
                is_text = to_fg < to_bg and to_fg < 16000
                if is_text:
                    run += 1
                else:
                    if 4 <= run <= 120:
                        runs.append(run)
                    run = 0
            if 4 <= run <= 120:
                runs.append(run)
        if not runs:
            return None
        runs.sort()
        px_height = runs[len(runs) // 2]
        estimate_pt = int(round(px_height * 0.72))
        return max(10, min(42, estimate_pt))

    def _estimate_font_spacing(self, image: QtGui.QImage, bg_hex: str, font_hex: str) -> float | None:
        w = image.width()
        h = image.height()
        if w < 20 or h < 10:
            return None
        bg = QtGui.QColor(bg_hex)
        fg = QtGui.QColor(font_hex)
        bg_rgb = (bg.red(), bg.green(), bg.blue())
        fg_rgb = (fg.red(), fg.green(), fg.blue())
        step_y = max(1, h // 45)
        gap_values: list[int] = []
        for y in range(0, h, step_y):
            run = 0
            gaps: list[int] = []
            in_text = False
            for x in range(w):
                c = QtGui.QColor(image.pixel(x, y))
                rgb = (c.red(), c.green(), c.blue())
                to_fg = self._rgb_distance_sq(rgb, fg_rgb)
                to_bg = self._rgb_distance_sq(rgb, bg_rgb)
                is_text = to_fg < to_bg and to_fg < 16000
                if is_text:
                    if not in_text and run > 0:
                        gaps.append(run)
                    in_text = True
                    run = 0
                else:
                    if in_text:
                        run = 1
                    elif run > 0:
                        run += 1
                    in_text = False
            compact_gaps = [g for g in gaps if 1 <= g <= 14]
            if len(compact_gaps) >= 3:
                gap_values.extend(compact_gaps)
        if not gap_values:
            return None
        gap_values.sort()
        baseline_gap = gap_values[len(gap_values) // 4]
        spacing = max(0.0, float(baseline_gap - 1))
        return min(20.0, spacing)

    def _estimate_line_spacing(self, image: QtGui.QImage, bg_hex: str, font_hex: str) -> float | None:
        w = image.width()
        h = image.height()
        if w < 20 or h < 20:
            return None
        bg = QtGui.QColor(bg_hex)
        fg = QtGui.QColor(font_hex)
        bg_rgb = (bg.red(), bg.green(), bg.blue())
        fg_rgb = (fg.red(), fg.green(), fg.blue())
        row_text_counts: list[int] = []
        for y in range(h):
            text_count = 0
            for x in range(0, w, max(1, w // 220)):
                c = QtGui.QColor(image.pixel(x, y))
                rgb = (c.red(), c.green(), c.blue())
                to_fg = self._rgb_distance_sq(rgb, fg_rgb)
                to_bg = self._rgb_distance_sq(rgb, bg_rgb)
                if to_fg < to_bg and to_fg < 16000:
                    text_count += 1
            row_text_counts.append(text_count)
        active_rows = [i for i, count in enumerate(row_text_counts) if count >= 2]
        if len(active_rows) < 8:
            return None
        text_runs: list[int] = []
        gap_runs: list[int] = []
        start = active_rows[0]
        prev = active_rows[0]
        for idx in active_rows[1:]:
            if idx == prev + 1:
                prev = idx
                continue
            text_runs.append(prev - start + 1)
            gap_runs.append(idx - prev - 1)
            start = idx
            prev = idx
        text_runs.append(prev - start + 1)
        text_runs = [run for run in text_runs if run >= 2]
        gap_runs = [gap for gap in gap_runs if gap >= 1]
        if not text_runs or not gap_runs:
            return None
        text_runs.sort()
        gap_runs.sort()
        text_height = text_runs[len(text_runs) // 2]
        gap_height = gap_runs[len(gap_runs) // 2]
        line_spacing = (text_height + gap_height) / max(1, text_height)
        return min(2.2, max(1.0, float(line_spacing)))

    def _rgb_distance_sq(self, a: tuple[int, int, int], b: tuple[int, int, int]) -> int:
        dr = a[0] - b[0]
        dg = a[1] - b[1]
        db = a[2] - b[2]
        return dr * dr + dg * dg + db * db

    def _luminance(self, r: int, g: int, b: int) -> float:
        return 0.2126 * r + 0.7152 * g + 0.0722 * b

    def accept(self) -> None:
        self._debug(f"触发设置弹窗accept，sender={type(self.sender()).__name__ if self.sender() else 'None'}")
        self.font_alpha = float(self.font_alpha_combo.currentData())
        self.bg_alpha = float(self.bg_alpha_combo.currentData())
        self.font_spacing = float(self.font_spacing_slider.value())
        self.line_spacing = max(1.0, self.line_spacing_slider.value() / 100.0)
        self._save_current_settings()
        super().accept()

    def reject(self) -> None:
        self._debug(f"触发设置弹窗reject，sender={type(self.sender()).__name__ if self.sender() else 'None'}")
        super().reject()

    def done(self, r: int) -> None:
        self._debug(f"设置弹窗done result={r}")
        super().done(r)

    def showEvent(self, event) -> None:
        super().showEvent(event)

    def hideEvent(self, event) -> None:
        super().hideEvent(event)

    def closeEvent(self, event) -> None:
        super().closeEvent(event)


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
        print("[SettingsDebug] 打开圈选遮罩窗口", flush=True)
        self.show()
        self.raise_()
        self.activateWindow()
        if PYQT6:
            self._loop.exec()
        else:
            self._loop.exec_()
        if self._selected_rect is None:
            print("[SettingsDebug] 圈选结果为空", flush=True)
        else:
            r = self._selected_rect
            print(f"[SettingsDebug] 圈选结果=({r.x()}, {r.y()}, {r.width()}, {r.height()})", flush=True)
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
        esc_key = QtCore.Qt.Key.Key_Escape if PYQT6 else QtCore.Qt.Key_Escape
        if event.key() == esc_key:
            print("[SettingsDebug] 圈选按下ESC取消", flush=True)
            self._selected_rect = None
            self.close()
            self._loop.quit()
            return
        super().keyPressEvent(event)


class HomeWindow(QtWidgets.QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("EpubReader")
        self.resize(920, 620)
        self.reader: ReaderWindow | None = None
        self.config_data = load_config_data()
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
        self.reader = ReaderWindow(on_back_home=open_home_window)
        keep_window_ref(self.reader)
        self.reader.load_file(file_path)
        self.reader.show()
        self.close()


def open_home_window() -> HomeWindow:
    window = HomeWindow()
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
