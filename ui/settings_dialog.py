from qt_compat import PYQT6, QtCore, QtGui, QtWidgets
from services.config_service import DEFAULT_CONFIG, load_config_data, save_config_data
from services.style_detect_service import (
    capture_region_image,
    detect_style_colors,
    estimate_font_size,
    estimate_font_spacing,
    estimate_line_spacing,
)
from ui.overlay import RegionSelectionOverlay


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
        image = capture_region_image(selected_rect)
        if image is None or image.isNull():
            self._debug("截图失败，恢复设置弹窗并提示")
            self._restore_dialog_after_detect()
            QtWidgets.QMessageBox.warning(self, "自适应识别", "识别失败：无法获取圈选区域图像")
            return
        bg_hex, font_hex = detect_style_colors(image)
        if bg_hex is None or font_hex is None:
            self._debug("颜色识别失败，恢复设置弹窗并提示")
            self._restore_dialog_after_detect()
            QtWidgets.QMessageBox.warning(self, "自适应识别", "识别失败：未能提取有效颜色")
            return
        font_size = estimate_font_size(image, bg_hex, font_hex) if use_font_size else None
        font_spacing = estimate_font_spacing(image, bg_hex, font_hex) if use_font_spacing else None
        line_spacing = estimate_line_spacing(image, bg_hex, font_hex) if use_line_spacing else None
        self._debug(
            f"识别结果 bg={bg_hex}, font={font_hex}, size={font_size}, font_spacing={font_spacing}, "
            f"line_spacing={line_spacing}, targets={use_font_color}/{use_font_size}/{use_bg_color}/{use_font_spacing}/{use_line_spacing}"
        )
        self._restore_dialog_after_detect(disable_ms=0)
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
        ask = QtWidgets.QMessageBox.question(
            self,
            "确认应用识别结果",
            "\n".join(result_lines),
            QtWidgets.QMessageBox.StandardButton.Yes | QtWidgets.QMessageBox.StandardButton.No
            if PYQT6
            else QtWidgets.QMessageBox.Yes | QtWidgets.QMessageBox.No,
            QtWidgets.QMessageBox.StandardButton.Yes if PYQT6 else QtWidgets.QMessageBox.Yes,
        )
        yes_btn = QtWidgets.QMessageBox.StandardButton.Yes if PYQT6 else QtWidgets.QMessageBox.Yes
        if ask == yes_btn:
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
