import pathlib
import sys

current_dir = pathlib.Path(__file__).resolve().parent
project_root = current_dir.parent
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

from main import main


if __name__ == "__main__":
    raise SystemExit(main())
