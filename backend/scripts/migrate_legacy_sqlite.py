from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from backend.app.core.database import init_db, SessionLocal
from backend.app.services.migration.legacy import migrate_legacy


def main() -> int:
    parser = argparse.ArgumentParser(description="迁移旧版 ChatBI SQLite 数据")
    parser.add_argument("--sqlite", type=Path, required=True)
    parser.add_argument("--owner", required=True, help="首位平台管理员用户名")
    args = parser.parse_args()
    init_db()
    result = migrate_legacy(
        args.sqlite,
        SessionLocal,
        owner_username=args.owner,
    )
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
