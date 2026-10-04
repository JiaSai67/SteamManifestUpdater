# -*- coding: utf-8 -*-
"""
Steam Manifest Updater 2.0 - Root Entry Point
轉發入口：自動將工作路徑錨定至 src 並啟動 2.0 櫻花流光現代化介面。
"""
import sys
from pathlib import Path

_src_dir = Path(__file__).resolve().parent / "src"
if str(_src_dir) not in sys.path:
    sys.path.insert(0, str(_src_dir))

from main import main

if __name__ == "__main__":
    main()
