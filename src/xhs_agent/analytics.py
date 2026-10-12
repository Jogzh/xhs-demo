# -*- coding: utf-8 -*-
"""数据回流 —— 个人主页拿 xsec_token → 详情页读互动数 → metrics 快照 → 打分 → T+7 结题。

一次回流 = 1 次主页 + N 篇详情页访问，日频在风控安全线内。
"""
import re
import time
from datetime import datetime

from xhs_agent import DATA_DIR, db, new_run_dir
from xhs_agent.browser import HOME, UA, Browser, RateLimitError, detect_rate_limit
from xhs_agent.fetch import DETAIL_JS, note_detail
from xhs_agent.research import EMOJI_RE
from xhs_agent.search import profile_notes


def _norm_title(t: str) -> str:
    """标题归一化（去 emoji/空白）用于回填匹配。"""
    return re.sub(EMOJI_RE, "", t or "").replace(" ", "")[:12]


def collect_metrics(b: Browser, trigger: str = "auto") -> None:
    notes = db.pending_metric_notes()
    if not notes:
        print("[metrics] 没有待回流笔记（发布后自动进入观察期）")
        return

    user_id = b.user_id()
    if not user_id:
        print("[metrics] cookie 里没找到 x-user-id，无法访问个人主页")
        return

    cards = profile_notes(b, user_id)
    tokens = {c["note_id"]: c["xsec_token"] for c in cards if c.get("xsec_token")}
    print(f"[metrics] 个人主页拿到 {len(tokens)} 条笔记 token")

    # 发布时 success 页没抓到 note_id 的笔记，按标题前缀回填
    for n in notes:
        if n["xhs_note_id"]:
            continue
        key = _norm_title(n["title"])
        hit = next((c for c in cards if _norm_title(c.get("title")).startswith(key)), None)
        if hit:
            db.set_note_xhs_id(n["id"], hit["note_id"])
            n["xhs_note_id"] = hit["note_id"]
            print(f"[metrics] 回填 note_id: {n['title'][:18]} → {hit['note_id']}")
        else:
            print(f"[metrics] {n['title'][:18]} 主页没匹配到 note_id，跳过")

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


# ---------- 无痕回流（2026-10-12 账号风控后：全程不碰登录态）----------

PROFILE_FILE = DATA_DIR / "my_profile.txt"   # 自己的主页链接（不进 git）

# 主页卡片：note_id / xsec_token / 标题 / 点赞数一次拿全
INCOGNITO_CARDS_JS = """() => {
    const out = [];
    for (const el of document.querySelectorAll('section.note-item')) {
        const a = el.querySelector('a[href*="/discovery/item/"], a[href*="/explore/"], a[href*="xsec_token"]');
        const href = a ? (a.getAttribute('href') || '') : '';
        const m = href.match(/\\/(?:discovery\\/item|explore|search_result)\\/([0-9a-f]{24})/);
        const tok = (href.match(/xsec_token=([^&]+)/) || [])[1] || '';
        const title = (el.querySelector('a.title')?.textContent
                       || el.querySelector('.title')?.textContent || '').trim();
        const like = (el.querySelector('.like-wrapper .count')?.textContent
                      || el.querySelector('.count')?.textContent || '').trim();
        if (m) out.push({note_id: m[1], xsec_token: tok, title, like});
    }
    return out;
}"""


def load_profile_url() -> str | None:
    """读 data/my_profile.txt 里自己的主页链接。"""
    if PROFILE_FILE.exists():
        for line in PROFILE_FILE.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "://" in line:
                return line
    return None


def _incognito_ctx(pw, headless: bool):
    """fresh chromium context：无 cookie、不碰 user_data/，与 spy 无痕模式同参数。"""
    browser = pw.chromium.launch(
        headless=headless,
        args=["--disable-blink-features=AutomationControlled"],
        ignore_default_args=["--enable-automation"],
    )
    ctx = browser.new_context(
        user_agent=UA, locale="zh-CN", timezone_id="Asia/Shanghai",
        viewport={"width": 1400, "height": 900},
    )
    return browser, ctx


