# -*- coding: utf-8 -*-
"""SQLite 存储层（WAL 模式），表设计见 docs/技术方案.md §4.8。

settings(开关热更新) / topics(主题池) / runs(审计+幂等) / notes(我方笔记)
metrics(互动快照) / competitors(调研对标) / insights(策略库)
"""
import json
import sqlite3
from datetime import datetime

from xhs_agent import DATA_DIR

DB_PATH = DATA_DIR / "app.db"

SCHEMA = """
CREATE TABLE IF NOT EXISTS settings (
    key        TEXT PRIMARY KEY,
    value      TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS topics (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    name         TEXT UNIQUE NOT NULL,
    status       TEXT NOT NULL DEFAULT 'active',   -- active/paused
    last_used_at TEXT
);
CREATE TABLE IF NOT EXISTS runs (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    run_date    TEXT NOT NULL,
    kind        TEXT NOT NULL,                     -- publish/metrics/research/refresh
    topic       TEXT,
    trigger     TEXT NOT NULL DEFAULT 'auto',      -- auto/manual
    status      TEXT NOT NULL,                     -- running/success/failed/skipped
    error       TEXT,
    started_at  TEXT NOT NULL,
    finished_at TEXT
);
CREATE UNIQUE INDEX IF NOT EXISTS idx_runs_daily ON runs(run_date, kind) WHERE status='success';
CREATE TABLE IF NOT EXISTS notes (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id       INTEGER REFERENCES runs(id),
    xhs_note_id  TEXT UNIQUE,
    title        TEXT NOT NULL,
    descr        TEXT NOT NULL DEFAULT '',
    image_paths  TEXT NOT NULL DEFAULT '[]',
    topics_json  TEXT NOT NULL DEFAULT '[]',
    strategy     TEXT NOT NULL DEFAULT '',
    is_private   INTEGER NOT NULL DEFAULT 0,
    published_at TEXT,
    score        REAL,
    finished     INTEGER NOT NULL DEFAULT 0        -- T+7 结题
);
CREATE TABLE IF NOT EXISTS metrics (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    note_id    INTEGER NOT NULL REFERENCES notes(id),
    captured_at TEXT NOT NULL,
    day_offset INTEGER,                            -- 距发布天数，T+1/3/7
    likes      INTEGER, collects INTEGER,
    comments   INTEGER, shares INTEGER
);
CREATE TABLE IF NOT EXISTS competitors (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    keyword     TEXT NOT NULL,
    note_id     TEXT NOT NULL,
    title       TEXT NOT NULL DEFAULT '',
    author      TEXT NOT NULL DEFAULT '',
    likes       TEXT,
    collected   TEXT, comments TEXT,
    raw_json    TEXT NOT NULL DEFAULT '{}',
    captured_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_competitors_kw ON competitors(keyword);
CREATE TABLE IF NOT EXISTS insights (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    scope      TEXT NOT NULL,                      -- 标题/正文/标签/发布
    content    TEXT NOT NULL,
    evidence   TEXT NOT NULL DEFAULT '',
    active     INTEGER NOT NULL DEFAULT 1,
    created_at TEXT NOT NULL
);
"""

# 打分权重：互动深度（评论/转发）权重高于点赞
SCORE_W = {"likes": 1.0, "comments": 2.0, "shares": 3.0, "collects": 1.5}


def connect() -> sqlite3.Connection:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.executescript(SCHEMA)
    return conn


def now() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def today() -> str:
    return datetime.now().strftime("%Y-%m-%d")


def score_of(likes, comments, shares, collects) -> float:
    return (SCORE_W["likes"] * _num(likes) + SCORE_W["comments"] * _num(comments)
            + SCORE_W["shares"] * _num(shares) + SCORE_W["collects"] * _num(collects))


def _num(v) -> int:
    """互动数可能是 '1.2万'/'35'/None 之类的展示值，粗转整数。"""
    if v in (None, "", False):
        return 0
    s = str(v).strip()
    try:
        return int(float(s.replace("万", "")) * (10000 if "万" in s else 1))
    except ValueError:
        return 0


# ---------- settings ----------

def get_setting(key: str, default: str = "") -> str:
    with connect() as conn:
        row = conn.execute("SELECT value FROM settings WHERE key=?", (key,)).fetchone()
        return row["value"] if row else default


def set_setting(key: str, value: str):
    with connect() as conn:
        conn.execute(
            "INSERT INTO settings(key,value,updated_at) VALUES(?,?,?) "
            "ON CONFLICT(key) DO UPDATE SET value=excluded.value, updated_at=excluded.updated_at",
            (key, value, now()))


def master_switch_on() -> bool:
    return get_setting("master_switch", "on") == "on"


# ---------- topics ----------

