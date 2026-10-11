# -*- coding: utf-8 -*-
"""复盘引擎（自我迭代的核心）—— 高分/低分笔记分组对比 → 结构化 insight 入库。

insights 表是策略库：AI 写 pending_note.json 时读 active insights（AGENTS.md 约定），
形成「发布 → 数据 → 结论 → 下一篇」的闭环。
"""
import json
import re
from datetime import datetime

from xhs_agent import db, new_run_dir

EMOJI_RE = re.compile(r"[\U0001F000-\U0001FAFF\u2600-\u27BF\uFE0F]")


def _features(note: dict) -> dict:
    title = note["title"] or ""
    body = note["descr"] or ""
    try:
        topics = json.loads(note.get("topics_json") or "[]")
    except Exception:
        topics = []
    return {
        "标题≤14字": len(re.sub(EMOJI_RE, "", title)) <= 14,
        "标题含数字": bool(re.search(r"\d", title)),
        "标题含emoji": bool(EMOJI_RE.search(title)),
        "标题疑问句": any(c in title for c in "？?吗呢"),
        "正文含清单": bool(re.search(r"[①②③📌\d+\.]", body)) or "·" in body,
        "正文≥400字": len(body) >= 400,
        "≥4个话题": len(topics) >= 4,
    }


def refresh() -> str:
    """复盘已结题笔记，返回人可读报告文本（同时写 insights 表）。"""
    with db.connect() as conn:
        notes = conn.execute(
            "SELECT id, title, descr, topics_json, score FROM notes "
            "WHERE finished=1 AND score IS NOT NULL ORDER BY score DESC").fetchall()
    notes = [dict(r) for r in notes]
    if len(notes) < 4:
        msg = f"已结题笔记 {len(notes)} 篇（<4），样本不足暂不复盘，先持续发布积累数据。"
        print(msg)
        return msg

    k = max(1, round(len(notes) * 0.3))
    high, low = notes[:k], notes[-k:]
    lines = [f"# 复盘报告 {datetime.now():%Y-%m-%d}",
             f"样本 {len(notes)} 篇已结题；高分组/低分组各 {k} 篇。",
             "",
             "## 分组",
             "### 高分组"]
    for n in high:
        lines.append(f"- score={n['score']:.0f} | {n['title'][:24]}")
    lines.append("### 低分组")
    for n in low:
        lines.append(f"- score={n['score']:.0f} | {n['title'][:24]}")

    lines += ["", "## 特征差异（高分组 vs 低分组占比）"]
    added = 0
    feats_h = [sum(_features(n)[f] for n in high) / len(high) for f in _features(high[0])]
    names = list(_features(high[0]).keys())
    feats_l = [sum(_features(n)[f] for n in low) / len(low) for f in names]
    for name, ph, pl in zip(names, feats_h, feats_l):
        diff = ph - pl
        mark = "↑" if diff >= 0.3 else ("↓" if diff <= -0.3 else " ")
        lines.append(f"- {mark} {name}: {ph:.0%} vs {pl:.0%}（差 {diff:+.0%}）")
        if abs(diff) >= 0.3:   # 差异 ≥30 个百分点才沉淀为策略
            direction = "多用" if diff > 0 else "少用"
            content = f"{direction}「{name}」——高分组 {ph:.0%}，低分组 {pl:.0%}"
            evidence = (f"高分: {'; '.join(n['title'][:16] for n in high[:2])} | "
                        f"低分: {'; '.join(n['title'][:16] for n in low[:2])}")
            db.save_insight(scope="写作策略", content=content, evidence=evidence)
            added += 1

    lines += ["", f"本次沉淀 insights {added} 条（AI 写 pending 时会读取）。"]
    report = "\n".join(lines)
    out = new_run_dir("refresh") / "insights.md"
    out.write_text(report, encoding="utf-8")
    print(report)
    print(f"📄 报告已存：{out}")
    return report
