from __future__ import annotations

import asyncio
import os
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

from playwright.async_api import TimeoutError as PlaywrightTimeoutError
from playwright.async_api import async_playwright

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field


class StartRequest(BaseModel):
    username: str = Field(..., min_length=1)
    password: str = Field(..., min_length=1)


class OtpRequest(BaseModel):
    otp: str = Field(..., min_length=4, max_length=12)


@dataclass
class TaskState:
    status: str = "idle"
    msg: str = "等待任务启动"
    result_markdown: str = ""
    last_update: datetime = field(default_factory=datetime.utcnow)
    otp_event: asyncio.Event = field(default_factory=asyncio.Event)
    otp_value: Optional[str] = None
    task: Optional[asyncio.Task] = None

    def update(self, status: str, msg: str) -> None:
        self.status = status
        self.msg = msg
        self.last_update = datetime.utcnow()


app = FastAPI(title="STU-OA Monitor API")
state = TaskState()
app.mount("/static", StaticFiles(directory="static"), name="static")


@app.get("/")
async def index() -> FileResponse:
    return FileResponse("static/index.html")


@app.post("/api/start")
async def start_task(payload: StartRequest) -> Dict[str, str]:
    if state.task and not state.task.done():
        raise HTTPException(status_code=409, detail="已有任务在运行")

    state.otp_event = asyncio.Event()
    state.otp_value = None
    state.result_markdown = ""
    state.update("processing", "正在初始化任务...")

    state.task = asyncio.create_task(run_job(payload))
    return {"status": state.status, "msg": state.msg}


@app.get("/api/status")
async def get_status() -> Dict[str, str]:
    return {"status": state.status, "msg": state.msg}


@app.post("/api/otp")
async def submit_otp(payload: OtpRequest) -> Dict[str, str]:
    if state.status != "waiting_otp":
        raise HTTPException(status_code=400, detail="当前不需要口令")

    state.otp_value = payload.otp
    state.otp_event.set()
    state.update("processing", "已收到口令，继续处理...")
    return {"status": state.status, "msg": state.msg}


@app.get("/api/result")
async def get_result() -> Dict[str, str]:
    if state.status != "done":
        raise HTTPException(status_code=404, detail="结果尚未生成")
    return {"markdown": state.result_markdown}


async def run_job(payload: StartRequest) -> None:
    try:
        async with async_playwright() as playwright:
            browser = await playwright.chromium.launch(headless=True)
            context = await browser.new_context()
            page = await context.new_page()
            await login_and_enter_oa(page, payload)
            notices = await scrape_notices(page)
            state.update("processing", "正在调用 AI 摘要...")
            state.result_markdown = await simulate_ai_summary(notices)
            state.update("done", "简报已生成")
            await context.close()
            await browser.close()
    except Exception as exc:  # pragma: no cover - generic fallback
        state.update("error", f"任务失败: {exc}")


def get_env(name: str, default: Optional[str] = None) -> str:
    value = os.getenv(name, default)
    if value is None:
        raise RuntimeError(f"缺少环境变量: {name}")
    return value


async def login_and_enter_oa(page: Any, payload: StartRequest) -> None:
    state.update("processing", "正在登录 WebVPN...")

    login_url = get_env("WEBVPN_LOGIN_URL")
    username_selector = get_env("WEBVPN_USERNAME_SELECTOR")
    password_selector = get_env("WEBVPN_PASSWORD_SELECTOR")
    submit_selector = get_env("WEBVPN_SUBMIT_SELECTOR")
    otp_dialog_selector = get_env("WEBVPN_OTP_DIALOG_SELECTOR")
    otp_input_selector = get_env("WEBVPN_OTP_INPUT_SELECTOR")
    otp_submit_selector = get_env("WEBVPN_OTP_SUBMIT_SELECTOR")
    oa_entry_url = get_env("OA_ENTRY_URL")
    oa_ready_selector = get_env("OA_READY_SELECTOR")

    await page.goto(login_url, wait_until="domcontentloaded")
    await page.fill(username_selector, payload.username)
    await page.fill(password_selector, payload.password)
    await page.click(submit_selector)

    try:
        await page.wait_for_selector(otp_dialog_selector, timeout=8000)
    except PlaywrightTimeoutError as exc:
        raise RuntimeError("未检测到口令输入窗口，请检查选择器") from exc

    state.update("waiting_otp", "等待动态口令输入...")
    try:
        await asyncio.wait_for(state.otp_event.wait(), timeout=60)
    except asyncio.TimeoutError as exc:
        state.update("error", "动态口令超时")
        raise exc

    await page.fill(otp_input_selector, state.otp_value or "")
    await page.click(otp_submit_selector)

    state.update("processing", "正在进入 OA 系统...")
    await page.goto(oa_entry_url, wait_until="domcontentloaded")
    try:
        await page.wait_for_selector(oa_ready_selector, timeout=15000)
    except PlaywrightTimeoutError as exc:
        raise RuntimeError("OA 页面未加载成功，请检查入口地址或选择器") from exc


