# -*- coding: utf-8 -*-
"""封面/清单卡生成 —— HTML 模板 + Playwright 截图（零额外依赖，避开字体问题）。

在发布所用的同一浏览器上下文里 set_content 渲染，1080x1440 小红书图文比例。
"""
from datetime import datetime

COVER_HTML = """<!doctype html><html><head><meta charset="utf-8"><style>
  body {{ margin: 0 }}
  #cover {{ position: relative; width: 1080px; height: 1440px; box-sizing: border-box;
    background: linear-gradient(160deg, #ff2442 0%, #b3123a 55%, #4d0e2b 100%);
    display: flex; flex-direction: column; justify-content: center; padding: 96px;
    font-family: "Microsoft YaHei", sans-serif; color: #fff }}
  .kicker {{ font-size: 34px; letter-spacing: 10px; opacity: .85; margin-bottom: 44px }}
  .title  {{ font-size: {title_size}px; font-weight: 700; line-height: 1.35 }}
  .title span {{ display: block }}
  .sub    {{ margin-top: 60px; font-size: 42px; opacity: .92; line-height: 1.7 }}
  .footer {{ position: absolute; left: 96px; right: 96px; bottom: 72px; display: flex;
    justify-content: space-between; font-size: 30px; opacity: .7 }}
</style></head><body><div id="cover">
  <div class="kicker">干 货 分 享</div>
  <div class="title">{title_html}</div>
  <div class="sub">{sub}</div>
  <div class="footer"><span>小红书</span><span>{date}</span></div>
</div></body></html>"""

LIST_HTML = """<!doctype html><html><head><meta charset="utf-8"><style>
  body {{ margin: 0 }}
  #card {{ position: relative; width: 1080px; height: 1440px; box-sizing: border-box;
    background: #fffdf5; padding: 72px; font-family: "Microsoft YaHei", sans-serif;
    color: #332c28 }}
  #card::before {{ content: ""; position: absolute; top: 0; left: 0; right: 0; height: 22px;
    background: #e6463c }}
  h1 {{ font-size: 64px; text-align: center; margin: 48px 0 56px; color: #e6463c }}
  .row {{ display: flex; align-items: center; background: #fff; border-radius: 24px;
    padding: 30px 40px; margin-bottom: 26px; font-size: 40px }}
  .row .day {{ color: #e6463c; font-weight: 700; width: 190px; flex: none }}
  .foot {{ position: absolute; bottom: 60px; left: 0; right: 0; text-align: center;
    font-size: 44px; color: #e6463c }}
</style></head><body><div id="card">
  <h1>{title}</h1>
  {rows}
  <div class="foot">细节看正文 👉</div>
</div></body></html>"""


def render_html(ctx, html: str, out) -> "Path":
    """渲染 HTML 并截元素图（等待字体就绪）。ctx: playwright BrowserContext。"""
    from pathlib import Path
    page = ctx.new_page()
    try:
        page.set_content(html)
        page.wait_for_selector("#cover, #card")
        page.wait_for_timeout(500)
        page.locator("#cover, #card").first.screenshot(path=str(out))
    finally:
        page.close()
    return Path(out)


def make_cover(ctx, lines: list, sub: str, out) -> "Path":
    """1080x1440 大字标题卡。lines: 封面大字（1~3 行，每行 ≤8 字）。"""
    lines = [str(l)[:8] for l in (lines or [])][:3] or ["干货分享"]
    # 行数越多字号越小，避免溢出画布
    size = {1: 130, 2: 104, 3: 88}[len(lines)]
    title_html = "".join(f"<span>{l}</span>" for l in lines)
    html = COVER_HTML.format(title_size=size, title_html=title_html,
                             sub=sub[:40] if sub else "", date=datetime.now().strftime("%Y-%m-%d"))
    return render_html(ctx, html, out)


def make_list_card(ctx, title: str, rows: list, out) -> "Path":
    """清单/步骤卡。rows: [(左标签, 内容), ...] ≤8 行。"""
    tr = "".join(f'<div class="row"><span class="day">{a}</span><span>{b}</span></div>'
                 for a, b in rows[:8])
    html = LIST_HTML.format(title=title[:14], rows=tr)
    return render_html(ctx, html, out)
