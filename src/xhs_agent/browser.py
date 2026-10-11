# -*- coding: utf-8 -*-
"""统一浏览器层 —— 所有操作共用一个 Playwright persistent context。

登录态存 user_data/（扫码一次永久有效，浏览器自己维护会话，不手抄 cookie）。
注意：persistent context 同一时刻只允许一个进程使用，跑脚本前确认没有残留浏览器。
"""
import time

from playwright.sync_api import sync_playwright

from xhs_agent import USER_DATA

HOME = "https://www.xiaohongshu.com"
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/133.0.0.0 Safari/537.36")
EXT_BY_TYPE = {"image/jpeg": ".jpg", "image/webp": ".webp", "image/png": ".png",
               "image/avif": ".avif", "video/mp4": ".mp4"}


class RateLimitError(RuntimeError):
    """触发小红书 IP 风控（安全限制 300012），应退避数小时再试。"""


class Browser:
    """persistent context 上下文管理器：with Browser() as b: b.page(...)"""

    def __init__(self, headless: bool = False):
        self.headless = headless
        self._pw = None
        self.ctx = None

    def __enter__(self):
        self._pw = sync_playwright().start()
        # 视口固定 1400x900：publisher 的发布按钮按坐标点击依赖这个值
        self.ctx = self._pw.chromium.launch_persistent_context(
            str(USER_DATA),
            headless=self.headless,
            user_agent=UA,
            locale="zh-CN",
            timezone_id="Asia/Shanghai",
            viewport={"width": 1400, "height": 900},
            args=["--disable-blink-features=AutomationControlled"],
            ignore_default_args=["--enable-automation"],
        )
        return self

    def __exit__(self, *exc):
        try:
            if self.ctx:
                self.ctx.close()
        except Exception:
            pass
        try:
            if self._pw:
                self._pw.stop()
        except Exception:
            pass

    # ---------- 页面与状态 ----------

    def new_page(self):
        return self.ctx.new_page()

    def has_login(self) -> bool:
        return any(c["name"] == "web_session" and c["value"]
                   for c in self.ctx.cookies(HOME))

    def user_id(self) -> str | None:
        """从 cookie 取自己的用户 id（persistent context 优势：不用手抄）。"""
        for c in self.ctx.cookies(HOME):
            if c["name"] == "x-user-id" and c["value"]:
                return c["value"].split("#")[0]
        return None

    def check_rate_limit(self, page):
        """所有页面导航后必须调用：检测 300012 安全限制。"""
        try:
            title = page.title()
            body = page.evaluate("() => document.body.innerText.slice(0, 300)") or ""
        except Exception:
            return
        if ("安全限制" in title or "/website-login/error" in page.url
                or "安全限制" in body or "300012" in body):
            raise RateLimitError(
                "触发小红书 IP 风控(300012 安全限制)。请数小时后再试，"
                "并降低访问频率（research 一天最多 1 次，调试勿反复跑）。")

    def goto(self, page, url: str, timeout: int = 60000):
        page.goto(url, wait_until="domcontentloaded", timeout=timeout)
        self.check_rate_limit(page)
        return page

    # ---------- 登录 ----------

    def wait_login(self, timeout_s: int = 300) -> bool:
        """弹出浏览器等用户扫码，登录态写入 user_data/ 后返回 True。"""
        page = self.new_page()
        try:
            page.goto(HOME, wait_until="domcontentloaded")
            print("请在弹出的浏览器窗口里登录小红书（扫码/验证码均可）...")
            deadline = time.time() + timeout_s
            while time.time() < deadline:
                if self.has_login():
                    print("✅ 登录成功！登录态已保存到 ./user_data，以后不用再登。")
                    return True
                time.sleep(2)
            print(f"⌛ 等了 {timeout_s // 60} 分钟还没登录，下次再运行 login 即可。")
            return False
        finally:
            page.close()

    # ---------- 下载 ----------

    def download(self, url: str, stem) -> "Path | None":
        """按响应 Content-Type 补扩展名下载，返回实际写入的文件路径。"""
        from pathlib import Path
        try:
            r = self.ctx.request.get(url, headers={"Referer": HOME + "/"}, timeout=30000)
            if r.ok and r.body():
                ctype = (r.headers.get("content-type") or "").split(";")[0].strip()
                path = Path(stem).with_suffix(EXT_BY_TYPE.get(ctype, ".jpg"))
                path.write_bytes(r.body())
                return path
        except Exception as e:
            print(f"  ⚠️ 下载失败 {url[:60]}...: {e}")
        return None
