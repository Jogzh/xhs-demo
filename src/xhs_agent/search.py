# -*- coding: utf-8 -*-
"""关键词搜索 —— 搜索页 DOM 提取（xhs-agent browser_research 方案，改为 persistent context）。

返回 [{note_id, xsec_token, title, author, like}]。
xsec_token 是详情页硬门槛：必须随取随用（从搜索卡片 a[href] 提取），不要长期存储。
"""
import re
from urllib.parse import quote

from xhs_agent.browser import HOME

# 搜索结果卡片提取
SEARCH_CARDS_JS = """() => {
    const out = [];
    for (const el of document.querySelectorAll('section.note-item')) {
        const a = el.querySelector('a[href*="xsec_token"]');
        if (!a) continue;
        const href = a.getAttribute('href') || '';
        const m = href.match(/\\/(?:search_result|explore)\\/([0-9a-f]{24})/);
        const tok = (href.match(/xsec_token=([^&]+)/) || [])[1] || '';
        const title = (el.querySelector('a.title')?.textContent
                       || el.querySelector('.title')?.textContent || '').trim();
        const author = (el.querySelector('.author .name')?.textContent || '').trim();
        const like = (el.querySelector('.like-wrapper .count')?.textContent || '').trim();
        if (m && tok) out.push({note_id: m[1], xsec_token: tok, title, author, like});
    }
    return out;
}"""

ID_TOKEN_RE = re.compile(r"/(?:search_result|explore|discovery/item)/([0-9a-f]{24})")
TOKEN_RE = re.compile(r"xsec_token=([^&]+)")


def search(b, keyword: str, top_n: int = 20) -> list:
    """搜索笔记卡片。b: Browser 实例。"""
    page = b.new_page()
    try:
        b.goto(page, f"{HOME}/search_result?keyword={quote(keyword)}&source=web_explore_feed")
        try:
            page.wait_for_selector("section.note-item", timeout=20000)
        except Exception:
            pass
        page.wait_for_timeout(1500)
        cards = page.evaluate(SEARCH_CARDS_JS)
        return cards[:top_n]
    finally:
        page.close()


# 主页笔记卡片：note_id / xsec_token / 标题整卡提取（与 spy.py 同构）
PROFILE_CARDS_JS = """() => {
    const out = [];
    for (const el of document.querySelectorAll('section.note-item')) {
        const a = el.querySelector('a[href*="xsec_token"]');
        if (!a) continue;
        const href = a.getAttribute('href') || '';
        const m = href.match(/\\/(?:search_result|explore|discovery\\/item)\\/([0-9a-f]{24})/);
        const tok = (href.match(/xsec_token=([^&]+)/) || [])[1] || '';
        const title = (el.querySelector('a.title')?.textContent
                       || el.querySelector('.title')?.textContent || '').trim();
        if (m) out.push({note_id: m[1], xsec_token: tok, title});
    }
    return out;
}"""


def profile_tokens(b, user_id: str) -> dict:
    """个人主页所有笔记的 {note_id: xsec_token}（metrics 回流用）。"""
    return {c["note_id"]: c["xsec_token"] for c in profile_notes(b, user_id)
            if c.get("xsec_token")}


def profile_notes(b, user_id: str) -> list:
    """个人主页笔记卡片 [{note_id, xsec_token, title}]。

    带标题：发布时 success 页偶尔抓不到 note_id（存了 NULL），
    回流阶段靠标题匹配回填。
    """
    page = b.new_page()
    try:
        b.goto(page, f"{HOME}/user/profile/{user_id}")
        page.wait_for_timeout(4000)
        return page.evaluate(PROFILE_CARDS_JS)
    finally:
        page.close()
