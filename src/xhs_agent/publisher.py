# -*- coding: utf-8 -*-
"""发布链路 —— 主站发布页 UI 自动化（本项目核心资产，2026-10-11 实测跑通）。

流程: 首页点「发布」开发布页 → 切「上传图文」→ 上传图片 → 填标题/正文
      → (尽力)加话题 → 点发布(坐标) → 处理确认框 → 等成功页 → 抓 note_id
每步截图到 data/runs/<ts>_publish>/。

实测细节（勿随意改）：
- 发布按钮在 shadow DOM 里取不到，按坐标点击（视口在 browser.py 固定 1400x900）；
- 正文用 keyboard.insert_text（fill 对 contenteditable 无效），Esc 关话题联想；
- 有些内容会弹「发布声明」确认框，按文本匹配点掉；
- 从首页顶栏进发布页（而非直链），行为更像真人。
"""
import re
import time
from pathlib import Path

from playwright.sync_api import BrowserContext

from xhs_agent.browser import HOME, RateLimitError
from xhs_agent.cover import make_cover, make_list_card
from xhs_agent.writer import derive_cover_lines

NOTE_ID_RE = re.compile(r"/(?:explore|discovery/item|search_result)/([0-9a-f]{24})")
EMOJI_STRIP_RE = re.compile(r"[\U0001F000-\U0001FAFF\u2600-\u27BF\uFE0F]")


class PublishError(RuntimeError):
    pass


def _shot(page, shots_dir: Path, name: str):
    try:
        page.screenshot(path=str(shots_dir / f"{name}.png"))
    except Exception:
        pass


def _open_publish_page(ctx: BrowserContext):
    """从官网顶栏点「发布」进入发布页（会新开标签页），返回新页面。"""
    home = ctx.new_page()
    home.goto(HOME, wait_until="domcontentloaded")
    home.wait_for_selector("span.channel", timeout=30000)
    with ctx.expect_page(timeout=30000) as pop:
        home.locator("span.channel").filter(has_text="发布").first.click()
    page = pop.value
    page.wait_for_load_state("domcontentloaded")
    home.close()
    return page


def prepare_images(ctx: BrowserContext, content: dict, shots_dir: Path) -> list:
    """解析内容里的图片：给了 images 用之；否则按 cover_title/menu_lines 生成卡片。"""
    paths = [str(Path(p).resolve()) for p in content.get("images", []) if p]
    if paths:
        return paths
    cover_lines = content.get("cover_title") or derive_cover_lines(content["title"])
    cover = make_cover(ctx, cover_lines, content.get("cover_sub", ""),
                       shots_dir / "cover.jpg")
    paths = [str(cover)]
    if content.get("menu_lines"):
        card = make_list_card(ctx, content.get("card_title", "清单（直接抄）"),
                              [tuple(x) for x in content["menu_lines"]],
                              shots_dir / "list_card.jpg")
        paths.append(str(card))
    return paths


def add_topics(page, editor, topics: list) -> list:
    """(尽力) #话题 触发联想下拉并选中；选不中也没关系——网页编辑器对
    `#话题␣` 会自动渲染成话题标签（2026-10 实测），所以最后以正文里
    真实出现的文本为准。返回写入成功的话题。"""
    for tp in (topics or [])[:4]:
        try:
            editor.click()
            page.keyboard.type("#" + tp, delay=30)
            page.wait_for_timeout(1200)
            dropdown = page.locator(
                ".mentionor-item, .topic-item, div[class*='mention'] li").first
            if dropdown.count() and dropdown.is_visible():
                dropdown.click()
                page.wait_for_timeout(500)
            else:
                page.keyboard.type(" ")
        except Exception:
            try:
                page.keyboard.type(" ")
            except Exception:
                pass
    try:
        text = editor.inner_text()
    except Exception:
        text = ""
    return [tp for tp in (topics or [])[:4] if tp in text]


