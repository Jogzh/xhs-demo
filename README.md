# xhs-demo —— 小红书自我迭代 Agent

输入主题 → 调研爆款 → AI 撰写并发布笔记 → 互动数据回流打分 → 复盘沉淀策略 →
反哺下一篇。每日自动执行（带总开关），SQLite 落库，全程不手抄 cookie。

- 📄 架构与实测记录：[docs/技术方案.md](docs/技术方案.md)
- 🤖 AI 操作手册：[AGENTS.md](AGENTS.md)（在 ZCode 会话说"发文章"即走标准流程）
- 🔑 核心链路：主站发布页 UI 自动化（`src/xhs_agent/publisher.py`，实测已通）
  + Playwright persistent context 登录态（`user_data/`，扫码一次）

## 快速开始

```bash
pip install -r requirements.txt && playwright install chromium
set PYTHONPATH=src

python -m xhs_agent login             # 1. 首次：扫码登录（登录态存 user_data/，勿删）
python -m xhs_agent search 减脂餐      # 2. 搜爆款（调试/选题用）
python -m xhs_agent research          # 3. 选题调研 → data/runs/<ts>/research.md
python -m xhs_agent publish-content --file 文章.md   # 4. 直接发一篇 markdown
python -m xhs_agent status            # 随时看：开关/排队内容/笔记得分/insights
```

> Git Bash / PowerShell 里环境变量写法：`PYTHONPATH=src python -m xhs_agent ...`。

## 发文章（内容由 ZCode 会话 AI 直接撰写，不接外部 LLM）

对 ZCode 说一句「发文章」——AI 按 [AGENTS.md](AGENTS.md) 流程：
选题 → （可选）调研 → 结合 insights 写 `data/pending_note.json` → `publish-content` 发布。
也可以自己写 markdown 直接 `publish-content --file 文章.md`。

## 每日自动 loop（Windows 计划任务）

| 任务 | 时间 | 动作 |
|---|---|---|
| `xhs-agent-daily-metrics` | 09:05 | 回流互动数据 → 打分 → T+7 结题 → 复盘出 insights |
| `xhs-agent-daily-publish` | 10:30 | **仅当有 AI 排队内容**（data/pending_note.json）时发布，否则跳过 |
| 日志 | — | `data/sched_publish.log`、`data/sched_metrics.log` |

注册（管理员 PowerShell）：`powershell -ExecutionPolicy Bypass -File scripts\register_tasks.ps1 -Action register`

```bash
python -m xhs_agent status     # 开关 / 排队内容 / 已发笔记 / 得分 / insights
python -m xhs_agent pause      # 总开关 → off（定时任务全部跳过）
python -m xhs_agent resume     # 总开关 → on
python -m xhs_agent metrics    # 立即回流一次
python -m xhs_agent refresh    # 立即复盘一次（纯本地，不开浏览器）
```

## ⚠️ 实测红线

1. **IP 风控 300012**：约 15 次自动化页面访问/小时触发"安全限制"，数小时自愈。
   日频在安全线内；**调试勿反复跑**，research 一天 1 次。
2. **xsec_token**：笔记详情必须带搜索/主页卡片里的 token，随取随用。
3. **每日最多发 1 篇**（runs 表幂等强制），发多了账号风险高。
4. **user_data/ 是登录态**：勿删勿并发使用（persistent context 单实例）。
5. 发布前可 `--dry-run` 检查表单截图。

> 仅供个人学习研究。请对自己的账号和内容负责。
