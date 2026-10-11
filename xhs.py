#!/usr/bin/env python3
"""小红书笔记抓取（Playwright 极简版）

用法:
  python xhs.py login                 首次使用：弹出浏览器登录(扫码)，登录态保存到 ./user_data
  python xhs.py <笔记链接> [更多链接]   抓取笔记 -> ./notes/<笔记id>/note.md（图片一并下载）

说明:
  - 链接用完整分享链接（带 xsec_token 参数）最稳，短链接 xhslink.com/xxx 也支持。
  - 默认弹出浏览器窗口运行（不易触发风控，遇到验证码可手动滑一下）；加 --headless 无头运行。
"""

import argparse
import time
from datetime import datetime
from pathlib import Path

from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parent
USER_DATA = ROOT / "user_data"   # 浏览器配置目录（存登录态，勿删）
NOTES_DIR = ROOT / "notes"       # 抓取结果输出目录
HOME = "https://www.xiaohongshu.com"
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/133.0.0.0 Safari/537.36")
EXT_BY_TYPE = {"image/jpeg": ".jpg", "image/webp": ".webp", "image/png": ".png",
               "image/avif": ".avif", "video/mp4": ".mp4"}

# 页面数据藏在 window.__INITIAL_STATE__.note.noteDetailMap 里，是 Vue 响应式代理，
# 整体序列化会失败，所以在这里只挑出需要的字段，拼成普通对象返回。
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


def launch(headless=False):
    pw = sync_playwright().start()
    ctx = pw.chromium.launch_persistent_context(
        str(USER_DATA),
        headless=headless,
        user_agent=UA,
        locale="zh-CN",
        timezone_id="Asia/Shanghai",
        viewport={"width": 1400, "height": 900},
        args=["--disable-blink-features=AutomationControlled"],
        ignore_default_args=["--enable-automation"],
    )
    return pw, ctx


def has_login(ctx) -> bool:
    return any(c["name"] == "web_session" and c["value"]
               for c in ctx.cookies(HOME))


def cmd_login():
    pw, ctx = launch()
    try:
        page = ctx.new_page()
        page.goto(HOME, wait_until="domcontentloaded")
        print("请在弹出的浏览器窗口里登录小红书（扫码/验证码均可）...")
        deadline = time.time() + 300
        while time.time() < deadline:
            if has_login(ctx):
                print("✅ 登录成功！登录态已保存到 ./user_data，以后不用再登。")
                return
            time.sleep(2)
        print("⌛ 等了 5 分钟还没登录，下次再运行 python xhs.py login 即可。")
    finally:
        ctx.close()
        pw.stop()


def wait_note_data(page, timeout_s=60):
    """轮询页面，拿到笔记 JSON（普通对象）就返回，超时返回 None"""
    deadline = time.time() + timeout_s
    while time.time() < deadline:
        try:
            data = page.evaluate(EXTRACT_JS)
        except Exception:
            data = None
        if data:
            return data
        time.sleep(1)
    return None


def download(ctx, url: str, stem: Path) -> Path | None:
    """按响应 Content-Type 补扩展名，返回实际写入的文件路径"""
    try:
        r = ctx.request.get(url, headers={"Referer": HOME + "/"}, timeout=30000)
        if r.ok and r.body():
            ctype = (r.headers.get("content-type") or "").split(";")[0].strip()
            path = stem.with_suffix(EXT_BY_TYPE.get(ctype, ".jpg"))
            path.write_bytes(r.body())
            return path
    except Exception as e:
        print(f"  ⚠️ 下载失败 {url[:60]}...: {e}")
    return None


def save_note(ctx, data: dict, src_url: str) -> Path:
    out = NOTES_DIR / data["id"]
    out.mkdir(parents=True, exist_ok=True)

    img_files = []
    for i, url in enumerate(data["images"], 1):
        f = download(ctx, url, out / f"{i:02d}")
        if f:
            img_files.append(f.name)
            print(f"  🖼️ 图片 {i}/{len(data['images'])} 已下载")

    video_file = None
    if data["video"]:
        vf = download(ctx, data["video"], out / "video")
        if vf:
            video_file = vf.name
            print("  🎬 视频已下载")

    ts = data["time"]
    t = datetime.fromtimestamp(ts / 1000).strftime("%Y-%m-%d %H:%M") if ts else "未知"
    title = data["title"].strip() or data["desc"].strip()[:30] or "无标题"

    lines = [
        f"# {title}",
        "",
        f"- 作者：{data['nickname']}",
        f"- 发布时间：{t}",
        f"- IP 属地：{data['ipLocation'] or '未知'}",
        f"- 数据：赞 {data['liked']} | 收藏 {data['collected']} "
        f"| 评论 {data['comments']} | 分享 {data['shares']}",
        f"- 类型：{'视频' if data['type'] == 'video' else '图文'}",
        f"- 原文：{src_url}",
    ]
    if data["tags"]:
        lines.append(f"- 标签：{' '.join('#' + t2 for t2 in data['tags'])}")
    lines += ["", "---", "", data["desc"].strip() or "（无正文）"]
    for f in img_files:
        lines += ["", f"![图片]({f})"]
    if video_file:
        lines += ["", f"[视频文件]({video_file})"]

    md = out / "note.md"
    md.write_text("\n".join(lines), encoding="utf-8")
    return md


def cmd_fetch(urls: list[str], headless: bool):
    pw, ctx = launch(headless=headless)
    try:
        if not has_login(ctx):
            print("⚠️  未检测到登录态，先试试抓（部分笔记不登录也能看）；失败就运行 python xhs.py login")
        ok = 0
        for url in urls:
            print(f"\n📄 抓取：{url}")
            page = ctx.new_page()
            try:
                page.goto(url, wait_until="domcontentloaded", timeout=60000)
                data = wait_note_data(page, timeout_s=60)
                if not data:
                    raise RuntimeError(
                        "60 秒内没拿到笔记数据。常见原因：① 登录过期 -> python xhs.py login；"
                        "② 链接缺 xsec_token -> 换完整分享链接；③ 页面有验证码 -> 用非 --headless 模式手动过一下。")
                md = save_note(ctx, data, url)
                print(f"  ✅ 已保存：{md}")
                ok += 1
            except Exception as e:
                print(f"  ❌ {e}")
            finally:
                page.close()
        print(f"\n完成：{ok}/{len(urls)} 篇成功，输出目录 {NOTES_DIR}")
    finally:
        ctx.close()
        pw.stop()


def main():
    ap = argparse.ArgumentParser(description="小红书笔记抓取",
                                 formatter_class=argparse.RawDescriptionHelpFormatter,
                                 epilog=__doc__.split("用法:")[1])
    ap.add_argument("items", nargs="+", help="login 或 笔记链接（可多个）")
    ap.add_argument("--headless", action="store_true", help="无头模式运行（不弹窗口）")
    args = ap.parse_args()

    if args.items[0] == "login":
        cmd_login()
    else:
        cmd_fetch(args.items, args.headless)


if __name__ == "__main__":
    main()