def publish(ctx, content: dict, shots_dir: Path, dry_run: bool = False,
            private: bool = False) -> dict:
    """发布一篇内容 dict（与 pending_note.json 同构），返回 {published, note_id}。"""
    shots_dir = Path(shots_dir)
    shots_dir.mkdir(parents=True, exist_ok=True)
    title = content["title"].strip()[:20]          # 小红书标题限 20 字
    body = content["body"].strip()[:1000]          # 正文限 1000 字

    page = _open_publish_page(ctx)
    try:
        page.wait_for_selector("input[type=file]", state="attached", timeout=30000)
        _shot(page, shots_dir, "01_open")

        # 切到「上传图文」tab（顶栏/侧边栏有同名隐藏项，只点可见的）
        page.evaluate("""() => {
            const els = [...document.querySelectorAll('span,div')].filter(e =>
                e.childElementCount === 0 && e.textContent.trim() === '上传图文' && e.offsetParent);
            if (els.length) els[0].click();
        }""")
        page.wait_for_selector('input[type=file][accept*=".jpg"]',
                               state="attached", timeout=15000)

        images = prepare_images(ctx, content, shots_dir)
        page.set_input_files("input[type=file]", images)
        print(f"[publish] 已上传 {len(images)} 张图片，等待处理...")
        _shot(page, shots_dir, "02_uploaded")

        # 上传后才会出现标题/正文表单
        page.wait_for_selector("input[placeholder*='标题'], .d-title", timeout=60000)
        page.fill("input[placeholder*='标题'], .d-title", title)
        editor = page.locator("[contenteditable=true]").first
        editor.click()
        page.keyboard.insert_text(body)
        page.keyboard.press("Escape")   # 关掉话题联想下拉
        page.wait_for_timeout(1000)
        _shot(page, shots_dir, "03_filled")

        # 关掉「图片可以编辑啦」之类的新手引导弹窗
        tip = page.get_by_role("button", name="我知道了")
        if tip.count() and tip.first.is_visible():
            tip.first.click()
            page.wait_for_timeout(500)

        added = add_topics(page, editor, content.get("topics"))
        if content.get("topics"):
            print(f"[publish] 话题加入 {len(added)}/{len(content['topics'])}: {added}")
        _shot(page, shots_dir, "04_topics")

        if private:
            try:
                priv = page.get_by_text("仅自己可见", exact=True).first
                if priv.count() and priv.is_visible():
                    priv.click()
                    page.wait_for_timeout(400)
                    print("[publish] 已选仅自己可见")
            except Exception:
                print("[publish] 未找到私密选项，按公开处理")

        if dry_run:
            _shot(page, shots_dir, "05_dryrun_stopped")
            print(f"[publish] dry-run：表单已填好未发布，截图在 {shots_dir}")
            return {"published": False, "reason": "dry-run"}

        # 底部「发布」按钮在 shadow DOM 里取不到，按坐标点（视口固定 1400x900）
        page.wait_for_timeout(1500)
        vp = page.viewport_size
        page.mouse.click(int(vp["width"] / 2 + 60), vp["height"] - 45)
        page.wait_for_timeout(2000)
        # 有些内容会弹「发布声明/AI 声明」确认框，有就点确认
        confirm = page.locator("button:visible").filter(
            has_text=re.compile("确认|确定|仍然|继续"))
        if confirm.count():
            confirm.first.click()
            page.wait_for_timeout(2000)
        _shot(page, shots_dir, "06_clicked")

        # 成功标志：跳转 success 页 / 出现「发布成功」；同时抓 note_id
        deadline = time.time() + 60
        while time.time() < deadline:
            try:
                title = page.title()
            except Exception:
                title = ""
            if "安全限制" in title:
                raise RateLimitError("发布过程触发风控")
            if "success" in page.url or page.get_by_text("发布成功").count():
                note_id = _capture_note_id(page)
                _shot(page, shots_dir, "07_success")
                print(f"[publish] 发布成功！note_id={note_id or '未捕获'}")
                return {"published": True, "note_id": note_id, "url": page.url}
            page.wait_for_timeout(1000)
        _shot(page, shots_dir, "07_timeout")
        raise PublishError(
            f"点了发布但 60 秒内没看到成功标志，当前页面：{page.url}（见截图 {shots_dir}）")
    finally:
        page.close()


def _capture_note_id(page) -> str | None:
    """从当前页 URL 和页面链接里抓 24 位 hex 的笔记 id。"""
    m = NOTE_ID_RE.search(page.url or "")
    if m:
        return m.group(1)
    try:
        hrefs = page.evaluate(
            "() => [...document.querySelectorAll('a[href]')].map(a => a.href).join('\\n')")
        m = NOTE_ID_RE.search(hrefs or "")
        if m:
            return m.group(1)
    except Exception:
        pass
    return None
