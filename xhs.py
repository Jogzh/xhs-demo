#!/usr/bin/env python3
"""小红书笔记抓取/发布（Playwright 极简版）

用法:
  python xhs.py login                 首次使用：弹出浏览器登录(扫码)，登录态保存到 ./user_data
  python xhs.py <笔记链接> [更多链接]   抓取笔记 -> ./notes/<笔记id>/note.md（图片一并下载）
  python xhs.py post <文章.md>        发布笔记：自动生成封面图 + 上传 + 填内容 + 发布
      --img 图片路径                    指定图片（可多次）；不给就按文章自动生成封面
      --dry-run                        填完表单但不点发布，截图确认用

说明:
  - 抓取链接用完整分享链接（带 xsec_token 参数）最稳，短链接 xhslink.com/xxx 也支持。
  - 默认弹出浏览器窗口运行（不易触发风控，遇到验证码可手动滑一下）；加 --headless 无头运行。
"""

import argparse
import re
import time
from datetime import datetime
from pathlib import Path

from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parent
USER_DATA = ROOT / "user_data"   # 浏览器配置目录（存登录态，勿删）
NOTES_DIR = ROOT / "notes"       # 抓取结果输出目录
TMP_DIR = ROOT / ".tmp"          # 自动生成封面等临时文件
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


def parse_article(path: Path) -> tuple[str, str]:
    """从 markdown 里取标题（第一个 # 开头行）和正文（去掉标题行/图片行）"""
    text = Path(path).read_text(encoding="utf-8")
    lines = text.splitlines()
    title = next((l.lstrip("# ").strip() for l in lines if l.startswith("# ")), "")
    body = "\n".join(l for l in lines
                     if not l.startswith("# ") and not l.startswith("![")).strip()
    return title[:20], body[:1000]   # 小红书标题限 20 字、正文限 1000 字


COVER_HTML = """<!doctype html><html><head><meta charset="utf-8"><style>
  body {{ margin: 0 }}
  #cover {{ position: relative; width: 1080px; height: 1440px; box-sizing: border-box;
    background: linear-gradient(160deg, #ff2442 0%, #b3123a 55%, #4d0e2b 100%);
    display: flex; flex-direction: column; justify-content: center; padding: 96px;
    font-family: "Microsoft YaHei", sans-serif; color: #fff }}
  .kicker {{ font-size: 34px; letter-spacing: 10px; opacity: .85; margin-bottom: 44px }}
  .title  {{ font-size: 96px; font-weight: 700; line-height: 1.35 }}
  .sub    {{ margin-top: 60px; font-size: 42px; opacity: .92; line-height: 1.7 }}
  .footer {{ position: absolute; left: 96px; right: 96px; bottom: 72px; display: flex;
    justify-content: space-between; font-size: 30px; opacity: .7 }}
</style></head><body><div id="cover">
  <div class="kicker">AUTOMATION TEST</div>
  <div class="title">{title}</div>
  <div class="sub">{sub}</div>
  <div class="footer"><span>xhs-demo</span><span>{date}</span></div>
</div></body></html>"""


def make_cover(ctx, title: str, sub: str) -> Path:
    """用浏览器渲染一张 1080x1440 的封面图，返回图片路径"""
    TMP_DIR.mkdir(exist_ok=True)
    out = TMP_DIR / "cover.png"
    page = ctx.new_page()
    try:
        page.set_content(COVER_HTML.format(title=title, sub=sub,
                                           date=datetime.now().strftime("%Y-%m-%d")))
        page.wait_for_selector("#cover")
        page.wait_for_timeout(500)   # 等字体渲染
        page.locator("#cover").screenshot(path=str(out))
    finally:
        page.close()
    return out


def open_publish_page(ctx):
    """从官网顶栏点「发布」，像手动操作一样进入发布页（会新开一个标签页）"""
    home = ctx.new_page()
    home.goto(HOME, wait_until="domcontentloaded")
    home.wait_for_selector("span.channel", timeout=30000)
    with ctx.expect_page(timeout=30000) as pop:
        home.locator("span.channel").filter(has_text="发布").first.click()
    page = pop.value
    page.wait_for_load_state("domcontentloaded")
    home.close()
    return page


