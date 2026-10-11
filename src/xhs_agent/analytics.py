# -*- coding: utf-8 -*-
"""数据回流 —— 个人主页拿 xsec_token → 详情页读互动数 → metrics 快照 → 打分 → T+7 结题。

一次回流 = 1 次主页 + N 篇详情页访问，日频在风控安全线内。
"""
from datetime import datetime

from xhs_agent import db, new_run_dir
from xhs_agent.browser import Browser, RateLimitError
from xhs_agent.fetch import note_detail
from xhs_agent.search import profile_tokens


def collect_metrics(b: Browser, trigger: str = "auto") -> None:
    notes = db.pending_metric_notes()
    if not notes:
        print("[metrics] 没有待回流笔记（发布后自动进入观察期）")
        return

    user_id = b.user_id()
    if not user_id:
        print("[metrics] cookie 里没找到 x-user-id，无法访问个人主页")
        return

    tokens = profile_tokens(b, user_id)
    print(f"[metrics] 个人主页拿到 {len(tokens)} 条笔记 token")

    out_dir = new_run_dir("metrics")
    done = 0
    for n in notes:
        xid = n["xhs_note_id"]
        if xid not in tokens:
            print(f"[metrics] {xid} 不在主页列表（可能已删/未展示），跳过")
            continue
        try:
            d = note_detail(b, xid, tokens[xid])
        except RateLimitError:
            print("[metrics] 触发风控，中止本次回流，明天再来")
            break
        if not d:
            continue
        it = d.get("interact") or {}
        days = max(1, (datetime.now() - datetime.strptime(
            n["published_at"], "%Y-%m-%d %H:%M:%S")).days)
        score = db.save_metric(n["id"], min(days, 7), it.get("likes"),
                               it.get("collects"), it.get("comments"), it.get("shares"))
        if days >= 7:
            db.finish_note(n["id"])
            state = "T+7 已结题"
        else:
            state = f"第 {days} 天"
        print(f"[metrics] {n['title'][:20]} | 赞 {it.get('likes')} 藏 {it.get('collects')} "
              f"评 {it.get('comments')} 转 {it.get('shares')} | score={score:.0f} | {state}")
        done += 1

    (out_dir / "metrics.txt").write_text(
        f"{datetime.now():%Y-%m-%d %H:%M} 回流 {done}/{len(notes)} 篇\n", encoding="utf-8")
    print(f"[metrics] 完成 {done}/{len(notes)} 篇")