def pick_topic() -> str | None:
    """轮询主题池：active 里最久未用的优先，用完标记 last_used_at。"""
    with connect() as conn:
        row = conn.execute(
            "SELECT name FROM topics WHERE status='active' "
            "ORDER BY COALESCE(last_used_at,'') ASC LIMIT 1").fetchone()
        if row:
            conn.execute("UPDATE topics SET last_used_at=? WHERE name=?", (now(), row["name"]))
            return row["name"]
    return None


def add_topic(name: str):
    with connect() as conn:
        conn.execute("INSERT OR IGNORE INTO topics(name) VALUES(?)", (name,))


# ---------- runs（幂等：同一天同 kind 只允许一次成功）----------

def run_started(kind: str, topic: str | None, trigger: str) -> int | None:
    """开始一次运行；当天同 kind 已有 success 则返回 None（幂等跳过）。"""
    with connect() as conn:
        # 清理僵死 running（进程被强杀残留），超过 20 分钟视为失败
        conn.execute(
            "UPDATE runs SET status='failed', error='interrupted', finished_at=? "
            "WHERE status='running' AND started_at < datetime('now','localtime','-20 minutes')",
            (now(),))
        dup = conn.execute(
            "SELECT id FROM runs WHERE run_date=? AND kind=? AND status='success'",
            (today(), kind)).fetchone()
        if dup:
            return None
        cur = conn.execute(
            "INSERT INTO runs(run_date,kind,topic,trigger,status,started_at) "
            "VALUES(?,?,?,?, 'running', ?)",
            (today(), kind, topic, trigger, now()))
        return cur.lastrowid


def run_finished(run_id: int, status: str, error: str = ""):
    with connect() as conn:
        conn.execute("UPDATE runs SET status=?, error=?, finished_at=? WHERE id=?",
                     (status, error, now(), run_id))


def has_run_today(kind: str) -> bool:
    with connect() as conn:
        row = conn.execute(
            "SELECT 1 FROM runs WHERE run_date=? AND kind=? AND status IN ('running','success')",
            (today(), kind)).fetchone()
        return bool(row)


# ---------- notes / metrics ----------

def save_note(run_id: int, title: str, descr: str, image_paths: list, topics: list,
              strategy: str, is_private: bool, xhs_note_id: str | None) -> int:
    with connect() as conn:
        cur = conn.execute(
            "INSERT INTO notes(run_id,title,descr,image_paths,topics_json,strategy,"
            "is_private,published_at,xhs_note_id) VALUES(?,?,?,?,?,?,?,?,?)",
            (run_id, title, descr, json.dumps(image_paths, ensure_ascii=False),
             json.dumps(topics, ensure_ascii=False), strategy, int(is_private),
             now(), xhs_note_id))
        return cur.lastrowid


def pending_metric_notes() -> list:
    """发布未满 7 天且未结题的笔记。"""
    with connect() as conn:
        rows = conn.execute(
            "SELECT id, xhs_note_id, title, published_at FROM notes "
            "WHERE xhs_note_id IS NOT NULL AND finished=0").fetchall()
        return [dict(r) for r in rows]


def save_metric(note_row_id: int, day_offset: int, likes, collects, comments, shares) -> float:
    """写一条快照并更新笔记总分，返回 score。"""
    score = score_of(likes, comments, shares, collects)
    with connect() as conn:
        conn.execute(
            "INSERT INTO metrics(note_id,captured_at,day_offset,likes,collects,comments,shares) "
            "VALUES(?,?,?,?,?,?,?)",
            (note_row_id, now(), day_offset, _num(likes), _num(collects),
             _num(comments), _num(shares)))
        conn.execute("UPDATE notes SET score=? WHERE id=?", (score, note_row_id))
    return score


def finish_note(note_row_id: int):
    with connect() as conn:
        conn.execute("UPDATE notes SET finished=1 WHERE id=?", (note_row_id,))


# ---------- competitors / insights ----------

def save_competitors(keyword: str, cards: list):
    """cards: search/note_detail 返回的 dict 列表，raw_json 存全文详情。"""
    with connect() as conn:
        for c in cards:
            it = c.get("interact") or {}
            conn.execute(
                "INSERT INTO competitors(keyword,note_id,title,author,likes,collected,"
                "comments,raw_json,captured_at) VALUES(?,?,?,?,?,?,?,?,?)",
                (keyword, c.get("note_id", ""), c.get("title", ""), c.get("author", ""),
                 it.get("likes"), it.get("collects"), it.get("comments"),
                 json.dumps(c, ensure_ascii=False), now()))


def save_insight(scope: str, content: str, evidence: str = "") -> int:
    with connect() as conn:
        cur = conn.execute(
            "INSERT INTO insights(scope,content,evidence,created_at) VALUES(?,?,?,?)",
            (scope, content, evidence, now()))
        return cur.lastrowid


def active_insights(limit: int = 10) -> list:
    with connect() as conn:
        rows = conn.execute(
            "SELECT id, scope, content, evidence, created_at FROM insights "
            "WHERE active=1 ORDER BY id DESC LIMIT ?", (limit,)).fetchall()
        return [dict(r) for r in rows]