def cmd_post(article: str, imgs: list[str], headless: bool, dry_run: bool):
    title, body = parse_article(Path(article))
    if not title:
        return print("❌ 文章里没找到标题行（# 开头）")

    pw, ctx = launch(headless=headless)
    try:
        page = open_publish_page(ctx)
        page.wait_for_selector("input[type=file]", state="attached", timeout=30000)

        # 切到「上传图文」tab（顶栏/侧边栏有同名隐藏项，只点可见的）
        page.evaluate("""() => {
            const els = [...document.querySelectorAll('span,div')].filter(e =>
                e.childElementCount === 0 && e.textContent.trim() === '上传图文' && e.offsetParent);
            if (els.length) els[0].click();
        }""")
        page.wait_for_selector('input[type=file][accept*=".jpg"]',
                               state="attached", timeout=15000)

        # 没给图就自动生成一张封面
        paths = [str(Path(p).resolve()) for p in imgs]
        if not paths:
            sub = body.replace("\n", " ")[:40]
            cover = make_cover(ctx, title, sub)
            paths = [str(cover.resolve())]
            print(f"🖼️ 已自动生成封面：{cover}")
        page.set_input_files("input[type=file]", paths)
        print(f"⬆️  已上传 {len(paths)} 张图片，等待处理...")

        # 上传后才会出现标题/正文表单
        page.wait_for_selector("input[placeholder*='标题'], .d-title", timeout=60000)
        page.fill("input[placeholder*='标题'], .d-title", title)
        page.click("[contenteditable=true]")
        page.keyboard.insert_text(body)
        page.keyboard.press("Escape")   # 关掉话题联想下拉
        page.wait_for_timeout(1000)

        # 关掉「图片可以编辑啦」之类的新手引导弹窗
        tip = page.get_by_role("button", name="我知道了")
        if tip.count() and tip.first.is_visible():
            tip.first.click()
            page.wait_for_timeout(500)

        if dry_run:
            page.screenshot(path=str(ROOT / "post_dryrun.png"))
            print("🔎 dry-run：已填好表单但未发布，截图在 post_dryrun.png")
            return

        # 底部「发布」按钮取不到 DOM（shadow DOM 渲染，文本/类名/按钮角色都查不到），
        # 但它固定在视口底部中间偏右，按坐标点击（视口在 launch() 里固定为 1400x900）
        page.wait_for_timeout(1500)
        page.screenshot(path=str(TMP_DIR / "pre_publish.png"))
        vp = page.viewport_size
        page.mouse.click(int(vp["width"] / 2 + 60), vp["height"] - 45)
        page.wait_for_timeout(2000)
        # 有些内容会弹「发布声明/AI 声明」确认框，有就点确认
        confirm = page.locator("button:visible").filter(
            has_text=re.compile("确认|确定|仍然|继续"))
        if confirm.count():
            confirm.first.click()
            page.wait_for_timeout(2000)

        # 成功标志：跳转 success 页，或页面出现「发布成功」提示
        deadline = time.time() + 60
        while time.time() < deadline:
            if "success" in page.url or page.get_by_text("发布成功").count():
                print(f"✅ 发布成功！{page.url}")
                page.screenshot(path=str(ROOT / "post_success.png"))
                return
            page.wait_for_timeout(1000)
        page.screenshot(path=str(ROOT / "post_fail.png"))
        print(f"⚠️  点了发布但 60 秒内没看到成功标志，当前页面：{page.url}")
    finally:
        ctx.close()
        pw.stop()


def main():
    ap = argparse.ArgumentParser(description="小红书笔记抓取/发布",
                                 formatter_class=argparse.RawDescriptionHelpFormatter,
                                 epilog=__doc__.split("用法:")[1])
    ap.add_argument("items", nargs="+", help="login / post <文章md> / 笔记链接（可多个）")
    ap.add_argument("--img", action="append", default=[], help="post 用的图片，可多次指定")
    ap.add_argument("--headless", action="store_true", help="无头模式运行（不弹窗口）")
    ap.add_argument("--dry-run", action="store_true", help="post 填完表单但不点发布")
    args = ap.parse_args()

    if args.items[0] == "login":
        cmd_login()
    elif args.items[0] == "post":
        if len(args.items) < 2:
            ap.error("post 需要一个 markdown 文件，如：python xhs.py post article.md")
        cmd_post(args.items[1], args.img, args.headless, args.dry_run)
    else:
        cmd_fetch(args.items, args.headless)


if __name__ == "__main__":
    main()
