# -*- coding: utf-8 -*-
"""命令行编排层 —— python -m xhs_agent <cmd>（需 PYTHONPATH=src）。

  login             扫码登录，登录态存 user_data/
  status            开关 / 排队内容 / 笔记得分 / 最近运行 / active insights
  pause / resume    总开关 off / on（计划任务全部跳过）
  search <关键词>    搜索打印 top 卡片
  fetch <链接>...    抓笔记存 notes/
  research          选题调研 → 爆款摘要 + competitors 入库（一天 1 次）
  publish-content   发布 AI 排队内容（默认 data/pending_note.json，发完归档）
  run-once          模板兜底发布（--topic X）
  daily             计划任务入口：只发排队内容，无则跳过（不盲发）
  metrics           数据回流打分（--auto 供计划任务，幂等）
  refresh           复盘出 insights（纯本地计算，无浏览器）
"""
import argparse
import json
import shutil
import sys

from xhs_agent import ARCHIVE_DIR, PENDING, db, new_run_dir
from xhs_agent.browser import Browser, RateLimitError
from xhs_agent.publisher import PublishError, publish
from xhs_agent.writer import generate


def _switch_guard(tag: str) -> bool:
    if not db.master_switch_on():
        print(f"[{tag}] 总开关为 off（先 resume），跳过")
        return False
    return True


# ---------- 发布 ----------

def _publish_one(content: dict, dry_run: bool, private: bool, trigger: str,
                 headless: bool, archive_src=None) -> int:
    """发布单篇内容 dict 并入库，返回 run_id（-1=跳过）。"""
    rid = db.run_started("publish", content.get("topic"), trigger)
    if rid is None:
        print("[publish] 今天已有成功发布记录，幂等跳过（每日最多 1 篇）")
        return -1
    shots = new_run_dir("publish")
    try:
        with Browser(headless=headless) as b:
            if not b.has_login():
                raise PublishError("登录态失效，请先运行: python -m xhs_agent login")
            res = publish(b.ctx, content, shots, dry_run=dry_run, private=private)
        if dry_run:
            db.run_finished(rid, "skipped", "dry-run")
            return rid
        db.save_note(rid, content["title"], content.get("body", ""),
                     content.get("images", []), content.get("topics", []),
                     content.get("strategy", ""), is_private=private,
                     xhs_note_id=res.get("note_id"))
        db.run_finished(rid, "success")
        if archive_src and archive_src.exists():
            ARCHIVE_DIR.mkdir(parents=True, exist_ok=True)
            dst = ARCHIVE_DIR / f"note_{shots.name.split('_', 1)[-1]}.json"
            shutil.move(str(archive_src), str(dst))
            print(f"[publish] 内容已归档: {dst}")
        print(f"[publish] 完成 note_id={res.get('note_id')} 截图: {shots}")
        return rid
    except (RateLimitError, PublishError) as e:
        db.run_finished(rid, "failed", str(e))
        print(f"[publish] 失败: {e}")
        return -1
    except Exception as e:
        db.run_finished(rid, "failed", f"{type(e).__name__}: {e}")
        print(f"[publish] 失败: {type(e).__name__}: {e}")
        return -1


def do_publish_content(file, dry_run: bool, private: bool, headless: bool) -> int:
    """发布 AI 写好的内容 JSON（ZCode 会话 AI 的工作通道）。"""
    if not _switch_guard("publish"):
        return -1
    if not file.exists():
        print(f"[publish] 内容文件不存在: {file}（AI 写 pending 请按 AGENTS.md）")
        return -1
    if file.suffix.lower() == ".md":   # markdown 直接发：取标题+正文，封面自动生成
        from xhs_agent.writer import from_markdown
        content = from_markdown(file)
    else:
        content = json.loads(file.read_text(encoding="utf-8"))
    content.setdefault("topic", "ai")
    print(f"[publish] 待发内容: {content['title']}")
    return _publish_one(content, dry_run, private, trigger="manual",
                        headless=headless, archive_src=file)


