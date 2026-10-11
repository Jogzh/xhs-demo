# -*- coding: utf-8 -*-
"""选题调研 —— search top 卡片 → 挑互动高的拉详情 → 爆款摘要。

产物：
  data/runs/<ts>_research/research.md   人/AI 可读的调研简报（写 pending 时的依据）
  competitors 表                         对标笔记入库（复盘可回溯）
频率红线：一次调研 ≈ 1 次搜索 + N 次详情页（6 次页面访问），一天最多 1 次。
"""
import re
from datetime import datetime

from xhs_agent import db
from xhs_agent.browser import Browser, RateLimitError
from xhs_agent.fetch import note_detail
from xhs_agent.search import search

EMOJI_RE = re.compile(r"[\U0001F000-\U0001FAFF\u2600-\u27BF\uFE0F]")


def _to_int(v) -> int:
    if v in (None, ""):
        return 0
    s = str(v).strip()
    try:
        return int(float(s.replace("万", "")) * (10000 if "万" in s else 1))
    except ValueError:
        return 0


def research(b: Browser, keyword: str, top_n: int = 20, detail_top: int = 5,
             out_dir=None) -> dict:
    """调研一个主题，返回 {keyword, cards, details, report_path}。"""
    from xhs_agent import new_run_dir
    out_dir = out_dir or new_run_dir("research")

    cards = search(b, keyword, top_n=top_n)
    if not cards:
        raise RuntimeError(f"搜索「{keyword}」没拿到卡片（可能风控前兆或页面改版）")

    # 按赞数排，拉前 N 篇详情
    ranked = sorted(cards, key=lambda c: _to_int(c.get("like")), reverse=True)
    details = []
    for c in ranked[:detail_top]:
        try:
            d = note_detail(b, c["note_id"], c["xsec_token"])
        except RateLimitError:
            print("  ⚠️ 拉详情触发风控，提前结束调研（已有数据够用）")
            break
        if d:
            d["author"] = c.get("author", "")
            details.append(d)

    db.save_competitors(keyword, details)

    report = _render_report(keyword, cards, details, out_dir)
    return {"keyword": keyword, "cards": cards, "details": details,
            "report_path": str(report)}


def _render_report(keyword: str, cards: list, details: list, out_dir) -> "Path":
    """爆款摘要：标题共性 / 互动量级 / 话题分布 / 可借鉴点。"""
    from pathlib import Path
    titles = [d["title"] or (d.get("desc") or "")[:20] for d in details]
    lens = [len(re.sub(EMOJI_RE, "", t)) for t in titles if t]
    n_emoji = sum(1 for t in titles if EMOJI_RE.search(t))
    n_digit = sum(1 for t in titles if re.search(r"\d", t))
    likes = [_to_int((d.get("interact") or {}).get("likes")) for d in details]

    tag_count: dict[str, int] = {}
    for d in details:
        for t in d.get("tags", [])[:8]:
            tag_count[t] = tag_count.get(t, 0) + 1
    hot_tags = sorted(tag_count.items(), key=lambda x: -x[1])[:8]

    lines = [
        f"# 「{keyword}」爆款调研 {datetime.now():%Y-%m-%d %H:%M}",
        f"搜索 {len(cards)} 条卡片，深挖互动最高 {len(details)} 篇。",
        "",
        "## 互动最高笔记",
    ]
    for d, lk in zip(details, likes):
        it = d.get("interact") or {}
        lines.append(f"- 赞 {it.get('likes')} 藏 {it.get('collects')} 评 {it.get('comments')}"
                     f" | @{d.get('author')} | {d.get('title') or (d.get('desc') or '')[:24]}")
    lines += [
        "",
        "## 标题共性（供 AI 写作参考）",
        f"- 标题长度（去 emoji）：{min(lens) if lens else 0}~{max(lens) if lens else 0} 字"
        f"（平均 {sum(lens) / len(lens):.0f}）" if lens else "- 无样本",
        f"- 含数字：{n_digit}/{len(titles or [1])}，含 emoji：{n_emoji}/{len(titles or [1])}",
        f"- 赞数区间：{min(likes) if likes else 0}~{max(likes) if likes else 0}",
    ]
    if hot_tags:
        lines += ["", "## 高频话题标签", " ".join(f"#{t}×{n}" for t, n in hot_tags)]
    lines += [
        "",
        "## 正文结构速览",
    ]
    for d in details[:3]:
        desc = (d.get("desc") or "").strip().replace("\n", " ⏎ ")
        lines.append(f"- {d.get('title') or ''}：{desc[:120]}")
    lines += ["", "## 建议写作方向", "- 结合上述标题句式/话题分布，写差异化内容；具体策略另见 insights。"]

    report = Path(out_dir) / "research.md"
    report.write_text("\n".join(lines), encoding="utf-8")
    print(f"📊 调研简报已写：{report}")
    return report
