# -*- coding: utf-8 -*-
"""小红书自我迭代 Agent。

架构见 docs/技术方案.md：
  调度(计划任务) → 选题 → 调研(search/详情) → 写内容(AI 排队/模板兜底)
  → 封面 → 发布(主站发布页 UI) → 数据回流打分 → 复盘出 insights → 反哺下一篇。
所有浏览器操作共用一个 Playwright persistent context（user_data/ 存登录态）。
"""
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]   # 项目根（含 src/ data/ user_data/）
DATA_DIR = ROOT / "data"                     # 运行数据（gitignore）
RUNS_DIR = DATA_DIR / "runs"                 # 每次运行的截图/产物归档
NOTES_DIR = ROOT / "notes"                   # 抓取的笔记
USER_DATA = ROOT / "user_data"               # 浏览器登录态（勿删）
PENDING = DATA_DIR / "pending_note.json"     # AI 排队待发内容
ARCHIVE_DIR = DATA_DIR / "archive"           # 已发布内容归档


def new_run_dir(prefix: str = "") -> Path:
    """为一次运行创建归档目录 data/runs/<prefix><时间戳>/"""
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    d = RUNS_DIR / (f"{prefix}_{stamp}" if prefix else stamp)
    d.mkdir(parents=True, exist_ok=True)
    return d
