import ctypes
import ctypes.wintypes
import json
import os
import pathlib
import bisect
import sys
from collections import defaultdict

from epub_utils import parse_epub_chapters, read_text_with_fallback
from qt_compat import (
    PYQT6,
    QtCore,
    QtGui,
    QtWidgets,
    context_menu_policy,
    cursor_shape,
    event_type,
    global_pos,
    key,
    local_pos,
    mouse_button,
    no_frame,
    window_flag,
    widget_attribute,
)


class ReaderWindow(QtWidgets.QMainWindow):
    def __init__(self, on_back_home=None) -> None:
        super().__init__()
        self.setWindowTitle("简易阅读器")
        self.setGeometry(100, 100, 900, 600)
        self.on_back_home = on_back_home

        self.content = ""
        self.chapters: list[dict[str, str]] = []
        self.chapter_index = 0
        self.page_index = 0
        self.page_cache: dict[int, list[str]] = {}
        self.page_char_offsets: dict[int, list[int]] = {}
        self.current_path: str | None = None

        self.font_family = "微软雅黑"
        self.font_size = 18
        self.font_color = "#000000"
        self.font_alpha = 1.0
        self.bg_color = "#F2F2F2"
        self.alpha = 1.0
        self.borderless = True
        self.anti_capture = True

        self._drag_offset: QtCore.QPoint | None = None
        self._resize_dir: str | None = None
        self._start_geom: QtCore.QRect | None = None
        self._start_pos: QtCore.QPoint | None = None
        self._press_global: QtCore.QPoint | None = None
        self._press_pos_window: QtCore.QPoint | None = None
        self._moved = False
        self._release_handled = False

        self.progress_path = pathlib.Path.home() / ".epubrand_progress.json"
        self.progress_data = self._load_progress_data()
        
        # 适配打包后的路径
        if getattr(sys, 'frozen', False):
            # 如果是打包后的 EXE，配置文件放在 EXE 同级目录
            self.base_path = pathlib.Path(sys.executable).parent
        else:
            # 开发环境，放在文件同级目录
            self.base_path = pathlib.Path(__file__).resolve().parent

        self.config_path = self.base_path / "reader_config.json"
        self.config_data = self._load_config_data()
        self.last_open_path = self.config_data.get("last_path", "")
        self.page_prev_shortcut_text = self._load_shortcut_text("prev_page", "A")
        self.page_next_shortcut_text = self._load_shortcut_text("next_page", "D")
        self.toggle_visible_shortcut_text = self._load_shortcut_text("toggle_visible", "Alt+V")
        self.close_app_shortcut_text = self._load_shortcut_text("close_app", "Alt+Esc")
        self.font_family = self.config_data.get("font_family", self.font_family)
        self.font_size = int(self.config_data.get("font_size", self.font_size))
        self.font_color = self.config_data.get("font_color", self.font_color)
        self.font_alpha = float(self.config_data.get("font_alpha", self.font_alpha))
        self.bg_color = self.config_data.get("bg_color", self.bg_color)
        self.alpha = float(self.config_data.get("bg_alpha", self.alpha))

        self.text = QtWidgets.QTextEdit()
        self.text.setReadOnly(True)
        self.text.setContextMenuPolicy(context_menu_policy())
        self.text.customContextMenuRequested.connect(self.show_menu)
        self.text.installEventFilter(self)
        self.text.viewport().installEventFilter(self)
        self.text.setFrameShape(no_frame())
        if PYQT6:
            self.text.setVerticalScrollBarPolicy(QtCore.Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
            self.text.setHorizontalScrollBarPolicy(QtCore.Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        else:
            self.text.setVerticalScrollBarPolicy(QtCore.Qt.ScrollBarAlwaysOff)
            self.text.setHorizontalScrollBarPolicy(QtCore.Qt.ScrollBarAlwaysOff)
        self.text.setStyleSheet(f"QTextEdit {{ background-color: {self.bg_color}; border: 0px; }}")
        self.setCentralWidget(self.text)

        self.setContextMenuPolicy(context_menu_policy())
        self.customContextMenuRequested.connect(self.show_menu)

        self.setMouseTracking(True)
        self.text.setMouseTracking(True)
        self.text.viewport().setMouseTracking(True)
        self._runtime_shortcuts: list[QtGui.QShortcut] = []
        self._setup_runtime_shortcuts()

        # 1. 先设置无边框标志，这对 WA_TranslucentBackground 很重要
        if self.borderless:
            self.setWindowFlag(window_flag("FramelessWindowHint"), True)
            
        # 2. 全局启用透明背景属性
        self.setAttribute(widget_attribute("WA_TranslucentBackground"))
        
        # 3. 移除可能导致点击穿透的属性
        # 确保窗口能接收鼠标事件，防止点到下层程序
        self.setAttribute(widget_attribute("WA_TransparentForMouseEvents"), False)

        # 4. 初始化样式和属性（不调用 show）
        self.apply_style()
        self.apply_anti_capture()

    def _load_progress_data(self) -> dict:
        try:
            if self.progress_path.exists():
                return json.loads(self.progress_path.read_text(encoding="utf-8"))
        except Exception:
            pass
        return {}

    def _save_progress_data(self) -> None:
        try:
            self.progress_path.write_text(json.dumps(self.progress_data, ensure_ascii=False), encoding="utf-8")
        except Exception:
            pass

    def _load_config_data(self) -> dict:
        try:
            if self.config_path.exists():
                return json.loads(self.config_path.read_text(encoding="utf-8"))
        except Exception:
            pass
        return {}

    def _save_config_data(self) -> None:
        try:
            self.config_path.write_text(json.dumps(self.config_data, ensure_ascii=False, indent=2), encoding="utf-8")
        except Exception:
            pass

    def _save_settings(self) -> None:
        self.config_data["font_family"] = self.font_family
        self.config_data["font_size"] = self.font_size
        self.config_data["font_color"] = self.font_color
        self.config_data["font_alpha"] = self.font_alpha
        self.config_data["bg_color"] = self.bg_color
        self.config_data["bg_alpha"] = self.alpha
        self._save_config_data()

    def _remember_last_path(self, path: str) -> None:
        self.config_data["last_path"] = path
        recent_paths = self.config_data.get("recent_paths", [])
        if not isinstance(recent_paths, list):
            recent_paths = []
        normalized_recent = []
        for p in recent_paths:
            if not isinstance(p, str):
                continue
            try:
                normalized = str(pathlib.Path(p).expanduser().resolve())
            except Exception:
                continue
            if normalized not in normalized_recent:
                normalized_recent.append(normalized)
        if path in normalized_recent:
            normalized_recent.remove(path)
        normalized_recent.insert(0, path)
        self.config_data["recent_paths"] = normalized_recent[:20]
        self.last_open_path = path
        self._save_config_data()

    def _load_shortcut_text(self, action: str, default_value: str) -> str:
        shortcuts = self.config_data.get("shortcuts", {})
        action_value = shortcuts.get(action) if isinstance(shortcuts, dict) else None
        if isinstance(action_value, str) and action_value.strip():
            return action_value.strip()
        return default_value

    def _setup_runtime_shortcuts(self) -> None:
        self._runtime_shortcuts.clear()
        context = QtCore.Qt.ShortcutContext.ApplicationShortcut if PYQT6 else QtCore.Qt.ApplicationShortcut
        bindings = [
            (self.page_prev_shortcut_text, self.prev_page),
            (self.page_next_shortcut_text, self.next_page),
            (self.toggle_visible_shortcut_text, self._toggle_visibility),
            (self.close_app_shortcut_text, self.close),
        ]
        if self.close_app_shortcut_text.strip().lower() == "alt+esc":
            bindings.append(("Alt+Q", self.close))
        for key_text, handler in bindings:
            sequence = QtGui.QKeySequence(key_text)
            if sequence.count() <= 0:
                continue
            shortcut = QtWidgets.QShortcut(sequence, self)
            shortcut.setContext(context)
            shortcut.activated.connect(handler)
            self._runtime_shortcuts.append(shortcut)

    def _toggle_visibility(self) -> None:
        if self.isMinimized() or not self.isVisible():
            self.showNormal()
            self.raise_()
            self.activateWindow()
        else:
            self.showMinimized()

    def load_last_file(self) -> None:
        if not self.last_open_path:
            return
        path = pathlib.Path(self.last_open_path)
        if not path.is_file():
            return
        self.load_file(str(path))

    def _window_pos_from_event(self, event) -> QtCore.QPoint:
        return self.mapFromGlobal(global_pos(event))

    def apply_style(self) -> None:
        font = QtGui.QFont(self.font_family, self.font_size)
        self.text.setFont(font)
        
        c = QtGui.QColor(self.bg_color)
        r, g, b = c.red(), c.green(), c.blue()
        alpha_int = int(self.alpha * 255)
        if self.alpha == 0.0:
            rgba_color = "rgba(0, 0, 0, 0)"
        else:
            rgba_color = f"rgba({r}, {g}, {b}, {alpha_int})"

        font_c = QtGui.QColor(self.font_color)
        fr, fg, fb = font_c.red(), font_c.green(), font_c.blue()
        font_alpha_int = int(self.font_alpha * 255)
        if self.font_alpha == 0.0:
            font_rgba = "rgba(0, 0, 0, 0)"
        else:
            font_rgba = f"rgba({fr}, {fg}, {fb}, {font_alpha_int})"

        self.text.setStyleSheet(f"QTextEdit {{ background-color: {rgba_color}; color: {font_rgba}; border: 0px; }}")
        self.text.setViewportMargins(0, 0, 0, 0)
        self.text.document().setDocumentMargin(0)

    def apply_opacity(self) -> None:
        wa_translucent = widget_attribute("WA_TranslucentBackground")
        if self.alpha == 0.0:
            if not self.testAttribute(wa_translucent):
                self.hide()
                self.setAttribute(wa_translucent, True)
                self.show()
            self.setWindowOpacity(1.0)
            self.apply_style()
        else:
            if self.testAttribute(wa_translucent):
                self.hide()
                self.setAttribute(wa_translucent, False)
                self.show()
            self.apply_style()

    def apply_borderless(self) -> None:
        self.setWindowFlag(window_flag("FramelessWindowHint"), self.borderless)
        if self.isVisible():
            self.show()

    def apply_anti_capture(self) -> None:
        try:
            hwnd = int(self.winId())
            user32 = ctypes.windll.user32
            WDA_NONE = 0x0
            WDA_EXCLUDEFROMCAPTURE = 0x11
            flag = WDA_EXCLUDEFROMCAPTURE if self.anti_capture else WDA_NONE
            user32.SetWindowDisplayAffinity(hwnd, flag)
        except Exception:
            pass

    def set_content(self, text: str) -> None:
        self.content = text
        
        # 针对长文本进行分章处理（每5万字符一章，防止渲染卡顿）
        chunk_size = 50000
        if len(text) > chunk_size:
            self.chapters = []
            for i in range(0, len(text), chunk_size):
                chunk_text = text[i:i + chunk_size]
                self.chapters.append({"title": f"第 {i//chunk_size + 1} 部分", "text": chunk_text})
        else:
            self.chapters = [{"title": "正文", "text": text}]
        self.chapter_index = 0
        self.update_view()

    def update_view(self, restore_scroll: int | None = None) -> None:
        if not self.chapters:
            self.text.setPlainText("")
            return

        current_chapter_text = self.chapters[self.chapter_index]["text"]
        if self.text.toPlainText() != current_chapter_text:
            self.text.setPlainText(current_chapter_text)

        if restore_scroll is not None:
            self.text.verticalScrollBar().setValue(restore_scroll)
        self._save_progress()

    def open_file(self) -> None:
        file_path, _ = QtWidgets.QFileDialog.getOpenFileName(
            self,
            "选择文件",
            "",
            "电子书 (*.txt *.epub);;文本 (*.txt);;EPUB (*.epub);;所有文件 (*.*)",
        )
        if not file_path:
            return
        self.load_file(file_path)

    def open_font_dialog(self) -> None:
        font, ok = QtWidgets.QFontDialog.getFont(QtGui.QFont(self.font_family, self.font_size), self)
        if ok:
            self.font_family = font.family()
            self.font_size = font.pointSize()
            self.apply_style()
            self._save_settings()

    def pick_bg(self) -> None:
        color = QtWidgets.QColorDialog.getColor(QtGui.QColor(self.bg_color), self)
        if color.isValid():
            self.bg_color = color.name()
            self.apply_style()
            self._save_settings()

    def pick_font_color(self) -> None:
        color = QtWidgets.QColorDialog.getColor(QtGui.QColor(self.font_color), self)
        if color.isValid():
            self.font_color = color.name()
            self.apply_style()
            self._save_settings()

    def set_opacity(self, value: float) -> None:
        self.alpha = value
        self.apply_opacity()
        self._save_settings()

    def set_font_opacity(self, value: float) -> None:
        self.font_alpha = value
        self.apply_style()
        self._save_settings()

    def toggle_anti_capture(self, checked: bool) -> None:
        self.anti_capture = checked
        self.apply_anti_capture()

    def jump_to_chapter(self) -> None:
        if not self.chapters:
            return
        items = [c["title"] for c in self.chapters]
        current = min(self.chapter_index, len(items) - 1)
        item, ok = QtWidgets.QInputDialog.getItem(self, "章节跳转", "选择章节", items, current, False)
        if ok and item in items:
            self.chapter_index = items.index(item)
            self.update_view()

    def adaptive_detect_style(self) -> None:
        self.config_data = self._load_config_data()
        adaptive_targets = self.config_data.get("adaptive_targets", {})
        use_font_color = bool(adaptive_targets.get("font_color", True)) if isinstance(adaptive_targets, dict) else True
        use_font_size = bool(adaptive_targets.get("font_size", True)) if isinstance(adaptive_targets, dict) else True
        use_bg_color = bool(adaptive_targets.get("bg_color", True)) if isinstance(adaptive_targets, dict) else True
        if not (use_font_color or use_font_size or use_bg_color):
            QtWidgets.QMessageBox.information(self, "自适应识别", "请先在首页阅读设置里至少勾选一个识别项")
            return
        prev_anti_capture = self.anti_capture
        if prev_anti_capture:
            self.anti_capture = False
            self.apply_anti_capture()
        self.hide()
        QtWidgets.QApplication.processEvents()
        selector = RegionSelectionOverlay(self)
        selected_rect = selector.select_region()
        if selected_rect is None:
            if prev_anti_capture:
                self.anti_capture = True
                self.apply_anti_capture()
            self.show()
            return
        image = self._capture_region_image(selected_rect)
        if prev_anti_capture:
            self.anti_capture = True
            self.apply_anti_capture()
        self.show()
        if image is None or image.isNull():
            QtWidgets.QMessageBox.warning(self, "自适应识别", "识别失败：无法获取圈选区域图像")
            return
        bg_hex, font_hex = self._detect_style_colors(image)
        if bg_hex is None or font_hex is None:
            QtWidgets.QMessageBox.warning(self, "自适应识别", "识别失败：未能提取有效颜色")
            return
        font_size = self._estimate_font_size(image, bg_hex, font_hex) if use_font_size else None
        result_lines = ["识别完成："]
        if use_bg_color:
            result_lines.append(f"背景色：{bg_hex}")
        if use_font_color:
            result_lines.append(f"字体颜色：{font_hex}")
        if use_font_size and font_size is not None:
            result_lines.append(f"建议字号：{font_size}pt")
        result_lines.append("\n是否应用到当前界面？")
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
            self.apply_style()
            self._save_settings()
            QtWidgets.QMessageBox.information(self, "自适应识别", "已应用识别结果")

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

    def _rgb_distance_sq(self, a: tuple[int, int, int], b: tuple[int, int, int]) -> int:
        dr = a[0] - b[0]
        dg = a[1] - b[1]
        db = a[2] - b[2]
        return dr * dr + dg * dg + db * db

    def _luminance(self, r: int, g: int, b: int) -> float:
        return 0.2126 * r + 0.7152 * g + 0.0722 * b

    def back_to_home(self) -> None:
        if callable(self.on_back_home):
            self.close()
            self.on_back_home()

    def show_menu(self, pos: QtCore.QPoint) -> None:
        menu = QtWidgets.QMenu(self)
        menu.addAction("打开文件", self.open_file)
        menu.addAction("章节跳转", self.jump_to_chapter)
        menu.addSeparator()
        menu.addAction("上一页", self.prev_page)
        menu.addAction("下一页", self.next_page)
        menu.addSeparator()
        menu.addAction("自适应识别", self.adaptive_detect_style)
        back_action = menu.addAction("返回首页")
        back_action.triggered.connect(self.back_to_home)
        if not callable(self.on_back_home):
            back_action.setEnabled(False)
        anti_action = menu.addAction("防截屏")
        anti_action.setCheckable(True)
        anti_action.setChecked(self.anti_capture)
        anti_action.toggled.connect(self.toggle_anti_capture)
        menu.addSeparator()
        menu.addAction("退出", self.close)
        sender = self.sender()
        if isinstance(sender, QtWidgets.QWidget):
            global_pos = sender.mapToGlobal(pos)
        else:
            global_pos = self.mapToGlobal(pos)
        if PYQT6:
            menu.exec(global_pos)
        else:
            menu.exec_(global_pos)

    def next_page(self) -> None:
        bar = self.text.verticalScrollBar()
        # 检查是否到底
        if bar.value() >= bar.maximum():
            if self.chapter_index < len(self.chapters) - 1:
                self.chapter_index += 1
                self.update_view(restore_scroll=0)
        else:
            # 计算按行对齐的翻页距离
            line_height = self.get_line_height()
            viewport_height = self.text.viewport().height()
            
            # 计算当前页面能完整显示的行数
            lines_per_page = max(1, viewport_height // line_height)
            scroll_step = lines_per_page * line_height
            
            # 确保滚动起点是行对齐的，避免累积误差
            current_aligned = round(bar.value() / line_height) * line_height
            bar.setValue(current_aligned + scroll_step)
            self._save_progress()

    def prev_page(self) -> None:
        bar = self.text.verticalScrollBar()
        # 检查是否到顶
        if bar.value() <= bar.minimum():
            if self.chapter_index > 0:
                self.chapter_index -= 1
                self.update_view()
                
                # 计算到底部时的行对齐位置
                line_height = self.get_line_height()
                aligned_max = (bar.maximum() // line_height) * line_height
                bar.setValue(aligned_max)
                 
        else:
            # 计算按行对齐的翻页距离
            line_height = self.get_line_height()
            viewport_height = self.text.viewport().height()
            lines_per_page = max(1, viewport_height // line_height)
            scroll_step = lines_per_page * line_height
            
            # 确保滚动起点是行对齐的
            current_aligned = round(bar.value() / line_height) * line_height
            bar.setValue(current_aligned - scroll_step)
            self._save_progress()

    def _save_progress(self) -> None:
        if not self.current_path:
            return
        try:
            stat = os.stat(self.current_path)
            scroll_val = self.text.verticalScrollBar().value()
            self.progress_data[self.current_path] = {
                "chapter": self.chapter_index,
                "scroll": scroll_val, # 使用滚动条位置替代页码
                "mtime": stat.st_mtime,
                "size": stat.st_size,
            }
            self._save_progress_data()
        except Exception:
            pass

    def load_file(self, file_path: str) -> None:
        try:
            self.current_path = str(pathlib.Path(file_path).expanduser().resolve())
            if self.current_path.lower().endswith(".txt"):
                content = read_text_with_fallback(self.current_path)
                self.set_content(content)
            elif self.current_path.lower().endswith(".epub"):
                self.chapters = parse_epub_chapters(self.current_path)
                new_chapters = []
                for ch in self.chapters:
                    if len(ch["text"]) > 50000:
                        for i in range(0, len(ch["text"]), 50000):
                            new_chapters.append({"title": ch["title"] + f" ({i//50000 + 1})", "text": ch["text"][i:i+50000]})
                    else:
                        new_chapters.append(ch)
                self.chapters = new_chapters
                self.chapter_index = 0
            else:
                raise ValueError("暂不支持该格式")
                
            saved = self.progress_data.get(self.current_path)
            restore_scroll = 0
            if saved:
                try:
                    stat = os.stat(self.current_path)
                    if saved.get("mtime") == stat.st_mtime and saved.get("size") == stat.st_size:
                        self.chapter_index = int(saved.get("chapter", 0))
                        restore_scroll = int(saved.get("scroll", 0))
                except Exception:
                    pass
            self.update_view(restore_scroll=restore_scroll)
            self._remember_last_path(self.current_path)
        except Exception as e:
            QtWidgets.QMessageBox.critical(self, "加载失败", str(e))

    def _hit_test_resize(self, pos: QtCore.QPoint) -> str | None:
        if not self.borderless:
            return None
        margin = 8
        x = pos.x()
        y = pos.y()
        w = self.width()
        h = self.height()
        left = x <= margin
        right = x >= w - margin
        top = y <= margin
        bottom = y >= h - margin
        if top and left:
            return "nw"
        if top and right:
            return "ne"
        if bottom and left:
            return "sw"
        if bottom and right:
            return "se"
        if left:
            return "w"
        if right:
            return "e"
        if top:
            return "n"
        if bottom:
            return "s"
        return None

    def _update_cursor(self, direction: str | None) -> None:
        cursor_map = {
            "nw": cursor_shape("SizeFDiagCursor"),
            "se": cursor_shape("SizeFDiagCursor"),
            "ne": cursor_shape("SizeBDiagCursor"),
            "sw": cursor_shape("SizeBDiagCursor"),
            "n": cursor_shape("SizeVerCursor"),
            "s": cursor_shape("SizeVerCursor"),
            "e": cursor_shape("SizeHorCursor"),
            "w": cursor_shape("SizeHorCursor"),
        }
        if direction:
            cursor = cursor_map[direction]
            self.setCursor(cursor)
            self.text.setCursor(cursor)
            self.text.viewport().setCursor(cursor)
        else:
            self.unsetCursor()
            self.text.unsetCursor()
            self.text.viewport().unsetCursor()

    def _start_drag_or_resize(self, event, pos_window: QtCore.QPoint | None = None, global_point: QtCore.QPoint | None = None) -> None:
        if event.button() != mouse_button("LeftButton"):
            return
        if pos_window is None:
            pos_window = local_pos(event)
        if global_point is None:
            global_point = global_pos(event)
        self._press_global = global_point
        self._press_pos_window = pos_window
        self._moved = False
        self._release_handled = False
        self._resize_dir = self._hit_test_resize(pos_window)
        if self._resize_dir:
            self._start_geom = self.geometry()
            self._start_pos = global_point
            self._drag_offset = None
        else:
            self._drag_offset = global_point - self.frameGeometry().topLeft()
            self._start_geom = None
            self._start_pos = None

    def _update_drag_or_resize(self, event, pos_window: QtCore.QPoint | None = None) -> None:
        if not (event.buttons() & mouse_button("LeftButton")):
            if pos_window is None:
                pos_window = local_pos(event)
            self._update_cursor(self._hit_test_resize(pos_window))
            return
        current_global = global_pos(event)
        if self._press_global:
            dx = abs(current_global.x() - self._press_global.x())
            dy = abs(current_global.y() - self._press_global.y())
            if dx > 5 or dy > 5:
                self._moved = True
        if self._resize_dir and self._start_geom and self._start_pos:
            dx = current_global.x() - self._start_pos.x()
            dy = current_global.y() - self._start_pos.y()
            geom = QtCore.QRect(self._start_geom)
            min_w, min_h = 360, 240
            if self._resize_dir in ("e", "ne", "se"):
                geom.setWidth(max(min_w, geom.width() + dx))
            if self._resize_dir in ("s", "se", "sw"):
                geom.setHeight(max(min_h, geom.height() + dy))
            if self._resize_dir in ("w", "nw", "sw"):
                new_w = max(min_w, geom.width() - dx)
                geom.setX(geom.x() + (geom.width() - new_w))
                geom.setWidth(new_w)
            if self._resize_dir in ("n", "nw", "ne"):
                new_h = max(min_h, geom.height() - dy)
                geom.setY(geom.y() + (geom.height() - new_h))
                geom.setHeight(new_h)
            self.setGeometry(geom)
        elif self._drag_offset is not None:
            self.move(current_global - self._drag_offset)

    def _end_drag_or_resize(self) -> None:
        self._drag_offset = None
        self._resize_dir = None
        self._start_geom = None
        self._start_pos = None
        self._press_global = None
        self._press_pos_window = None
        self._update_cursor(None)

    def _handle_click(self, local: QtCore.QPoint, pos_window: QtCore.QPoint) -> bool:
        if self._hit_test_resize(pos_window):
            return False
        width = max(1, self.text.viewport().width())
        height = max(1, self.text.viewport().height())
        margin = 8
        if local.y() < margin or local.y() > height - margin:
            return False
        if local.x() >= width // 2:
            self.next_page()
        else:
            self.prev_page()
        return True

    def _handle_release(self, event, pos_window: QtCore.QPoint, local_text: QtCore.QPoint) -> bool:
        if event.button() != mouse_button("LeftButton"):
            self._end_drag_or_resize()
            return False
        if self._release_handled:
            self._end_drag_or_resize()
            return False
        self._release_handled = True
        handled = False
        if not self._moved and not self._resize_dir:
            handled = self._handle_click(local_text, pos_window)
        self._end_drag_or_resize()
        return handled

    def _handle_wheel(self, delta: int) -> bool:
        bar = self.text.verticalScrollBar()
        line_height = self.get_line_height()
        step = line_height * 3
        
        # 确保起点对齐
        current_aligned = round(bar.value() / line_height) * line_height
        
        if delta > 0:
            bar.setValue(current_aligned - step)
        elif delta < 0:
            bar.setValue(current_aligned + step)
            
        self._save_progress()
        return True

    def nativeEvent(self, eventType, message):
        if self.alpha == 0.0:
            if eventType in (b"windows_generic_MSG", b"windows_dispatcher_MSG", "windows_generic_MSG", "windows_dispatcher_MSG"):
                if PYQT6:
                    msg = ctypes.wintypes.MSG.from_address(int(message))
                else:
                    msg = ctypes.wintypes.MSG.from_address(message.__int__())
                if msg.message == 0x0084:
                    return True, 1
        return super().nativeEvent(eventType, message)

    def eventFilter(self, obj, event):
        if obj is self.text or obj is self.text.viewport():
            if event.type() in (event_type("MouseButtonPress"), event_type("MouseButtonDblClick")):
                pos_w = self._window_pos_from_event(event)
                gp = global_pos(event)
                self._start_drag_or_resize(event, pos_w, gp)
            elif event.type() == event_type("MouseMove"):
                pos_w = self._window_pos_from_event(event)
                self._update_drag_or_resize(event, pos_w)
            elif event.type() == event_type("MouseButtonRelease"):
                pos_w = self._window_pos_from_event(event)
                if obj is self.text.viewport():
                    local = local_pos(event)
                else:
                    local = self.text.viewport().mapFrom(self.text, local_pos(event))
                if self._handle_release(event, pos_w, local):
                    return True
            elif event.type() == event_type("Wheel"):
                try:
                    delta = event.angleDelta().y()
                except Exception:
                    delta = 0
                if self._handle_wheel(delta):
                    return True
        return super().eventFilter(obj, event)

    def mousePressEvent(self, event) -> None:
        self._start_drag_or_resize(event)
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event) -> None:
        self._update_drag_or_resize(event)
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event) -> None:
        pos_w = self._window_pos_from_event(event)
        local = self.text.viewport().mapFrom(self, pos_w)
        self._handle_release(event, pos_w, local)
        super().mouseReleaseEvent(event)

    def wheelEvent(self, event) -> None:
        try:
            delta = event.angleDelta().y()
        except Exception:
            delta = 0
        if self._handle_wheel(delta):
            return
        super().wheelEvent(event)

    def get_line_height(self) -> int:
        font = self.text.currentFont()
        metrics = QtGui.QFontMetrics(font)
        return max(1, metrics.lineSpacing())

    def snap_to_line(self) -> None:
        bar = self.text.verticalScrollBar()
        line_height = self.get_line_height()
        current_val = bar.value()
        # 四舍五入到最近的行
        aligned_val = round(current_val / line_height) * line_height
        if abs(aligned_val - current_val) > 0:
            bar.setValue(aligned_val)
            self._save_progress()

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        self.snap_to_line()

    def keyPressEvent(self, event) -> None:
        super().keyPressEvent(event)


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
