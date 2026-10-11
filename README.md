# xhs-demo

抓取小红书笔记的极简脚本（Playwright + 浏览器登录态）。

## 安装

```bash
pip install -r requirements.txt
python -m playwright install chromium
```

## 使用

```bash
# 1. 首次使用：登录一次（扫码），登录态保存在 ./user_data，之后免登录
python xhs.py login

# 2. 抓取笔记（链接建议用 App 里"复制链接"得到的完整链接，带 xsec_token）
python xhs.py "https://www.xiaohongshu.com/explore/xxxx?xsec_token=yyyy"
```

结果保存在 `notes/<笔记id>/` 下：`note.md`（标题/作者/正文/标签/数据/图片）+ 图片文件；视频笔记会一并下载视频。

支持一次传多个链接；加 `--headless` 可无头运行（不弹窗口，但更容易触发风控/验证码）。
