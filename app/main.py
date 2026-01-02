from __future__ import annotations

import asyncio
import os
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

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
        await simulate_login(payload)
        notices = await simulate_scrape()
        state.update("processing", "正在调用 AI 摘要...")
        state.result_markdown = await simulate_ai_summary(notices)
        state.update("done", "简报已生成")
    except Exception as exc:  # pragma: no cover - generic fallback
        state.update("error", f"任务失败: {exc}")


async def simulate_login(payload: StartRequest) -> None:
    state.update("processing", "正在登录 WebVPN...")
    await asyncio.sleep(0.2)

    if not payload.username or not payload.password:
        raise ValueError("账号和密码不能为空")

    state.update("waiting_otp", "等待动态口令输入...")
    try:
        await asyncio.wait_for(state.otp_event.wait(), timeout=60)
    except asyncio.TimeoutError:
        state.update("error", "动态口令超时")
        raise

    state.update("processing", "登录成功，准备进入 OA...")
    await asyncio.sleep(0.2)


async def simulate_scrape() -> List[Dict[str, Any]]:
    if os.getenv("MOCK_MODE", "0") != "1":
        raise RuntimeError("未配置实际登录与抓取逻辑，请启用 MOCK_MODE=1 进行演示")
    state.update("processing", "正在抓取通知列表...")
    await asyncio.sleep(0.2)

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
