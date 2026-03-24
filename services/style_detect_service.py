from collections import defaultdict

from qt_compat import QtGui


def capture_region_image(rect) -> QtGui.QImage | None:
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


def detect_style_colors(image: QtGui.QImage) -> tuple[str | None, str | None]:
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
    bg_rgb = _avg_rgb_from_bin(bg_bin, sums)
    bg_luma = _luminance(*bg_rgb)
    font_rgb = None
    best_score = -1.0
    for key_bin, count in sorted_bins[1:20]:
        rgb = _avg_rgb_from_bin(key_bin, sums)
        contrast = abs(_luminance(*rgb) - bg_luma)
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
        font_hex = "#000000" if _luminance(*bg_rgb) >= 128 else "#ffffff"
    return bg_hex, font_hex


def estimate_font_size(image: QtGui.QImage, bg_hex: str, font_hex: str) -> int | None:
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
            to_fg = _rgb_distance_sq(rgb, fg_rgb)
            to_bg = _rgb_distance_sq(rgb, bg_rgb)
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
    stroke_px = _percentile_sorted(runs, 0.75)
    row_text_counts: list[int] = []
    sample_step_x = max(1, w // 220)
    for y in range(h):
        text_count = 0
        for x in range(0, w, sample_step_x):
            c = QtGui.QColor(image.pixel(x, y))
            rgb = (c.red(), c.green(), c.blue())
            to_fg = _rgb_distance_sq(rgb, fg_rgb)
            to_bg = _rgb_distance_sq(rgb, bg_rgb)
            if to_fg < to_bg and to_fg < 16000:
                text_count += 1
        row_text_counts.append(text_count)
    active_rows = [i for i, count in enumerate(row_text_counts) if count >= 2]
    band_runs: list[int] = []
    if active_rows:
        start = active_rows[0]
        prev = active_rows[0]
        for idx in active_rows[1:]:
            if idx == prev + 1:
                prev = idx
                continue
            band_runs.append(prev - start + 1)
            start = idx
            prev = idx
        band_runs.append(prev - start + 1)
    band_runs = [run for run in band_runs if run >= 2]
    band_px = _percentile_sorted(sorted(band_runs), 0.6) if band_runs else stroke_px
    px_height = stroke_px * 0.45 + band_px * 0.55
    dpr = float(image.devicePixelRatio()) if hasattr(image, "devicePixelRatio") else 1.0
    if dpr <= 0:
        dpr = 1.0
    logical_px_height = px_height / dpr
    estimate_pt = int(round(logical_px_height * 72.0 / 96.0))
    return max(10, min(42, estimate_pt))


def estimate_font_spacing(image: QtGui.QImage, bg_hex: str, font_hex: str) -> float | None:
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
            to_fg = _rgb_distance_sq(rgb, fg_rgb)
            to_bg = _rgb_distance_sq(rgb, bg_rgb)
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


def estimate_line_spacing(image: QtGui.QImage, bg_hex: str, font_hex: str) -> float | None:
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
            to_fg = _rgb_distance_sq(rgb, fg_rgb)
            to_bg = _rgb_distance_sq(rgb, bg_rgb)
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


def _avg_rgb_from_bin(key_bin: tuple[int, int, int], sums: dict[tuple[int, int, int], list[int]]) -> tuple[int, int, int]:
    data = sums[key_bin]
    count = max(1, data[3])
    return (data[0] // count, data[1] // count, data[2] // count)


def _rgb_distance_sq(a: tuple[int, int, int], b: tuple[int, int, int]) -> int:
    dr = a[0] - b[0]
    dg = a[1] - b[1]
    db = a[2] - b[2]
    return dr * dr + dg * dg + db * db


def _luminance(r: int, g: int, b: int) -> float:
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def _percentile_sorted(values: list[int], ratio: float) -> float:
    if not values:
        return 0.0
    ratio = min(1.0, max(0.0, ratio))
    index = int(round((len(values) - 1) * ratio))
    return float(values[index])
