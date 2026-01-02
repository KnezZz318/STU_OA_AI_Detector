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

需配置以下环境变量以确保可以正确登录并进入 OA：

- `WEBVPN_LOGIN_URL`：WebVPN 登录页地址。
- `WEBVPN_USERNAME_SELECTOR`：账号输入框选择器。
- `WEBVPN_PASSWORD_SELECTOR`：密码输入框选择器。
- `WEBVPN_SUBMIT_SELECTOR`：登录提交按钮选择器。
- `WEBVPN_OTP_DIALOG_SELECTOR`：动态口令弹窗选择器。
- `WEBVPN_OTP_INPUT_SELECTOR`：动态口令输入框选择器。
- `WEBVPN_OTP_SUBMIT_SELECTOR`：动态口令确认按钮选择器。
- `OA_ENTRY_URL`：WebVPN 下 OA 入口地址。
- `OA_READY_SELECTOR`：OA 首页加载完成的标识选择器。
- `OA_LIST_ROW_SELECTOR`：通知列表行选择器。
- `OA_TITLE_SELECTOR`：通知标题选择器（相对列表行）。
- `OA_DEPARTMENT_SELECTOR`：发布单位选择器（相对列表行）。
- `OA_DATE_SELECTOR`：日期选择器（相对列表行）。
- `OA_LINK_SELECTOR`：详情链接选择器（相对列表行）。
- `OA_DETAIL_CONTENT_SELECTOR`：详情页正文选择器。
