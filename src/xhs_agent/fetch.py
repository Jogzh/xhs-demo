# -*- coding: utf-8 -*-
"""按链接抓取笔记 → notes/<笔记id>/note.md（图片/视频一并下载）。原 xhs.py cmd_fetch 平移。

页面数据藏在 window.__INITIAL_STATE__.note.noteDetailMap 里，是 Vue 响应式代理，
整体序列化会失败，所以只在 JS 端挑出需要的字段拼普通对象返回。
"""
import time
from datetime import datetime
from pathlib import Path

from xhs_agent import NOTES_DIR
from xhs_agent.browser import Browser, HOME

# 详情页数据提取（note.md 用，含图片/视频列表）
EXTRACT_JS = """() => {
    const map = window.__INITIAL_STATE__?.note?.noteDetailMap;
    if (!map) return null;
    for (const k of Object.keys(map)) {
        const n = map[k]?.note;
        if (!n || !(n.title || n.desc)) continue;
        const it = n.interactInfo || {};
        let video = null;
        try {
            for (const s of n.video.media.videoStream)
                if (!video || (s.videoBitrate || 0) > (video.bitrate || 0))
                    video = { url: s.masterUrl, bitrate: s.videoBitrate || 0 };
        } catch (e) {}
        const images = (n.imageList || []).map(img => {
            let url = null;
            for (const info of img.infoList || [])
                if (info.imageScene === 'WB_DFT' && info.url) { url = info.url; break; }
            return url || img.urlDefault || img.url || null;
        }).filter(Boolean);
        return {
            id: n.noteId || k,
            type: n.type || 'normal',
            title: n.title || '',
            desc: n.desc || '',
            time: n.time || null,
            ipLocation: n.ipLocation || '',
            nickname: (n.user && n.user.nickname) || '未知',
            liked: it.likedCount || '', collected: it.collectedCount || '',
            comments: it.commentCount || '', shares: it.shareCount || '',
            tags: (n.tagList || []).map(t => t && t.name).filter(Boolean),
            images,
            video: video ? video.url : null,
        };
    }
    return null;
}"""

# 结构化详情（research/metrics 用，字段更紧凑）
DETAIL_JS = """() => {
    const map = window.__INITIAL_STATE__?.note?.noteDetailMap || {};
    for (const k of Object.keys(map)) {
        const n = map[k]?.note;
        if (n && (n.title || n.desc)) return {
            note_id: k || null, type: n.type || 'normal',
            title: n.title || '', desc: n.desc || '',
            nickname: (n.user && n.user.nickname) || '',
            tags: (n.tagList || []).map(t => t.name),
            interact: {
                likes: n.interactInfo?.likedCount || null,
                collects: n.interactInfo?.collectedCount || null,
                comments: n.interactInfo?.commentCount || null,
                shares: n.interactInfo?.shareCount || null,
            },
            time: n.time || null, ip: n.ipLocation || '',
        };
    }
    return null;
}"""


def note_detail(b: Browser, note_id: str, xsec_token: str, timeout_s: int = 60) -> dict | None:
    """带 xsec_token 打开详情页，返回 DETAIL_JS 提取的紧凑结构（research/metrics 用）。"""
    page = b.new_page()
    try:
        b.goto(page, f"{HOME}/explore/{note_id}?xsec_token={xsec_token}&xsec_source=pc_search")
        deadline = time.time() + timeout_s
        while time.time() < deadline:
            try:
                data = page.evaluate(DETAIL_JS)
            except Exception:
                data = None
            if data:
                return data
            page.wait_for_timeout(1000)
        return None
    finally:
        page.close()


def _save_note_md(b: Browser, data: dict, src_url: str) -> Path:
    out = NOTES_DIR / data["id"]
    out.mkdir(parents=True, exist_ok=True)

    img_files = []
    for i, url in enumerate(data["images"], 1):
        f = b.download(url, out / f"{i:02d}")
        if f:
            img_files.append(f.name)
            print(f"  🖼️ 图片 {i}/{len(data['images'])} 已下载")

    video_file = None
    if data["video"]:
        vf = b.download(data["video"], out / "video")
        if vf:
            video_file = vf.name
            print("  🎬 视频已下载")

    ts = data["time"]
    t = datetime.fromtimestamp(ts / 1000).strftime("%Y-%m-%d %H:%M") if ts else "未知"
    title = data["title"].strip() or data["desc"].strip()[:30] or "无标题"

    lines = [
        f"# {title}", "",
        f"- 作者：{data['nickname']}",
        f"- 发布时间：{t}",
        f"- IP 属地：{data['ipLocation'] or '未知'}",
        f"- 数据：赞 {data['liked']} | 收藏 {data['collected']} "
        f"| 评论 {data['comments']} | 分享 {data['shares']}",
        f"- 类型：{'视频' if data['type'] == 'video' else '图文'}",
        f"- 原文：{src_url}",
    ]
    if data["tags"]:
        lines.append(f"- 标签：{' '.join('#' + t for t in data['tags'])}")
    lines += ["", "---", "", data["desc"].strip() or "（无正文）"]
    for f in img_files:
        lines += ["", f"![图片]({f})"]
    if video_file:
        lines += ["", f"[视频文件]({video_file})"]

    md = out / "note.md"
    md.write_text("\n".join(lines), encoding="utf-8")
    return md


def fetch(b: Browser, urls: list[str]) -> int:
    """抓取多个笔记链接到 notes/，返回成功数。"""
    if not b.has_login():
        print("⚠️  未检测到登录态，先试试抓（部分笔记不登录也能看）；失败就运行 login")
    ok = 0
    for url in urls:
        print(f"\n📄 抓取：{url}")
        page = b.new_page()
        try:
            b.goto(page, url, timeout=60000)
            deadline = time.time() + 60
            data = None
            while time.time() < deadline:
                try:
                    data = page.evaluate(EXTRACT_JS)
                except Exception:
                    data = None
                if data:
                    break
                page.wait_for_timeout(1000)
            if not data:
                raise RuntimeError(
                    "60 秒内没拿到笔记数据。常见原因：① 登录过期 -> login；"
                    "② 链接缺 xsec_token -> 换完整分享链接；③ 风控/验证码 -> 非 headless 手动过。")
            md = _save_note_md(b, data, url)
            print(f"  ✅ 已保存：{md}")
            ok += 1
        except Exception as e:
            print(f"  ❌ {e}")
        finally:
            page.close()
    print(f"\n完成：{ok}/{len(urls)} 篇成功，输出目录 {NOTES_DIR}")
    return ok
