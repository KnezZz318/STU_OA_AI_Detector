# STU_OA_AI_Detector

STU-OA 智能监控与 AI 摘要助手的最小可运行原型。

## 快速开始

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --reload
```

访问 `http://127.0.0.1:8000` 将会看到前端页面。API 路径详见 `app/main.py`。

## 环境变量

- `REQUIRE_OTP=1`：需要动态口令（默认）。
- `REQUIRE_OTP=0`：跳过动态口令流程。
