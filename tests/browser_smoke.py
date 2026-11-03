"""Optional real-browser check: python tests/browser_smoke.py (requires Playwright + Chromium)."""
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import time

import httpx
from playwright.sync_api import sync_playwright, expect

ROOT = Path(__file__).resolve().parent.parent


def run():
    with tempfile.TemporaryDirectory() as temp:
        server = subprocess.Popen(
            [sys.executable, "-m", "uvicorn", "backend.app:app", "--host", "127.0.0.1", "--port", "8765"],
            cwd=ROOT, env={**os.environ, "BOB_DB_PATH": str(Path(temp) / "test.sqlite3")},
            stdout=subprocess.DEVNULL, stderr=subprocess.PIPE,
        )
        try:
            with httpx.Client(trust_env=False) as client:
                for _ in range(100):
                    if server.poll() is not None:
                        raise RuntimeError(server.stderr.read().decode())
                    try:
                        if client.get("http://127.0.0.1:8765/api/health").is_success:
                            break
                    except httpx.ConnectError:
                        pass
                    time.sleep(.1)
                else:
                    raise RuntimeError("Server startup timed out")
            with sync_playwright() as p:
                browser = p.chromium.launch(executable_path=shutil.which("chromium"), args=["--no-sandbox"])
                page = browser.new_page(viewport={"width": 1440, "height": 1050})
                errors = []
                page.on("pageerror", lambda e: errors.append(str(e)))
                page.on("console", lambda m: errors.append(m.text) if m.type == "error" else None)
                page.goto("http://127.0.0.1:8765")
                expect(page.get_by_role("heading", name="你好，鲍勃。")).to_be_visible()
                page.get_by_role("button", name="使用虚构记忆，开启七天实验").click()
                expect(page.get_by_text("0 / 7 天", exact=True)).to_be_visible()
                page.get_by_role("button", name="01 全力推进项目").click()
                expect(page.get_by_text("1 / 7 天", exact=True)).to_be_visible()
                page.screenshot(path="/tmp/bob-world-desktop.png", full_page=True)
                page.get_by_role("button", name="模拟到第七天 →").click()
                expect(page.get_by_text("7 / 7 天", exact=True)).to_be_visible()
                page.get_by_role("button", name="查看 / 分岔 ↗").last.click()
                expect(page.get_by_role("dialog")).to_be_visible()
                page.get_by_role("button", name="回到这次选择，创建另一条路 ↗").click()
                page.get_by_label("分支名称").fill("从第一天重新开始")
                page.get_by_role("button", name="创建平行分支 →").click()
                expect(page.get_by_role("heading", name="从第一天重新开始")).to_be_visible()
                expect(page.get_by_text("0 / 7 天", exact=True)).to_be_visible()
                page.get_by_role("button", name="记忆档案").click()
                page.get_by_role("button", name="＋ 导入记忆").click()
                page.get_by_label("记忆 JSON").fill("broken json")
                page.get_by_role("button", name="导入到本地记忆库").click()
                expect(page.get_by_role("alert")).to_contain_text("JSON 格式有误")
                data = {"memories": [{"source": "health_assistant", "type": "goal", "content": "<script>测试文本保持纯文本</script>", "observed_at": "2026-11-03", "confidence": 1}]}
                page.get_by_label("记忆 JSON").fill(json.dumps(data, ensure_ascii=False))
                page.get_by_role("button", name="导入到本地记忆库").click()
                expect(page.get_by_text(data["memories"][0]["content"], exact=True)).to_be_visible()
                page.get_by_role("button", name="＋ 开启新分支").click()
                page.get_by_label("分支名称").fill("我的记忆分支")
                page.get_by_label("记忆背景").select_option("imported")
                page.get_by_role("button", name="开启新分支 →").click()
                expect(page.get_by_role("heading", name="我的记忆分支")).to_be_visible()
                page.get_by_role("button", name="平行人生").click()
                page.get_by_role("button", name="⑂ 生成三条七天路径").click()
                expect(page.locator(".result-card")).to_have_count(4)
                expect(page.locator(".chart-line")).to_have_count(4)
                page.screenshot(path="/tmp/bob-world-comparison.png", full_page=True)
                page.get_by_role("button", name="实验记录").click()
                with page.expect_download() as download:
                    page.get_by_role("button", name="导出", exact=True).first.click()
                saved=download.value
                saved.save_as(str(Path(temp)/"export.json"))
                assert len(json.loads((Path(temp)/"export.json").read_text())["events"]) == 7
                page.reload()
                page.get_by_role("button", name="实验记录").click()
                expect(page.locator("tbody tr")).to_have_count(6)
                page.get_by_role("button", name="记忆档案").click()
                page.get_by_role("button", name="删除", exact=True).click()
                page.get_by_role("button", name="确认删除", exact=True).click()
                expect(page.get_by_role("heading", name="还没有导入真实记忆")).to_be_visible()
                page.get_by_role("button", name="世界概览").click()
                page.set_viewport_size({"width":390,"height":844})
                expect(page.get_by_role("heading", name="你好，鲍勃。")).to_be_visible()
                assert page.evaluate("document.documentElement.scrollWidth <= innerWidth"), "Mobile layout overflows"
                page.screenshot(path="/tmp/bob-world-mobile.png", full_page=True)
                page.get_by_role("button", name="✧ 全自动模拟七天").click()
                expect(page.get_by_role("heading", name="鲍勃的全自动人生")).to_be_visible()
                expect(page.get_by_text("7 / 7 天", exact=True)).to_be_visible()
                expect(page.get_by_text("已自主决定 7 天，手动选择 0 天。", exact=False)).to_be_visible()
                page.get_by_role("button", name="查看 / 分岔 ↗").first.click()
                expect(page.get_by_role("heading", name="选择时的候选评分")).to_be_visible()
                expect(page.get_by_role("dialog").locator("tbody tr")).to_have_count(3)
                page.get_by_role("button", name="关闭对话框").click()
                page.screenshot(path="/tmp/bob-world-autopilot.png", full_page=True)
                assert not errors, errors
                browser.close()
                print("PASS: browser workflow, manual/autonomous actions, fork, import/XSS, comparison, export, persistence, deletion, mobile layout, full autopilot and decision scores; no browser errors")
        finally:
            server.terminate()
            server.wait(timeout=10)


if __name__ == "__main__":
    run()