def do_daily(headless: bool) -> int:
    """计划任务入口：只发 AI 排队内容，没有则跳过（不盲发模板）。"""
    if not _switch_guard("daily"):
        return -1
    if not PENDING.exists():
        print("[daily] 无 AI 排队内容（data/pending_note.json），跳过。"
              "想发文章：在 ZCode 会话说'发文章'，或手动 run-once --topic X")
        return -1
    content = json.loads(PENDING.read_text(encoding="utf-8"))
    content.setdefault("topic", "ai")
    print(f"[daily] 发现 AI 排队内容: {content['title']}")
    return _publish_one(content, dry_run=False, private=False, trigger="auto",
                        headless=headless, archive_src=PENDING)


def do_run_once(topic: str, dry_run: bool, private: bool, headless: bool) -> int:
    """模板内容兜底发布。"""
    if not _switch_guard("run-once"):
        return -1
    content = generate(topic)
    content["topic"] = topic
    print(f"[run-once] 主题[{topic}] 标题: {content['title']}")
    return _publish_one(content, dry_run, private, trigger="manual", headless=headless)


# ---------- 读 / 回流 ----------

def do_search(keyword: str, top_n: int, headless: bool) -> int:
    with Browser(headless=headless) as b:
        from xhs_agent.search import search
        cards = search(b, keyword, top_n=top_n)
    print(f"「{keyword}」{len(cards)} 条：")
    for i, c in enumerate(cards, 1):
        print(f"  [{i}] 赞:{c['like']:>6} | {c['title'][:40]} | @{c['author']}")
    return len(cards)


def do_fetch(urls: list, headless: bool) -> int:
    with Browser(headless=headless) as b:
        from xhs_agent.fetch import fetch
        return fetch(b, urls)


def do_research(topic: str | None, headless: bool) -> int:
    if not _switch_guard("research"):
        return -1
    if db.has_run_today("research"):
        print("[research] 今天已调研过（红线：一天 1 次，防 300012 风控），跳过")
        return -1
    topic = topic or db.pick_topic() or "上班族减脂餐"
    rid = db.run_started("research", topic, "manual")
    try:
        with Browser(headless=headless) as b:
            from xhs_agent.research import research
            r = research(b, topic)
        db.run_finished(rid, "success")
        print(f"[research] 完成：{len(r['cards'])} 卡片 / {len(r['details'])} 详情，"
              f"简报 {r['report_path']}")
        return rid
    except (RateLimitError, Exception) as e:
        db.run_finished(rid, "failed", str(e))
        print(f"[research] 失败: {e}")
        return -1


def do_metrics(auto: bool, headless: bool) -> int:
    trigger = "auto" if auto else "manual"
    if not _switch_guard("metrics"):
        return -1
    if auto and db.has_run_today("metrics"):
        print("[metrics] 今天已回流过，幂等跳过")
        return -1
    rid = db.run_started("metrics", None, trigger)
    if rid is None:
        print("[metrics] 今天已有成功回流记录，跳过")
        return -1
    try:
        with Browser(headless=headless) as b:
            if not b.has_login():
                raise PublishError("登录态失效，请先运行: python -m xhs_agent login")
            from xhs_agent.analytics import collect_metrics
            collect_metrics(b, trigger=trigger)
        db.run_finished(rid, "success")
        return rid
    except (RateLimitError, Exception) as e:
        db.run_finished(rid, "failed", str(e))
        print(f"[metrics] 失败: {e}")
        return -1


# ---------- 展示 ----------

def do_topic(op: str, name: str | None):
    """主题池管理：topic add X / topic list / topic pause X / topic resume X。"""
    with db.connect() as conn:
        if op == "add":
            db.add_topic(name)
            return print(f"[topic] 已添加: {name}")
        if op in ("pause", "resume"):
            conn.execute("UPDATE topics SET status=? WHERE name=?",
                         ("active" if op == "resume" else "paused", name))
            return print(f"[topic] {name} → {'active' if op == 'resume' else 'paused'}")
        rows = conn.execute(
            "SELECT name, status, last_used_at FROM topics ORDER BY id").fetchall()
    print("主题池:")
    for r in rows:
        print(f"  [{'on ' if r['status'] == 'active' else 'off'}] {r['name']}"
              f"（上次使用 {r['last_used_at'] or '从未'}）")
    if not rows:
        print("  （空，topic add <名称> 添加；research 默认主题在 cli.py 兜底）")