async def scrape_notices(page: Any) -> List[Dict[str, Any]]:
    state.update("processing", "正在抓取通知列表...")
    list_row_selector = get_env("OA_LIST_ROW_SELECTOR")
    title_selector = get_env("OA_TITLE_SELECTOR")
    department_selector = get_env("OA_DEPARTMENT_SELECTOR")
    date_selector = get_env("OA_DATE_SELECTOR")
    link_selector = get_env("OA_LINK_SELECTOR")
    detail_content_selector = get_env("OA_DETAIL_CONTENT_SELECTOR")

    await page.wait_for_selector(list_row_selector, timeout=15000)
    rows = await page.query_selector_all(list_row_selector)
    cutoff_date = datetime.utcnow().date() - timedelta(days=30)

    metadata: List[Dict[str, Any]] = []
    for row in rows:
        title_el = await row.query_selector(title_selector)
        department_el = await row.query_selector(department_selector)
        date_el = await row.query_selector(date_selector)
        link_el = await row.query_selector(link_selector)
        if not all([title_el, department_el, date_el, link_el]):
            raise RuntimeError("通知列表选择器不完整，请检查配置")

        title = (await title_el.inner_text()).strip()
        department = (await department_el.inner_text()).strip()
        date_text = (await date_el.inner_text()).strip()
        link = await link_el.get_attribute("href")
        if not link:
            continue

        try:
            parsed_date = datetime.fromisoformat(date_text).date()
        except ValueError:
            parsed_date = datetime.strptime(date_text, "%Y-%m-%d").date()

        if parsed_date < cutoff_date:
            break

        metadata.append(
            {
                "title": title,
                "department": department,
                "date": parsed_date,
                "link": link,
            }
        )

    items: List[Dict[str, Any]] = []
    for entry in metadata:
        await page.goto(entry["link"], wait_until="domcontentloaded")
        await page.wait_for_selector(detail_content_selector, timeout=15000)
        content = await page.inner_text(detail_content_selector)
        items.append(
            {
                "title": entry["title"],
                "department": entry["department"],
                "date": str(entry["date"]),
                "content": " ".join(content.split()),
            }
        )
        state.update("processing", f"已读取 {len(items)} 条通知详情...")

    if not items:
        raise RuntimeError("未抓取到任何通知，请检查选择器配置")
    return items

    now = datetime.utcnow().date()
    sample_items = [
        {
            "title": "关于期末考试安排的通知",
            "department": "教务处",
            "date": str(now - timedelta(days=7)),
            "content": "请各学院于本月完成期末考试安排上报。",
        },
        {
            "title": "校园讲座：AI 与教育",
            "department": "学术处",
            "date": str(now - timedelta(days=3)),
            "content": "地点图书馆报告厅，欢迎师生参加。",
        },
    ]
    state.update("processing", "正在读取详情页...")
    await asyncio.sleep(0.2)
    return sample_items


async def simulate_ai_summary(items: List[Dict[str, Any]]) -> str:
    lines = ["# 本月 OA 重点摘要", "", "## 重要教务"]
    for item in items:
        lines.append(
            f"- **{item['title']}**（{item['department']} / {item['date']}）："
            f"{item['content']}"
        )
    lines.append("\n## 其他\n- 暂无")
    await asyncio.sleep(0.2)
    return "\n".join(lines)
