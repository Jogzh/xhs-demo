# -*- coding: utf-8 -*-
"""封面/清单卡生成 —— HTML 模板 + Playwright 截图（零额外依赖，避开字体问题）。

在浏览器上下文里 set_content 渲染（不访问任何网站），1080x1440 小红书图文比例。
2026-10-12 换科技深色风：账号定位 AI/科技，原红渐变"干货分享"风不符
（依据：对标博主均为 AI 赛道 + AGENTS.md 自主权授权）。
"""
from datetime import datetime

COVER_HTML = """<!doctype html><html><head><meta charset="utf-8"><style>
  body {{ margin: 0 }}
  #cover {{ position: relative; width: 1080px; height: 1440px; box-sizing: border-box;
    background: linear-gradient(165deg, #0a0f1e 0%, #101a30 55%, #0b2338 100%);
    display: flex; flex-direction: column; justify-content: center; padding: 96px;
    font-family: "Microsoft YaHei", sans-serif; color: #fff; overflow: hidden }}
  #cover::before {{ content: ""; position: absolute; top: -260px; right: -220px;
    width: 720px; height: 720px; border-radius: 50%;
    background: radial-gradient(circle, rgba(56,189,248,.28) 0%, rgba(56,189,248,0) 65%) }}
  #cover::after {{ content: ""; position: absolute; bottom: -300px; left: -240px;
    width: 760px; height: 760px; border-radius: 50%;
    background: radial-gradient(circle, rgba(129,140,248,.20) 0%, rgba(129,140,248,0) 65%) }}
  .kicker {{ display: flex; align-items: center; gap: 22px; font-size: 34px;
    letter-spacing: 10px; color: #7dd3fc; margin-bottom: 52px }}
  .kicker::before {{ content: ""; width: 14px; height: 40px; border-radius: 7px;
    background: linear-gradient(180deg, #38bdf8, #818cf8) }}
  .title  {{ font-size: {title_size}px; font-weight: 700; line-height: 1.38;
    text-shadow: 0 6px 40px rgba(0,0,0,.45) }}
  .title span {{ display: block }}
  .sub    {{ margin-top: 64px; font-size: 42px; color: #a7b7cd; line-height: 1.7 }}
  .footer {{ position: absolute; left: 96px; right: 96px; bottom: 72px; display: flex;
    justify-content: space-between; font-size: 30px; color: rgba(255,255,255,.55) }}
</style></head><body><div id="cover">
  <div class="kicker">{kicker}</div>
  <div class="title">{title_html}</div>
  <div class="sub">{sub}</div>
  <div class="footer"><span>{account_tag}</span><span>{date}</span></div>
</div></body></html>"""

LIST_HTML = """<!doctype html><html><head><meta charset="utf-8"><style>
  body {{ margin: 0 }}
  #card {{ position: relative; width: 1080px; height: 1440px; box-sizing: border-box;
    background: #f6f8fc; padding: 72px; font-family: "Microsoft YaHei", sans-serif;
    color: #1e293b }}
  #card::before {{ content: ""; position: absolute; top: 0; left: 0; right: 0; height: 22px;
    background: linear-gradient(90deg, #2563eb, #38bdf8) }}
  h1 {{ font-size: 64px; text-align: center; margin: 48px 0 56px; color: #1d4ed8 }}
  .row {{ display: flex; align-items: center; background: #fff; border-radius: 24px;
    padding: 30px 40px; margin-bottom: 26px; font-size: 40px;
    box-shadow: 0 4px 24px rgba(37,99,235,.08) }}
  .row .day {{ color: #2563eb; font-weight: 700; width: 240px; flex: none }}
  .foot {{ position: absolute; bottom: 60px; left: 0; right: 0; text-align: center;
    font-size: 44px; color: #2563eb }}
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


def make_cover(ctx, lines: list, sub: str, out, kicker: str = "AI 实测",
               account_tag: str = "AI 工具实测") -> "Path":
    """1080x1440 深色科技风大字卡。lines: 封面大字（1~3 行，每行 ≤8 字）。"""
    lines = [str(l)[:8] for l in (lines or [])][:3] or ["干货分享"]
    # 行数越多字号越小，避免溢出画布
    size = {1: 130, 2: 104, 3: 88}[len(lines)]
    title_html = "".join(f"<span>{l}</span>" for l in lines)
    html = COVER_HTML.format(title_size=size, title_html=title_html,
                             sub=sub[:40] if sub else "", kicker=kicker,
                             account_tag=account_tag,
                             date=datetime.now().strftime("%Y-%m-%d"))
    return render_html(ctx, html, out)


def make_list_card(ctx, title: str, rows: list, out) -> "Path":
    """清单/步骤卡。rows: [(左标签, 内容), ...] ≤8 行。"""
    tr = "".join(f'<div class="row"><span class="day">{a}</span><span>{b}</span></div>'
                 for a, b in rows[:8])
    html = LIST_HTML.format(title=title[:14], rows=tr)
    return render_html(ctx, html, out)
