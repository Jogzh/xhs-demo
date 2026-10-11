# -*- coding: utf-8 -*-
"""对标博主无痕采集 —— 全新浏览器 context、不登录、不碰 user_data/。

与 research 的分工：research 用登录态搜索（≈6 次页面访问，占 300012 风控额度，
和发布抢额度，一天最多 1 次）；spy 用无痕 context 直接访问博主主页，
登录态零消耗，也不影响当天发布额度。

博主清单：data/bloggers.txt，每行 `名称 链接`（# 开头为注释），不进 git。
产物：data/runs/<ts>_spy/bloggers.json + spy.md（写 pending 时的对标依据）。
"""
import json
import re
from datetime import datetime

from playwright.sync_api import sync_playwright

from xhs_agent import DATA_DIR, new_run_dir
from xhs_agent.browser import UA
from xhs_agent.research import EMOJI_RE, _to_int

BLOGGERS_FILE = DATA_DIR / "bloggers.txt"

# 主页笔记卡片（与搜索卡片同构：标题 + 点赞数，链接里带 note_id）
CARDS_JS = """() => {
    const out = [];
    for (const el of document.querySelectorAll('section.note-item')) {
        const a = el.querySelector('a[href*="/discovery/item/"], a[href*="/explore/"], a[href*="xsec_token"]');
        const href = a ? (a.getAttribute('href') || '') : '';
        const m = href.match(/\\/(?:discovery\\/item|explore|search_result)\\/([0-9a-f]{24})/);
        const title = (el.querySelector('a.title')?.textContent
                       || el.querySelector('.title')?.textContent || '').trim();
        const like = (el.querySelector('.like-wrapper .count')?.textContent
                      || el.querySelector('.count')?.textContent || '').trim();
        if (title || m) out.push({note_id: m ? m[1] : '', title, like});
    }
    return out;
}"""

# 博主元信息：优先 INITIAL_STATE 挑字段（整体序列化会炸，见 6d6c15e），兜底 DOM
META_JS = """() => {
    const pick = (sels) => {
        for (const s of sels) {
            const el = document.querySelector(s);
            if (el && el.textContent.trim()) return el.textContent.trim();
        }
        return '';
    };
    let st = {};
    try {
        const u = window.__INITIAL_STATE__ && window.__INITIAL_STATE__.user;
        if (u && u.userPageData) {
            st = {nickname: u.userPageData.nickname || '',
                  desc: u.userPageData.desc || '',
                  fans: u.userPageData.fans || ''};
        }
    } catch (e) {}
    return {
        nickname: st.nickname || pick(['.user-name', '.nickname']),
        desc: st.desc || pick(['.user-desc', '.desc']),
        fans: String(st.fans || pick(['.fans .count', '.user-interactions .fans'])),
    };
}"""


def load_bloggers() -> list:
    """读 data/bloggers.txt → [(名称, 链接), ...]。"""
    if not BLOGGERS_FILE.exists():
        return []
    out = []
    for line in BLOGGERS_FILE.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "://" not in line:
            continue
        parts = line.split(None, 1)
        if len(parts) == 2:
            out.append((parts[0], parts[1].strip()))
    return out


def _dismiss_login_popup(page):
    """未登录访问主页可能弹登录框，尽力关掉（Esc 通常足够）。"""
    for _ in range(2):
        try:
            page.keyboard.press("Escape")
        except Exception:
            pass
        page.wait_for_timeout(400)


def _scroll_and_collect(page, scrolls: int) -> list:
    """下滚加载更多笔记卡片，数量连续 2 轮不涨就停。"""
    prev, stable = 0, 0
    for _ in range(scrolls):
        page.mouse.wheel(0, 1400)
        page.wait_for_timeout(1300)
        n = len(page.evaluate(CARDS_JS))
        if n == prev:
            stable += 1
            if stable >= 2:
                break
        else:
            stable = 0
        prev = n
    return page.evaluate(CARDS_JS)


def _dedupe(cards: list) -> list:
    seen, out = set(), []
    for c in cards:
        key = c.get("note_id") or c.get("title")
        if key and key not in seen:
            seen.add(key)
            out.append(c)
    return out


def _collect(ctx, name: str, url: str, scrolls: int) -> dict:
    page = ctx.new_page()
    try:
        page.goto(url, wait_until="domcontentloaded", timeout=60000)
        page.wait_for_timeout(2500)
        try:
            page.wait_for_selector("section.note-item", timeout=15000)
        except Exception:
            pass   # 拿不到卡片也继续，靠截图/返回值诊断
        _dismiss_login_popup(page)
        cards = _dedupe(_scroll_and_collect(page, scrolls))
        meta = page.evaluate(META_JS)
        print(f"  [{name}] {len(cards)} 篇 | 昵称 {meta.get('nickname') or '?'} "
              f"粉丝 {meta.get('fans') or '?'}")
        return {"name": name, "url": url, "final_url": page.url,
                "meta": meta, "cards": cards}
    finally:
        page.close()


def spy(bloggers: list, scrolls: int = 6, out_dir=None, headless: bool = False) -> dict:
    """无痕采集一组博主主页，返回 {results, report_path}。"""
    out_dir = out_dir or new_run_dir("spy")
    results = []
    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=headless)
        try:
            ctx = browser.new_context(
                user_agent=UA, locale="zh-CN", timezone_id="Asia/Shanghai",
                viewport={"width": 1400, "height": 900},
            )
            for name, url in bloggers:
                results.append(_collect(ctx, name, url, scrolls))
        finally:
            browser.close()

    (out_dir / "bloggers.json").write_text(
        json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8")
    report = _render_md(results, out_dir)
    return {"results": results, "report_path": str(report)}


def _render_md(results: list, out_dir) -> "Path":
    """每位博主：互动 top 笔记 + 标题共性统计（AI 写 pending 的对标依据）。"""
    from pathlib import Path
    lines = [f"# 对标博主采集 {datetime.now():%Y-%m-%d %H:%M}", ""]
    for r in results:
        meta = r["meta"] or {}
        cards = sorted(r["cards"], key=lambda c: _to_int(c.get("like")), reverse=True)
        likes = [_to_int(c.get("like")) for c in cards]
        titles = [c["title"] for c in cards if c["title"]]
        lens = [len(re.sub(EMOJI_RE, "", t)) for t in titles]
        n_num = sum(1 for t in titles if re.search(r"\d", t))
        n_emo = sum(1 for t in titles if EMOJI_RE.search(t))
        lines += [
            f"## {r['name']}（{meta.get('nickname') or '?'}，粉丝 {meta.get('fans') or '?'}）",
            f"链接 {r['url']} → {r['final_url']}",
            f"采集 {len(cards)} 篇，赞 {min(likes) if likes else 0}~"
            f"{max(likes) if likes else 0}（中位 {sorted(likes)[len(likes)//2] if likes else 0}）",
            f"标题长度（去emoji）{min(lens) if lens else 0}~{max(lens) if lens else 0} "
            f"平均 {sum(lens)/len(lens):.0f}；含数字 {n_num}/{len(titles)}，"
            f"含 emoji {n_emo}/{len(titles)}",
            "",
        ]
        for c in cards[:15]:
            lines.append(f"- 赞 {c.get('like') or 0:>6} | {c['title'][:50]}")
        lines.append("")

    report = Path(out_dir) / "spy.md"
    report.write_text("\n".join(lines), encoding="utf-8")
    print(f"📊 采集简报已写：{report}")
    return report
