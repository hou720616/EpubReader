import ctypes
import ctypes.wintypes
import json
import os
import pathlib
import bisect

from epub_utils import parse_epub_chapters, read_text_with_fallback
from qt_compat import (
    PYQT6,
    QtCore,
    QtGui,
    QtWidgets,
    context_menu_policy,
    cursor_shape,
    event_type,
    key,
    global_pos,
    local_pos,
    mouse_button,
    no_frame,
    window_flag,
    widget_attribute,
)
from services.config_service import get_base_path, load_config_data, save_config_data, update_recent_paths
from services.style_detect_service import (
    capture_region_image,
    detect_style_colors,
    estimate_font_size,
    estimate_font_spacing,
    estimate_line_spacing,
)
from ui.overlay import RegionSelectionOverlay
from ui.settings_dialog import SettingsDialog


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
        self.chapter_start_positions: list[int] = []
        self.stream_start_chapter = 0
        self.stream_loaded_end = -1
        self.scroll_initial_chapters = 1
        self.scroll_append_batch = 2
        self.scroll_append_threshold = 240
        self.current_path: str | None = None

        self.font_family = "微软雅黑"
        self.font_size = 18
        self.font_color = "#000000"
        self.font_alpha = 1.0
        self.font_spacing = 0.0
        self.line_spacing = 1.0
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
        self._restoring_scroll_stream = False
        self._scroll_progress_tracking_active = False
        self._pending_scroll_restore: int | None = None

        self.progress_path = get_base_path() / ".epubrand_progress.json"
        self.progress_data = self._load_progress_data()
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
        self.font_spacing = float(self.config_data.get("font_spacing", self.font_spacing))
        self.line_spacing = float(self.config_data.get("line_spacing", self.line_spacing))
        self.font_spacing = min(20.0, max(0.0, self.font_spacing))
        self.line_spacing = min(2.2, max(1.0, self.line_spacing))
        self.bg_color = self.config_data.get("bg_color", self.bg_color)
        self.alpha = float(self.config_data.get("bg_alpha", self.alpha))
        self.reading_mode = str(self.config_data.get("reading_mode", "page"))
        if self.reading_mode not in ("page", "scroll"):
            self.reading_mode = "page"

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
        self.text.verticalScrollBar().valueChanged.connect(self._on_scrollbar_value_changed)
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
        self._restore_window_geometry()
        self.apply_style()
        self._apply_reading_mode_ui()
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
        return load_config_data()

    def _save_config_data(self) -> None:
        save_config_data(self.config_data)

    def _save_settings(self) -> None:
        self.config_data["font_family"] = self.font_family
        self.config_data["font_size"] = self.font_size
        self.config_data["font_color"] = self.font_color
        self.config_data["font_alpha"] = self.font_alpha
        self.config_data["font_spacing"] = self.font_spacing
        self.config_data["line_spacing"] = self.line_spacing
        self.config_data["bg_color"] = self.bg_color
        self.config_data["bg_alpha"] = self.alpha
        self._save_config_data()

    def _remember_last_path(self, path: str) -> None:
        update_recent_paths(self.config_data, path)
        self.last_open_path = path
        self._save_config_data()

    def _save_window_geometry(self) -> None:
        rect = self.normalGeometry() if (self.isMinimized() or self.isMaximized()) else self.geometry()
        if rect.width() < 360 or rect.height() < 240:
            return
        self.config_data["window_geometry"] = {
            "x": int(rect.x()),
            "y": int(rect.y()),
            "w": int(rect.width()),
            "h": int(rect.height()),
        }
        self._save_config_data()

    def _restore_window_geometry(self) -> None:
        geometry_data = self.config_data.get("window_geometry")
        if not isinstance(geometry_data, dict):
            return
        try:
            x = int(geometry_data.get("x"))
            y = int(geometry_data.get("y"))
            w = int(geometry_data.get("w"))
            h = int(geometry_data.get("h"))
        except Exception:
            return
        if w < 360 or h < 240:
            return
        rect = QtCore.QRect(x, y, w, h)
        screen = QtGui.QGuiApplication.screenAt(rect.center()) or QtGui.QGuiApplication.primaryScreen()
        if screen is None:
            self.setGeometry(rect)
            return
        available = screen.availableGeometry()
        w = min(w, available.width())
        h = min(h, available.height())
        x = min(max(x, available.left()), available.right() - w + 1)
        y = min(max(y, available.top()), available.bottom() - h + 1)
        self.setGeometry(x, y, w, h)

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

    def _is_scroll_mode(self) -> bool:
        return self.reading_mode == "scroll"

    def _apply_reading_mode_ui(self) -> None:
        if self._is_scroll_mode():
            if PYQT6:
                self.text.setVerticalScrollBarPolicy(QtCore.Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
                self.text.setHorizontalScrollBarPolicy(QtCore.Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
            else:
                self.text.setVerticalScrollBarPolicy(QtCore.Qt.ScrollBarAlwaysOff)
                self.text.setHorizontalScrollBarPolicy(QtCore.Qt.ScrollBarAlwaysOff)
        else:
            if PYQT6:
                self.text.setVerticalScrollBarPolicy(QtCore.Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
                self.text.setHorizontalScrollBarPolicy(QtCore.Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
            else:
                self.text.setVerticalScrollBarPolicy(QtCore.Qt.ScrollBarAlwaysOff)
                self.text.setHorizontalScrollBarPolicy(QtCore.Qt.ScrollBarAlwaysOff)

    def _on_scrollbar_value_changed(self, _value: int) -> None:
        if not self.current_path:
            return
        if self._restoring_scroll_stream:
            return
        if self._is_scroll_mode():
            if not self._scroll_progress_tracking_active:
                return
            self._maybe_append_scroll_chapters()
            self._sync_chapter_index_from_scroll()
        self._save_progress()

    def _sync_chapter_index_from_scroll(self) -> None:
        if not self._is_scroll_mode() or not self.chapter_start_positions:
            return
        loaded_count = min(len(self.chapter_start_positions), self.stream_loaded_end + 1)
        if loaded_count <= 0:
            return
        bar = self.text.verticalScrollBar()
        if bar.value() <= bar.minimum():
            self.chapter_index = min(max(0, self.stream_start_chapter), len(self.chapters) - 1)
            return
        viewport = self.text.viewport()
        sample_x = max(1, min(viewport.width() - 1, viewport.width() // 3))
        sample_y = max(1, min(viewport.height() - 1, 24))
        sample_point = QtCore.QPoint(sample_x, sample_y)
        cursor = self.text.cursorForPosition(sample_point)
        pos = max(0, cursor.position())
        idx = bisect.bisect_right(self.chapter_start_positions[:loaded_count], pos) - 1
        if idx < 0:
            idx = 0
        self.chapter_index = min(idx, len(self.chapters) - 1)

    def _reading_anchor_point(self) -> QtCore.QPoint:
        viewport = self.text.viewport()
        sample_x = max(1, min(viewport.width() - 1, viewport.width() // 3))
        sample_y = max(1, min(viewport.height() - 1, 24))
        return QtCore.QPoint(sample_x, sample_y)

    def _normalize_chapter_progress(self, chapter_idx: int, char_pos: int) -> float:
        if chapter_idx < 0 or chapter_idx >= len(self.chapters):
            return 0.0
        chapter_len = len(self.chapters[chapter_idx]["text"])
        if chapter_len <= 1:
            return 0.0
        normalized = max(0, min(char_pos, chapter_len - 1)) / (chapter_len - 1)
        return max(0.0, min(1.0, normalized))

    def _chapter_char_pos_from_progress(self, chapter_idx: int, chapter_progress: float | None) -> int:
        if chapter_idx < 0 or chapter_idx >= len(self.chapters):
            return 0
        progress = 0.0 if chapter_progress is None else max(0.0, min(1.0, float(chapter_progress)))
        chapter_len = len(self.chapters[chapter_idx]["text"])
        if chapter_len <= 1:
            return 0
        return int(round((chapter_len - 1) * progress))

    def _current_progress_marker(self) -> tuple[int, float]:
        chapter_idx = min(max(0, self.chapter_index), max(0, len(self.chapters) - 1))
        if not self.chapters:
            return 0, 0.0
        if self._is_scroll_mode():
            self._sync_chapter_index_from_scroll()
            chapter_idx = min(max(0, self.chapter_index), len(self.chapters) - 1)
            if self.text.verticalScrollBar().value() <= self.text.verticalScrollBar().minimum():
                return chapter_idx, 0.0
            cursor = self.text.cursorForPosition(self._reading_anchor_point())
            doc_pos = max(0, cursor.position())
            chapter_start = self.chapter_start_positions[chapter_idx] if chapter_idx < len(self.chapter_start_positions) else 0
            local_pos = max(0, doc_pos - chapter_start)
            return chapter_idx, self._normalize_chapter_progress(chapter_idx, local_pos)
        cursor = self.text.cursorForPosition(self._reading_anchor_point())
        local_pos = max(0, cursor.position())
        return chapter_idx, self._normalize_chapter_progress(chapter_idx, local_pos)

    def _apply_page_progress_restore(self, chapter_idx: int, chapter_progress: float | None) -> None:
        local_pos = self._chapter_char_pos_from_progress(chapter_idx, chapter_progress)
        cursor = QtGui.QTextCursor(self.text.document())
        cursor.setPosition(max(0, local_pos))
        self.text.setTextCursor(cursor)
        self.text.ensureCursorVisible()

    def _append_chapter_to_stream(self, chapter_idx: int) -> None:
        if chapter_idx < 0 or chapter_idx >= len(self.chapters):
            return
        document = self.text.document()
        cursor = QtGui.QTextCursor(document)
        cursor.movePosition(QtGui.QTextCursor.MoveOperation.End if PYQT6 else QtGui.QTextCursor.End)
        current_count = max(0, document.characterCount() - 1)
        chapter_text = self.chapters[chapter_idx]["text"]
        if current_count > 0:
            cursor.insertText("\n\n")
            current_count += 2
        if chapter_idx >= len(self.chapter_start_positions):
            self.chapter_start_positions.extend([0] * (chapter_idx - len(self.chapter_start_positions) + 1))
        self.chapter_start_positions[chapter_idx] = current_count
        cursor.insertText(chapter_text)
        self.stream_loaded_end = max(self.stream_loaded_end, chapter_idx)

    def _build_scroll_stream(self, start_chapter: int, restore_progress: float | None) -> None:
        self._restoring_scroll_stream = True
        try:
            self.text.clear()
            self.chapter_start_positions = [0] * len(self.chapters)
            if not self.chapters:
                self.stream_start_chapter = 0
                self.stream_loaded_end = -1
                return
            start = min(max(0, start_chapter), len(self.chapters) - 1)
            self.stream_start_chapter = start
            self.chapter_index = start
            self.stream_loaded_end = start - 1
            initial_end = min(len(self.chapters) - 1, start + self.scroll_initial_chapters - 1)
            for idx in range(start, initial_end + 1):
                self._append_chapter_to_stream(idx)
            self._apply_text_spacing_format()
            local_pos = self._chapter_char_pos_from_progress(start, restore_progress)
            self._pending_scroll_restore = self.chapter_start_positions[start] + local_pos
            QtCore.QTimer.singleShot(0, self._apply_pending_scroll_restore)
        finally:
            self._restoring_scroll_stream = False

    def _apply_pending_scroll_restore(self) -> None:
        pending = self._pending_scroll_restore
        if pending is None:
            return
        self._pending_scroll_restore = None
        cursor = QtGui.QTextCursor(self.text.document())
        cursor.setPosition(max(0, pending))
        self.text.setTextCursor(cursor)
        self.text.ensureCursorVisible()

    def _maybe_append_scroll_chapters(self) -> None:
        if not self._is_scroll_mode() or not self.chapters:
            return
        if self.stream_loaded_end >= len(self.chapters) - 1:
            return
        bar = self.text.verticalScrollBar()
        if bar.value() + self.scroll_append_threshold < bar.maximum():
            return
        target = min(len(self.chapters) - 1, self.stream_loaded_end + self.scroll_append_batch)
        for idx in range(self.stream_loaded_end + 1, target + 1):
            self._append_chapter_to_stream(idx)
        self._apply_text_spacing_format()

    def apply_style(self) -> None:
        font = QtGui.QFont(self.font_family, self.font_size)
        spacing_type = QtGui.QFont.SpacingType.AbsoluteSpacing if PYQT6 else QtGui.QFont.AbsoluteSpacing
        font.setLetterSpacing(spacing_type, self.font_spacing)
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
        self._apply_text_spacing_format()

    def _apply_text_spacing_format(self) -> None:
        cursor = QtGui.QTextCursor(self.text.document())
        selection_type = QtGui.QTextCursor.SelectionType.Document if PYQT6 else QtGui.QTextCursor.Document
        cursor.select(selection_type)
        block_format = QtGui.QTextBlockFormat()
        line_height_type = QtGui.QTextBlockFormat.LineHeightTypes.ProportionalHeight if PYQT6 else QtGui.QTextBlockFormat.ProportionalHeight
        block_format.setLineHeight(int(round(self.line_spacing * 100)), line_height_type)
        cursor.mergeBlockFormat(block_format)

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

    def update_view(self, restore_progress: float | None = None) -> None:
        if not self.chapters:
            self.text.setPlainText("")
            self.stream_loaded_end = -1
            self.chapter_start_positions = []
            return
        self.chapter_index = min(max(0, self.chapter_index), len(self.chapters) - 1)
        if self._is_scroll_mode():
            self._scroll_progress_tracking_active = False
            self._build_scroll_stream(self.chapter_index, restore_progress)
        else:
            self.stream_loaded_end = self.chapter_index
            current_chapter_text = self.chapters[self.chapter_index]["text"]
            if self.text.toPlainText() != current_chapter_text:
                self.text.setPlainText(current_chapter_text)
                self._apply_text_spacing_format()
            self._apply_page_progress_restore(self.chapter_index, restore_progress)
        if not self._is_scroll_mode():
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
            target_index = items.index(item)
            if self._is_scroll_mode():
                self._scroll_progress_tracking_active = True
                while self.stream_loaded_end < target_index:
                    next_idx = self.stream_loaded_end + 1
                    if next_idx >= len(self.chapters):
                        break
                    self._append_chapter_to_stream(next_idx)
                self._apply_text_spacing_format()
                self.chapter_index = target_index
                chapter_pos = self.chapter_start_positions[target_index] if target_index < len(self.chapter_start_positions) else 0
                cursor = QtGui.QTextCursor(self.text.document())
                cursor.setPosition(max(0, chapter_pos))
                self.text.setTextCursor(cursor)
                self.text.ensureCursorVisible()
                self._save_progress()
            else:
                self.chapter_index = target_index
                self.update_view(restore_progress=0.0)

    def adaptive_detect_style(self) -> None:
        self.config_data = self._load_config_data()
        adaptive_targets = self.config_data.get("adaptive_targets", {})
        use_font_color = bool(adaptive_targets.get("font_color", True)) if isinstance(adaptive_targets, dict) else True
        use_font_size = bool(adaptive_targets.get("font_size", True)) if isinstance(adaptive_targets, dict) else True
        use_bg_color = bool(adaptive_targets.get("bg_color", True)) if isinstance(adaptive_targets, dict) else True
        use_font_spacing = bool(adaptive_targets.get("font_spacing", False)) if isinstance(adaptive_targets, dict) else False
        use_line_spacing = bool(adaptive_targets.get("line_spacing", False)) if isinstance(adaptive_targets, dict) else False
        if not (use_font_color or use_font_size or use_bg_color or use_font_spacing or use_line_spacing):
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
        image = capture_region_image(selected_rect)
        if prev_anti_capture:
            self.anti_capture = True
            self.apply_anti_capture()
        self.show()
        if image is None or image.isNull():
            QtWidgets.QMessageBox.warning(self, "自适应识别", "识别失败：无法获取圈选区域图像")
            return
        bg_hex, font_hex = detect_style_colors(image)
        if bg_hex is None or font_hex is None:
            QtWidgets.QMessageBox.warning(self, "自适应识别", "识别失败：未能提取有效颜色")
            return
        font_size = estimate_font_size(image, bg_hex, font_hex) if use_font_size else None
        font_spacing = estimate_font_spacing(image, bg_hex, font_hex) if use_font_spacing else None
        line_spacing = estimate_line_spacing(image, bg_hex, font_hex) if use_line_spacing else None
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
            if use_font_spacing and font_spacing is not None:
                self.font_spacing = font_spacing
            if use_line_spacing and line_spacing is not None:
                self.line_spacing = line_spacing
            self.apply_style()
            self._save_settings()
            QtWidgets.QMessageBox.information(self, "自适应识别", "已应用识别结果")

    def back_to_home(self) -> None:
        if callable(self.on_back_home):
            if self._is_scroll_mode():
                self._sync_chapter_index_from_scroll()
                self._save_progress(force=True)
            self._save_window_geometry()
            self.close()
            self.on_back_home()

    def open_settings_dialog(self) -> None:
        dialog = SettingsDialog(self)
        if PYQT6:
            dialog.exec()
        else:
            dialog.exec_()
        old_mode = self.reading_mode
        if self.chapters and self.current_path:
            self.chapter_index, chapter_progress = self._current_progress_marker()
            self._save_progress(force=True)
        else:
            chapter_progress = 0.0
        self.config_data = self._load_config_data()
        self.font_family = self.config_data.get("font_family", self.font_family)
        self.font_size = int(self.config_data.get("font_size", self.font_size))
        self.font_color = self.config_data.get("font_color", self.font_color)
        self.font_alpha = float(self.config_data.get("font_alpha", self.font_alpha))
        self.font_spacing = float(self.config_data.get("font_spacing", self.font_spacing))
        self.line_spacing = float(self.config_data.get("line_spacing", self.line_spacing))
        self.font_spacing = min(20.0, max(0.0, self.font_spacing))
        self.line_spacing = min(2.2, max(1.0, self.line_spacing))
        self.bg_color = self.config_data.get("bg_color", self.bg_color)
        self.alpha = float(self.config_data.get("bg_alpha", self.alpha))
        self.reading_mode = str(self.config_data.get("reading_mode", "page"))
        if self.reading_mode not in ("page", "scroll"):
            self.reading_mode = "page"
        self._apply_reading_mode_ui()
        if old_mode != self.reading_mode and self.chapters:
            self.chapter_index = min(max(0, self.chapter_index), max(0, len(self.chapters) - 1))
            self.update_view(restore_progress=chapter_progress)
        self.apply_opacity()

    def show_menu(self, pos: QtCore.QPoint) -> None:
        menu = QtWidgets.QMenu(self)
        menu.addAction("打开文件", self.open_file)
        menu.addAction("章节跳转", self.jump_to_chapter)
        menu.addSeparator()
        menu.addAction("阅读设置", self.open_settings_dialog)
        menu.addSeparator()
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
        if self._is_scroll_mode():
            self._scroll_progress_tracking_active = True
            step = max(1, int(self.text.viewport().height() * 0.85))
            bar.setValue(bar.value() + step)
            self._maybe_append_scroll_chapters()
            self._sync_chapter_index_from_scroll()
            self._save_progress()
            return
        # 检查是否到底
        if bar.value() >= bar.maximum():
            if self.chapter_index < len(self.chapters) - 1:
                self.chapter_index += 1
                self.update_view(restore_progress=0.0)
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
        if self._is_scroll_mode():
            self._scroll_progress_tracking_active = True
            step = max(1, int(self.text.viewport().height() * 0.85))
            bar.setValue(bar.value() - step)
            self._sync_chapter_index_from_scroll()
            self._save_progress()
            return
        # 检查是否到顶
        if bar.value() <= bar.minimum():
            if self.chapter_index > 0:
                self.chapter_index -= 1
                self.update_view(restore_progress=1.0)
                
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

    def _save_progress(self, force: bool = False) -> None:
        if not self.current_path:
            return
        if self._is_scroll_mode() and not self._scroll_progress_tracking_active and not force:
            return
        try:
            stat = os.stat(self.current_path)
            chapter_idx, chapter_progress = self._current_progress_marker()
            self.chapter_index = chapter_idx
            self.progress_data[self.current_path] = {
                "chapter": chapter_idx,
                "chapter_progress": chapter_progress,
                "mtime": stat.st_mtime,
                "size": stat.st_size,
            }
            self._save_progress_data()
        except Exception:
            pass

    def _get_saved_progress(self, file_path: str) -> tuple[int, float]:
        saved = self.progress_data.get(file_path)
        if not isinstance(saved, dict):
            return 0, 0.0
        try:
            stat = os.stat(file_path)
        except Exception:
            return 0, 0.0
        if saved.get("mtime") != stat.st_mtime or saved.get("size") != stat.st_size:
            return 0, 0.0
        try:
            chapter = int(saved.get("chapter", 0))
            chapter_progress = float(saved.get("chapter_progress", 0.0))
        except Exception:
            return 0, 0.0
        return chapter, max(0.0, min(1.0, chapter_progress))

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
                
            saved_chapter, restore_progress = self._get_saved_progress(self.current_path)
            self.chapter_index = min(max(0, saved_chapter), max(0, len(self.chapters) - 1))
            self.update_view(restore_progress=restore_progress)
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
        if self._is_scroll_mode():
            return False
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
        if self._is_scroll_mode():
            return False
        if delta == 0:
            return True
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
                if not self._is_scroll_mode():
                    event.accept()
                    return True
                self._scroll_progress_tracking_active = True
                self._maybe_append_scroll_chapters()
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
        if not self._is_scroll_mode():
            event.accept()
            return
        self._scroll_progress_tracking_active = True
        self._maybe_append_scroll_chapters()
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
        return max(1, int(round(metrics.lineSpacing() * self.line_spacing)))

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
        if not self._is_scroll_mode():
            self.snap_to_line()

    def closeEvent(self, event) -> None:
        if self._is_scroll_mode():
            self._sync_chapter_index_from_scroll()
            self._save_progress(force=True)
        self._save_window_geometry()
        super().closeEvent(event)

    def keyPressEvent(self, event) -> None:
        if self._is_scroll_mode():
            event_key = event.key()
            if event_key == key("Key_Down"):
                self._scroll_progress_tracking_active = True
                self.text.verticalScrollBar().setValue(self.text.verticalScrollBar().value() + self.get_line_height() * 3)
                self._maybe_append_scroll_chapters()
                self._sync_chapter_index_from_scroll()
                self._save_progress()
                return
            if event_key == key("Key_Up"):
                self._scroll_progress_tracking_active = True
                self.text.verticalScrollBar().setValue(self.text.verticalScrollBar().value() - self.get_line_height() * 3)
                self._sync_chapter_index_from_scroll()
                self._save_progress()
                return
        super().keyPressEvent(event)