def show_status():
    print(f"总开关: {'on' if db.master_switch_on() else 'off'}   数据库: {db.DB_PATH}")
    if PENDING.exists():
        try:
            t = json.loads(PENDING.read_text(encoding="utf-8")).get("title", "")
            print(f"AI 排队内容: {t}")
        except Exception:
            print("AI 排队内容: pending_note.json 解析失败（请检查格式）")
    else:
        print("AI 排队内容: 无")

    with db.connect() as conn:
        notes = conn.execute(
            "SELECT id, xhs_note_id, title, published_at, score, finished "
            "FROM notes ORDER BY id DESC LIMIT 10").fetchall()
        print(f"\n最近笔记 {len(notes)} 条:")
        for r in notes:
            print(f"  #{r['id']} [{'已结题' if r['finished'] else '观察中'}] "
                  f"{(r['title'] or '')[:24]} | 发布 {r['published_at']} | "
                  f"score={r['score']} | id={r['xhs_note_id']}")
        runs = conn.execute(
            "SELECT run_date, kind, status, error FROM runs ORDER BY id DESC LIMIT 8").fetchall()
        print("\n最近运行:")
        for r in runs:
            print(f"  {r['run_date']} {r['kind']:8s} {r['status']:8s} {r['error'] or ''}")
        insights = db.active_insights(5)
        print(f"\nactive insights（最近 {len(insights)} 条，AI 写 pending 时参考）:")
        for i in insights:
            print(f"  [{i['scope']}] {i['content']}")


def main():
    # 计划任务里 stdout 重定向到日志文件，默认 ANSI 编码遇到 emoji 会崩，强制 UTF-8
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")
    p = argparse.ArgumentParser(prog="xhs_agent", description="小红书自我迭代 Agent")
    p.add_argument("cmd", choices=["login", "status", "pause", "resume", "search", "fetch",
                                   "research", "publish-content", "run-once", "daily",
                                   "metrics", "refresh", "topic"])
    p.add_argument("args", nargs="*", help="search 的关键词 / fetch 的链接")
    p.add_argument("--topic", default=None)
    p.add_argument("--file", default=str(PENDING))
    p.add_argument("--top", type=int, default=10)
    p.add_argument("--private", action="store_true")
    p.add_argument("--dry-run", action="store_true")
    p.add_argument("--auto", action="store_true", help="metrics 计划任务模式（幂等）")
    p.add_argument("--headless", action="store_true", help="无头模式（默认弹窗，遇验证码可手动过）")
    a = p.parse_args()

    if a.cmd == "login":
        with Browser(headless=False) as b:
            sys.exit(0 if b.wait_login() else 1)
    if a.cmd == "status":
        return show_status()
    if a.cmd == "pause":
        db.set_setting("master_switch", "off")
        return print("总开关 → off（所有定时任务将跳过）")
    if a.cmd == "resume":
        db.set_setting("master_switch", "on")
        return print("总开关 → on")
    if a.cmd == "search":
        if not a.args:
            p.error("search 需要关键词")
        return do_search(a.args[0], a.top, a.headless)
    if a.cmd == "fetch":
        if not a.args:
            p.error("fetch 需要笔记链接")
        return do_fetch(a.args, a.headless)
    if a.cmd == "research":
        return do_research(a.topic, a.headless)
    if a.cmd == "publish-content":
        from pathlib import Path
        return do_publish_content(Path(a.file), a.dry_run, a.private, a.headless)
    if a.cmd == "run-once":
        return do_run_once(a.topic or db.pick_topic() or "上班族减脂餐",
                           a.dry_run, a.private, a.headless)
    if a.cmd == "daily":
        return do_daily(a.headless)
    if a.cmd == "metrics":
        return do_metrics(a.auto, a.headless)
    if a.cmd == "refresh":
        from xhs_agent.refresher import refresh
        return refresh()
    if a.cmd == "topic":
        ops = {"add", "list", "pause", "resume"}
        op = a.args[0] if a.args else "list"
        if op not in ops:
            p.error(f"topic 子命令: {sorted(ops)}")
        if op in ("add", "pause", "resume") and len(a.args) < 2:
            p.error(f"topic {op} 需要主题名")
        return do_topic(op, a.args[1] if len(a.args) > 1 else None)


if __name__ == "__main__":
    main()
