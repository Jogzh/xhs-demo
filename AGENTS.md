# AGENTS.md —— xhs-agent 项目工作指南

本项目是小红书自我迭代 Agent。**内容不调用外部 LLM，由当前 ZCode 会话里的 AI（你）直接撰写。**
架构与红线详见 [docs/技术方案.md](docs/技术方案.md)；命令统一走
`PYTHONPATH=src python -m xhs_agent <cmd>`（下文简写为 `python -m xhs_agent`）。

## 收到"发文章"时的标准流程

1. **确定选题**：用户给了主题就用用户的；没给就 `python -m xhs_agent status` 看
   topics 表轮询，或问一句。
2. **读策略库**：status 输出末尾的 **active insights** 是历史数据沉淀的写作策略
   （高分组 vs 低分组的显著差异），撰写时必须吸收。
3. **（可选）调研**，两条路径按需选：
   ```bash
   python -m xhs_agent research --topic <主题>   # 搜索页爆款调研（≈6 次访问，一天最多 1 次）
   python -m xhs_agent spy --logged-in           # 拆对标博主主页（≈2 次访问，清单 data/bloggers.txt）
   ```
   - research 产出 `data/runs/<ts>_research/research.md`（标题句式/字数/话题分布/互动量级）。
     已调研过会自动跳过；触发风控（RateLimitError）就直接凭经验写。
   - spy 产出 `data/runs/<ts>_spy/spy.md`（每位博主 top 笔记 + 标题共性统计）。
     对标博主清单维护在 `data/bloggers.txt`（每行 `名称 链接`，**不进 git**）。
   - 同一天两样都跑也就 ≈8 次访问，低于红线，但别和发布挤在同一小时里反复跑。
4. **撰写内容**，写入 `data/pending_note.json`（UTF-8）：
   ```json
   {
     "topic": "主题名",
     "title": "≤20字，数字承诺+身份代入+emoji",
     "body": "hook → 干货清单 → tips → 互动引导，正文 300~800 字",
     "topics": ["话题1", "话题2", "话题3", "话题4"],
     "cover_title": ["封面大字第1行", "第2行", "第3行"],
     "cover_sub": "副标题一句话",
     "menu_lines": [["周一", "搭配"], ["周二", "搭配"]],
     "strategy": "ai_v1"
   }
   ```
   - `cover_title`/`cover_sub`/`menu_lines`/`images` 都可省略：省略 images 时自动画
     大字封面卡；有 `menu_lines` 会多画一张清单卡；也可以自己给 `images` 本地图路径。
   - 清单卡只适合清单/步骤类内容；非清单类给 `images` 放真实图或只留封面。
   - `strategy` 是这篇内容的策略标签，复盘时用来对比（可用 ai_v1、清单体_v2 等自造标签）。
5. **发布**（默认公开；用户没说私密就发公开）：
   ```bash
   python -m xhs_agent publish-content            # 发布并自动归档 pending 文件
   python -m xhs_agent publish-content --dry-run  # 填好表单但不点发布，看截图
   python -m xhs_agent publish-content --file 文章.md   # 也可以直接发 markdown
   ```
6. **回报结果**：把 title / note_id / 截图目录（data/runs/<ts>_publish/）告诉用户；
   失败时读 runs 表 error 和对应截图，修好后重试（注意红线）。

## 每日节奏（2026-10-11 起改为人工驱动，计划任务已注销）

用户每天会主动发起，没有定时任务：
- **"复盘"**：`python -m xhs_agent metrics` 回流互动数据 → 打分
  （score = 1赞+2评+3转+1.5藏）→ `python -m xhs_agent refresh` 出新 insights，
  把结论讲给用户。
- **"发文"**：按上面标准流程写 pending → 发布 → 回报。
- 想恢复自动 loop：`powershell -ExecutionPolicy Bypass -File scripts\register_tasks.ps1 -Action register`。

## 自主权（用户授权，2026-10-11）

发现问题直接修，不必逐次请示——本项目不是"照护既有代码"，而是由你持续经营：