def collect_metrics_incognito(trigger: str = "manual", headless: bool = False) -> None:
    """无痕回流：主页卡片拿点赞（有 token 再进详情页拿全量互动）。

    页面访问预算：1 次主页 + 每篇待回流笔记 1 次详情页；无登录态、零账号风险。
    """
    notes = db.pending_metric_notes()
    if not notes:
        print("[metrics] 没有待回流笔记（发布后自动进入观察期）")
        return
    url = load_profile_url()
    if not url:
        print(f"[metrics] 缺自己主页链接，请写入 {PROFILE_FILE}（一行链接）")
        return

    out_dir = new_run_dir("metrics")
    from playwright.sync_api import sync_playwright
    with sync_playwright() as pw:
        browser, ctx = _incognito_ctx(pw, headless)
        try:
            page = ctx.new_page()
            page.goto(url, wait_until="domcontentloaded", timeout=60000)
            page.wait_for_timeout(2500)
            detect_rate_limit(page)
            try:
                page.wait_for_selector("section.note-item", timeout=15000)
            except Exception:
                pass
            for _ in range(2):   # 尽力关掉未登录弹窗
                page.keyboard.press("Escape")
                page.wait_for_timeout(400)
            # 下滚加载，卡片数稳定即停
            prev, stable = 0, 0
            for _ in range(4):
                page.mouse.wheel(0, 1400)
                page.wait_for_timeout(1200)
                n = len(page.evaluate(INCOGNITO_CARDS_JS))
                if n == prev:
                    stable += 1
                    if stable >= 2:
                        break
                else:
                    stable = 0
                prev = n
            cards = page.evaluate(INCOGNITO_CARDS_JS)
            final_url = page.url
            if not cards:
                page.screenshot(path=str(out_dir / "profile_fail.png"))
            page.close()

            print(f"[metrics] 无痕主页拿到 {len(cards)} 张卡片（落地 {final_url[:60]}）")
            if not cards:
                print(f"[metrics] 采不到卡片（可能登录墙/页面改版），证据: "
                      f"{out_dir / 'profile_fail.png'}")
                return

            by_id = {c["note_id"]: c for c in cards}
            tokens = {c["note_id"]: c["xsec_token"] for c in cards if c["xsec_token"]}
            done = 0
            for n in notes:
                xid = n["xhs_note_id"]
                if not xid:   # 按标题前缀回填 note_id
                    key = _norm_title(n["title"])
                    hit = next(
                        (c for c in cards
                         if _norm_title(c.get("title")).startswith(key)), None)
                    if hit:
                        db.set_note_xhs_id(n["id"], hit["note_id"])
                        xid = n["xhs_note_id"] = hit["note_id"]
                        print(f"[metrics] 回填 note_id: {n['title'][:18]} → {xid}")
                    else:
                        print(f"[metrics] {n['title'][:18]} 主页无匹配卡片"
                              f"（可能被判违规仅自己可见），跳过")
                        continue
                card = by_id.get(xid)
                like = card.get("like") if card else None
                interact = {"likes": like, "collects": None, "comments": None, "shares": None}
                tok = tokens.get(xid)
                if tok:   # 详情页一次，拿全量互动
                    try:
                        dpage = ctx.new_page()
                        dpage.goto(f"{HOME}/explore/{xid}?xsec_token={tok}"
                                   f"&xsec_source=pc_search",
                                   wait_until="domcontentloaded", timeout=60000)
                        deadline = time.time() + 20
                        data = None
                        while time.time() < deadline and not data:
                            try:
                                data = dpage.evaluate(DETAIL_JS)
                            except Exception:
                                data = None
                            if not data:
                                dpage.wait_for_timeout(1000)
                        dpage.close()
                        if data and data.get("interact"):
                            interact = data["interact"]
                    except Exception as e:
                        print(f"[metrics] 详情页失败（用主页点赞数兜底）: {e}")
                days = max(1, (datetime.now() - datetime.strptime(
                    n["published_at"], "%Y-%m-%d %H:%M:%S")).days)
                score = db.save_metric(n["id"], min(days, 7), interact.get("likes"),
                                       interact.get("collects"), interact.get("comments"),
                                       interact.get("shares"))
                if days >= 7:
                    db.finish_note(n["id"])
                    state = "T+7 已结题"
                else:
                    state = f"第 {days} 天"
                print(f"[metrics] {n['title'][:20]} | 赞 {interact.get('likes')} "
                      f"藏 {interact.get('collects')} 评 {interact.get('comments')} "
                      f"转 {interact.get('shares')} | score={score:.0f} | {state}")
                done += 1
            (out_dir / "metrics.txt").write_text(
                f"{datetime.now():%Y-%m-%d %H:%M} 无痕回流 {done}/{len(notes)} 篇\n",
                encoding="utf-8")
            print(f"[metrics] 完成 {done}/{len(notes)} 篇")
        finally:
            browser.close()
