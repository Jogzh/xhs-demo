# AGENTS.md —— xhs-agent 项目工作指南

本项目是小红书自我迭代 Agent。**内容不调用外部 LLM，由当前 ZCode 会话里的 AI（你）直接撰写。**
架构与红线详见 [docs/技术方案.md](docs/技术方案.md)；命令统一走
`PYTHONPATH=src python -m xhs_agent <cmd>`（下文简写为 `python -m xhs_agent`）。

> **⚠️ 当前状态（2026-10-12 起）：账号限流观察期 + 项目已重置重新开始。**
> 账号被平台两次行为警告＋首篇笔记被封＋第二篇（手动发的）疑似限流。
> 处置：**停更养号 3~7 天**（期间正常人工浏览互动，不发笔记）；
> **登录态自动化全部禁止**（账号锁 on），发布永久改用户手动；
> 完整限流规则见 [docs/限流规避.md](docs/限流规避.md)（硬约束的一部分，写内容前必读）。
> 下文涉及登录态的命令（research/spy --logged-in/publish 等）在锁开着时一律不可用。

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
5. **发布（风控观察期：改用户手动）**——AI 只产出图片和文本存本地，用户自己去 App 发：
   ```bash
   python -m xhs_agent render-images   # 离线出图 + 发文文本，输出 data/runs/<ts>_manual/
   ```
   把该目录里的 `cover.jpg`/`list_card.jpg`（按顺序）和 `发文文本.txt`（标题/正文/话题
   可直接复制）交给用户手动发布；用户报回 note_id 后补录入库。
   （登录态自动发布 `publish-content` 已被账号锁封死，恢复须用户明确同意 unlock-account。）
6. **回报结果**：把内容目录（data/runs/<ts>_manual/）告诉用户；用户手动发布后若报了
   数据/链接，按下面"复盘"一节补录。

## 每日节奏（2026-10-11 起改为人工驱动，计划任务已注销）

用户每天会主动发起，没有定时任务：
- **"复盘"（风控期路径）**：登录态被锁，`metrics` 默认路径不可用。依次尝试：
  ① `python -m xhs_agent metrics --incognito`——无痕访问自己主页
  （链接存 `data/my_profile.txt`，**不进 git**）；**已知是登录墙，大概率采不到**。
  ② 请用户报互动数（赞/藏/评/转），或给笔记分享链接，无痕 `fetch` 补录后
  写 metrics 表打分。之后 `refresh` 出新 insights，把结论讲给用户。
- **"发文"**：按上面标准流程写 pending → `render-images` 出图 → 用户手动发布 → 回报。
- 想恢复自动 loop：先要用户同意 `unlock-account`，再
  `powershell -ExecutionPolicy Bypass -File scripts\register_tasks.ps1 -Action register`。

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
PYTHONPATH=src python -m xhs_agent metrics --incognito # 无痕回流（不碰账号；主页是登录墙，见硬约束）
PYTHONPATH=src python -m xhs_agent refresh         # 手动复盘（纯本地）
PYTHONPATH=src python -m xhs_agent render-images   # 离线出图+发文文本（手动发布用，不访问小红书）
PYTHONPATH=src python -m xhs_agent lock-account / unlock-account  # 账号锁（风控期登录态全禁）
PYTHONPATH=src python -m xhs_agent search <关键词>  # 搜爆款（需登录态，锁开时不可用）
PYTHONPATH=src python -m xhs_agent fetch <笔记链接> # 抓整篇笔记到 notes/
PYTHONPATH=src python -m xhs_agent spy --logged-in  # 拆对标博主主页（清单 data/bloggers.txt；需登录态）
PYTHONPATH=src python -m xhs_agent run-once --topic X   # 模板内容兜底发布（需登录态）
PYTHONPATH=src python -m xhs_agent topic list           # 主题池
PYTHONPATH=src python -m xhs_agent topic add X          # 加主题（research 轮询用）
```

## 硬约束（实测踩坑+平台规则，勿越）

**完整限流规则与出处见 [docs/限流规避.md](docs/限流规避.md)，以下为最高优先级摘要：**

- **🔥 风控观察期（2026-10-12 起）**：账号被平台两次行为警告，首篇笔记因「AI 托管」
  叙事被封禁，第二篇疑似限流。**停更养号 3~7 天**；**一切登录态（user_data/）操作
  禁止**——账号锁 `account_lock=on` 在 Browser 层强制。恢复登录态操作必须用户明确
  同意（`unlock-account`）。**登录态自动发布永久放弃**（平台对"云端工具托管批量发布"
  直接封号，已处置 42 万账号）。
- **内容红线**（insights 表有同款，写 pending 时 status 会显示）：
  ① 严禁「AI 托管/自动运营账号」叙事；② 不虚构亲身经历——写"实测"必须真测过，
  不编"我上周/昨天"时间线，优先教程/清单框架；③ 措辞禁令：绝对化用语/夸大功效/
  诱导互动/拉踩/站外导流/敏感词。
- **发布纪律（用户手动发）**：一次到位，**发布后不改笔记**（二次修改→重审→大概率
  限流）、不删了重发、一天最多 1 条；遇「AI 声明」弹窗如实勾选（贴标不限流，
  不标限分发）。
- **频率**：约 15 次自动化页面访问/小时触发 300012"安全限制"（数小时自愈）。
  research（≈6 次）一天最多 1 次；**调试严禁短时间内反复跑浏览器命令**。
  教训：2026-10-11 曾 10 分钟内连跑 spy×2＋publish，机器节奏是行为检测重点。
- **xsec_token**：访问笔记详情必须带搜索/主页卡片里的 token，随取随用、不落库长期存。
- **每天最多发 1 篇**：runs 表幂等强制，发多了账号风险高。
- **persistent context 单实例**：同一时刻只能有一个脚本用 user_data/，
  跑之前确认没有残留浏览器进程占用。
- **未登录主页是登录墙**：网页端不登录访问任何博主主页（包括自己的，
  `data/my_profile.txt`）会整页 302 到 /login，无痕采不到东西。
- **训练数据不进 git**：data/（db/调研/归档/bloggers.txt/my_profile.txt）、notes/、
  user_data/ 都在 .gitignore；对标博主、主题池、主页链接等信息只存在 data/ 下，
  仓库可公开。
- **发布按钮是 shadow DOM**：publisher.py 按坐标点（视口 1400x900 固定），勿改视口。

### 内容自检清单（写完 pending、交付用户前逐项过）

1. 标题/正文/封面/话题里没有任何"AI 托管/AI 自动运营"表述？
2. 没有"我上周实测/我昨天用了"这类无法证实的经历时间线？（教程/清单框架优先）
3. 无绝对化用语（最/第一/国家级）、无功效承诺、无"求赞求关注"式诱导？
4. 无微信号/链接/二维码等站外导流，无敏感词？
5. 正文 ≥300 字 ≤1000 字、标题 ≤20 字、话题 4 个、图片 1080×1440？
6. 提醒用户：发布时如弹「AI 声明」按实际情况勾选，发布后不要修改笔记。

## 迭代机制（score 驱动）

metrics 回流后：`refresher` 把已结题笔记按 score 分高/低组（各前/后 30%），
对比 7 个特征（标题字数/数字/emoji/疑问句/正文清单结构/字数/话题数），
差异 ≥30 个百分点的特征沉淀为 insights（active=1）。
**你写 pending 时必须读 status 里的 insights 并应用**——这就是"自我迭代"闭环：
数据 → 结论 → 下一篇内容。新的策略标签（strategy 字段）可自由实验，复盘可回溯。