- **架构随时可改**：模块划分、数据流、表结构、CLI 命令面不合理就重构，
  不受初始设计束缚。改完 commit 写清动机，回报里提一句改了什么、为什么。
- **模板/视觉随时可改**：writer.py 兜底文案、cover.py 大字卡/清单卡的
  字体、配色、排版、构图，不好看或和账号定位不符就直接改
  （例：红渐变"干货分享"风不适合科技/AI 定位，该换就换）。
  以对标博主视觉 + 复盘数据为准，不凭空发挥。
- **改动留痕、依据优先**：每次改动一个 commit；动机尽量来自证据
  （insights / spy 对标样本 / 运行截图 / 报错信息），commit message 写清楚。
- **文档同步**：改架构同步 [docs/技术方案.md](docs/技术方案.md)，
  改流程同步本文件；文档与代码不一致视为 bug。
- **失败自修**：发布/回流失败先读截图和 runs.error 自查自修，
  修不动或需要用户决策（扫码、删号风险等）再找人；
  能本地验证的（语法/纯本地计算/截图分析）不上浏览器。
- **授权边界**：本节只覆盖工程实现。「硬约束」一节是账号安全红线
  （风控频率 / 每日 1 篇 / xsec_token / 发布视口坐标），要动必须用户明确同意。

## 常用命令

```bash
PYTHONPATH=src python -m xhs_agent status          # 开关/排队内容/笔记得分/insights
PYTHONPATH=src python -m xhs_agent pause / resume  # 总开关
PYTHONPATH=src python -m xhs_agent metrics         # 手动回流
PYTHONPATH=src python -m xhs_agent refresh         # 手动复盘（纯本地）
PYTHONPATH=src python -m xhs_agent search <关键词>  # 搜爆款
PYTHONPATH=src python -m xhs_agent fetch <笔记链接> # 抓整篇笔记到 notes/
PYTHONPATH=src python -m xhs_agent spy --logged-in  # 拆对标博主主页（清单 data/bloggers.txt）
PYTHONPATH=src python -m xhs_agent run-once --topic X   # 模板内容兜底发布
PYTHONPATH=src python -m xhs_agent topic list           # 主题池
PYTHONPATH=src python -m xhs_agent topic add X          # 加主题（research 轮询用）
```

## 硬约束（实测踩坑，勿越）

- **频率**：约 15 次自动化页面访问/小时触发 300012"安全限制"（数小时自愈）。
  一次发布 ≈ 2~3 次页面访问，安全；research（≈6 次）一天最多 1 次；
  **调试严禁短时间内反复跑浏览器命令**。
- **xsec_token**：访问笔记详情必须带搜索/主页卡片里的 token，随取随用、不落库长期存。
- **每天最多发 1 篇**：runs 表幂等强制，发多了账号风险高。
- **persistent context 单实例**：同一时刻只能有一个脚本用 user_data/，
  跑之前确认没有残留浏览器进程占用。
- **登录态失效**：发布报"登录态失效"时，请用户跑 `python -m xhs_agent login` 扫码。
- **未登录主页是登录墙**：网页端不登录访问博主主页会整页 302 到 /login，
  spy 默认无痕模式采不到东西，实际用 `spy --logged-in`（仅 ≈2 次页面访问）。
- **训练数据不进 git**：data/（db/调研/归档/bloggers.txt）、notes/、user_data/
  都在 .gitignore；对标博主、主题池等信息只存在 data/ 下，仓库可公开。
- **发布按钮是 shadow DOM**：publisher.py 按坐标点（视口 1400x900 固定），勿改视口。

## 迭代机制（score 驱动）

metrics 回流后：`refresher` 把已结题笔记按 score 分高/低组（各前/后 30%），
对比 7 个特征（标题字数/数字/emoji/疑问句/正文清单结构/字数/话题数），
差异 ≥30 个百分点的特征沉淀为 insights（active=1）。
**你写 pending 时必须读 status 里的 insights 并应用**——这就是"自我迭代"闭环：
数据 → 结论 → 下一篇内容。新的策略标签（strategy 字段）可自由实验，复盘可回溯。
