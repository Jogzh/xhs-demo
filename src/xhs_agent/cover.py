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

# 对比式封面（Before/After VS 分屏，2026-10-12 新增：情绪钩子+视觉冲击）
VS_COVER_HTML = """<!doctype html><html><head><meta charset="utf-8"><style>
  body {{ margin: 0 }}
  #cover {{ position: relative; width: 1080px; height: 1440px; box-sizing: border-box;
    display: flex; flex-direction: column; font-family: "Microsoft YaHei",
    "Segoe UI Emoji", sans-serif; overflow: hidden }}
  .top {{ height: 300px; display: flex; align-items: center; justify-content: center;
    background: #111827; color: #fbbf24; font-size: 62px; font-weight: 700;
    padding: 0 70px; text-align: center; line-height: 1.4 }}
  .split {{ flex: 1; display: flex; position: relative }}
  .side {{ flex: 1; display: flex; flex-direction: column; align-items: center;
    justify-content: center; padding: 40px; text-align: center }}
  .side.left {{ background: #374151; color: #d1d5db }}
  .side.right {{ background: linear-gradient(200deg, #2563eb 0%, #38bdf8 100%);
    color: #fff }}
  .emoji {{ font-size: 150px; line-height: 1.2 }}
  .big {{ font-size: 78px; font-weight: 700; margin: 36px 0 20px; color: inherit }}
  .side.left .big {{ color: #f3f4f6 }}
  .small {{ font-size: 40px; line-height: 1.6; opacity: .9;
    word-break: keep-all; overflow-wrap: anywhere }}
  .vs {{ position: absolute; left: 50%; top: 50%; transform: translate(-50%, -50%);
    width: 170px; height: 170px; border-radius: 50%; background: #fff; color: #ff2442;
    display: flex; align-items: center; justify-content: center; font-size: 72px;
    font-weight: 900; box-shadow: 0 10px 50px rgba(0,0,0,.35);
    border: 8px solid #ff2442; z-index: 2 }}
  .footer {{ position: absolute; bottom: 44px; left: 0; right: 0; text-align: center;
    color: rgba(255,255,255,.75); font-size: 30px; z-index: 2 }}
</style></head><body><div id="cover">
  <div class="top">{top}</div>
  <div class="split">
    <div class="side left">
      <div class="emoji">{l_emoji}</div>
      <div class="big">{l_big}</div>
      <div class="small">{l_small}</div>
    </div>
    <div class="side right">
      <div class="emoji">{r_emoji}</div>
      <div class="big">{r_big}</div>
      <div class="small">{r_small}</div>
    </div>
    <div class="vs">VS</div>
    <div class="footer">{account_tag} · {date}</div>
  </div>
</div></body></html>"""

# 手账便签卡（楷体+荧光笔+胶带贴纸，2026-10-12 新增：真实亲切感）
NOTE_CARD_HTML = """<!doctype html><html><head><meta charset="utf-8"><style>
  body {{ margin: 0 }}
  #card {{ position: relative; width: 1080px; height: 1440px; box-sizing: border-box;
    background: #faf7f0; padding: 90px 80px; font-family: "KaiTi", "楷体",
    "Microsoft YaHei", "Segoe UI Emoji", sans-serif; color: #292524; overflow: hidden }}
  #card::before {{ content: ""; position: absolute; inset: 0;
    background: repeating-linear-gradient(0deg, transparent 0 79px,
    rgba(120, 110, 90, .08) 79px 80px) }}
  h1 {{ position: relative; font-size: 74px; text-align: center; margin: 0 0 30px;
    font-weight: 700 }}
  h1 em {{ font-style: normal; background: linear-gradient(transparent 55%,
    #fde047 55%) }}
  .note {{ position: relative; background: #fff; border-radius: 6px;
    box-shadow: 0 6px 20px rgba(0,0,0,.08); padding: 40px 44px; margin: 44px 0;
    font-size: 44px; line-height: 1.65 }}
  .note::before {{ content: ""; position: absolute; top: -22px; left: 50%;
    transform: translateX(-50%) rotate(-2deg); width: 220px; height: 44px;
    background: rgba(147, 197, 253, .55) }}
  .note .no {{ display: inline-flex; width: 56px; height: 56px; border-radius: 50%;
    background: #2563eb; color: #fff; font-family: "Microsoft YaHei", sans-serif;
    font-size: 34px; align-items: center; justify-content: center; margin-right: 18px }}
  .note b {{ color: #1d4ed8 }}
  .n1 {{ transform: rotate(-1.2deg) }}
  .n2 {{ transform: rotate(0.8deg) }}
  .n3 {{ transform: rotate(-0.6deg) }}
  .n4 {{ transform: rotate(1deg) }}
  .foot {{ position: absolute; bottom: 52px; left: 0; right: 0; text-align: center;
    font-size: 42px; color: #b45309 }}
</style></head><body><div id="card">
  <h1><em>{title}</em></h1>
  {notes}
  <div class="foot">详细步骤看正文 👉</div>
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


def make_vs_cover(ctx, top: str, left: dict, right: dict, out,
                  account_tag: str = "AI 工具实测") -> "Path":
    """对比式（Before/After）封面。left/right: {emoji, big, small}。"""
    html = VS_COVER_HTML.format(
        top=(top or "")[:24],
        l_emoji=left.get("emoji", "😩"), l_big=left.get("big", "")[:6],
        l_small=left.get("small", "")[:30],
        r_emoji=right.get("emoji", "🤖"), r_big=right.get("big", "")[:6],
        r_small=right.get("small", "")[:30],
        account_tag=account_tag, date=datetime.now().strftime("%Y-%m-%d"))
    return render_html(ctx, html, out)


def make_note_card(ctx, title: str, notes: list, out) -> "Path":
    """手账便签卡。notes: [(序号, 富文本)， ...] ≤4 张便签，富文本可含 <b>。"""
    items = []
    for i, (no, text) in enumerate(notes[:4], 1):
        items.append(f'<div class="note n{i}"><span class="no">{no}</span>{text}</div>')
    html = NOTE_CARD_HTML.format(title=(title or "")[:12], notes="".join(items))
    return render_html(ctx, html, out)
