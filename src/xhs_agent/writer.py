# -*- coding: utf-8 -*-
"""内容生成兜底 —— 无 AI 排队内容时 run-once 用模板（不接外部 LLM）。

主路径是 ZCode 会话 AI 按 AGENTS.md 写 data/pending_note.json；
本模块只是"没排队内容又想保持日更"的兜底。结构依据爆款共性：
标题 = 数字承诺 + 身份代入 + emoji（≤20 字）；正文 = hook → 干货清单 → tips → 互动引导。
"""
import random
import re

TEMPLATES = {
    "上班族减脂餐": {
        "title": "打工人带饭一周不重样🍱同事追着要菜谱",
        "body": (
            "带饭一个月，省了600+，体重还轻了3斤🔥\n"
            "关键是同事天天追着问我菜谱，今天一次说清楚👇\n\n"
            "📌我的备餐逻辑（周末1小时搞定5天）\n"
            "① 周日集中处理蛋白质：鸡胸肉/虾仁/牛肉分装腌制\n"
            "② 杂粮饭一次煮5盒放冷冻，吃前微波2分钟\n"
            "③ 蔬菜当天早上快炒，保持口感不发黄\n\n"
            "🍱一周搭配（直接抄作业）\n"
            "周一：香煎鸡胸肉+蒜蓉西兰花+杂粮饭\n"
            "周二：滑蛋虾仁+凉拌青瓜+杂粮饭\n"
            "周三：番茄牛肉+水煮菜心+杂粮饭\n"
            "周四：香煎三文鱼+芦笋+藜麦饭\n"
            "周五：彩椒炒牛肉+白灼生菜+杂粮饭\n\n"
            "💡打工人Tips\n"
            "· 带汤汁的菜单独装小盒，不然饭会泡烂\n"
            "· 鸡胸肉煮完泡冰水再冷藏，嫩到不像鸡胸\n"
            "· 前一晚放冷藏，早上直接拿走，0操作\n\n"
            "你们明天带什么饭？评论区交换灵感👇\n"
        ),
        "topics": ["减脂餐", "上班族带饭", "工作日午餐", "带饭日记"],
        "cover_title": ["打工人带饭", "一周不重样"],
        "cover_sub": "省钱 600+ · 轻了 3 斤 · 周末 1 小时备齐 5 天",
        "menu_lines": [("周一", "香煎鸡胸+蒜蓉西兰花+杂粮饭"), ("周二", "滑蛋虾仁+凉拌青瓜"),
                       ("周三", "番茄牛肉+水煮菜心"), ("周四", "香煎三文鱼+芦笋+藜麦饭"),
                       ("周五", "彩椒炒牛肉+白灼生菜")],
    },
    "通用": {
        "title": "普通人坚持的第{N}天｜变化真的肉眼可见",
        "body": (
            "坚持到第{N}天，最明显的变化是👇\n\n"
            "📌3 个立刻能抄的方法\n"
            "① 先从每天 10 分钟开始，不贪多\n"
            "② 固定时间固定地点，减少决策消耗\n"
            "③ 记录打卡，可视化进度才是持续的动力\n\n"
            "💡避坑提醒\n"
            "· 完美主义是坚持的大敌，断了就续上，别自责\n"
            "· 找同频伙伴互相监督，成功率翻倍\n\n"
            "你们坚持最久的一件事是什么？评论区聊聊👇"
        ),
        "topics": ["自律", "成长记录", "坚持打卡"],
        "cover_title": ["普通人坚持", "第 {N} 天"],
        "cover_sub": "每天进步一点点，时间会给出答案",
    },
}


def generate(topic: str) -> dict:
    """模板生成内容 dict（与 pending_note.json 同构）。"""
    tpl = TEMPLATES.get(topic) or TEMPLATES["通用"]
    n = random.randint(7, 30)
    content = {"topic": topic, "strategy": "template_v1"}
    for k, v in tpl.items():
        content[k] = (v.replace("{N}", str(n)) if isinstance(v, str)
                      else [x.replace("{N}", str(n)) if isinstance(x, str) else x for x in v])
    return content


def derive_cover_lines(title: str) -> list:
    """没给 cover_title 时，把标题切成 2~3 行大字（每行 ≤8 字）。"""
    t = re.sub(r"[\U0001F000-\U0001FAFF\u2600-\u27BF\uFE0F#\|]", "", title.replace("｜", "，"))
    parts = [p for p in re.split(r"[，。！？\s]+", t) if p]
    lines = []
    for p in parts:
        while p and len(lines) < 3:
            lines.append(p[:8])
            p = p[8:]
    return (lines or [title[:8]])[:3]


def from_markdown(path) -> dict:
    """从 markdown 取标题（第一个 # 行）和正文（去掉标题行/图片行），拼内容 dict。"""
    from pathlib import Path
    text = Path(path).read_text(encoding="utf-8")
    lines = text.splitlines()
    title = next((l.lstrip("# ").strip() for l in lines if l.startswith("# ")), "")
    body = "\n".join(l for l in lines
                     if not l.startswith("# ") and not l.startswith("!["))
    return {"topic": "markdown", "strategy": "md_v1",
            "title": title, "body": body.strip(),
            "topics": [], "cover_title": derive_cover_lines(title)}
