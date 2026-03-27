import copy
import json
import pathlib
import sys


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
    "reading_mode": "page",
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
    return pathlib.Path(__file__).resolve().parent.parent


def get_config_path() -> pathlib.Path:
    return get_base_path() / "reader_config.json"


def get_icon_path() -> pathlib.Path:
    base = get_base_path() / "ico"
    ico_path = base / "yu.ico"
    if ico_path.exists():
        return ico_path
    return base / "yu.svg"


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
    reading_mode = config.get("reading_mode")
    if reading_mode not in ("page", "scroll"):
        config["reading_mode"] = "page"
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
