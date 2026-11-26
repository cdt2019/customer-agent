"""运行配置：全部来自环境变量，默认值是本机开发用的。"""

import json
import os
from pathlib import Path
from zoneinfo import ZoneInfo

from dotenv import load_dotenv

ROOT = Path(__file__).parents[3]
load_dotenv(ROOT / "server/.env")  # 每台机器自己的路径和密钥放这里，不进版本管理

DATABASE_URL = os.environ.get("DATABASE_URL", "postgresql+psycopg://customer_agent:customer_agent@localhost/customer_agent")
QDRANT_URL = os.environ.get("QDRANT_URL", "http://127.0.0.1:6333")
QDRANT_API_KEY = os.environ.get("QDRANT_API_KEY") or None  # Qdrant 设了访问密钥时填
MODELS_DIR = Path(os.environ.get("MODELS_DIR", ROOT / "var/models"))
HF_ENDPOINT = os.environ.get("HF_ENDPOINT", "https://huggingface.co")  # 下模型从哪里下，可以换成镜像
HF_HOME = Path(os.environ.get("HF_HOME", ROOT / "var/hf"))  # Docling 的模型
UPLOADS_DIR = Path(os.environ.get("UPLOADS_DIR", ROOT / "var/uploads"))
IMAGES_DIR = Path(os.environ.get("IMAGES_DIR", ROOT / "var/images"))  # 买家在聊天里发的图，随聊天记录 90 天清掉
EVALS_DIR = Path(os.environ.get("EVALS_DIR", ROOT / "evals"))
TIMEZONE = ZoneInfo(os.environ.get("TIMEZONE", "Asia/Shanghai"))  # 业务时区：按哪里的零点算「今天」（每天的限额、统计）。库里的时间都带时区，跟它无关

# 管理后台的账号；没配密码时后台接口不开放
ADMIN_USER = os.environ.get("ADMIN_USER", "admin")
ADMIN_PASSWORD = os.environ.get("ADMIN_PASSWORD", "")
ADMIN_COOKIE_SECURE = os.environ.get("ADMIN_COOKIE_SECURE", "1") != "0"  # 默认只走 HTTPS（浏览器对 localhost 也认）；没有 HTTPS 的环境设 0

# 接入方调对话接口用的密钥；没配时对话接口不开放
SERVICE_API_KEY = os.environ.get("SERVICE_API_KEY", "")
# Telegram 渠道（docs/10）：配了令牌才启用
TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_INDEX_ID = int(os.environ.get("TELEGRAM_INDEX_ID") or 0)  # 用哪个索引回答
TELEGRAM_PROXY = os.environ.get("TELEGRAM_PROXY") or None  # 连 Telegram 要走的代理；线上直连不配
SHOP_URL = os.environ.get("SHOP_URL", "http://127.0.0.1:8100")  # 接入方的店铺接口（技术方案 §5.2）
SHOP_API_KEY = os.environ.get("SHOP_API_KEY", "")

# 回答用的模型：任何兼容 OpenAI 接口的服务。密钥只从环境变量读。
LLM_BASE_URL = os.environ.get("LLM_BASE_URL", "https://api.deepseek.com")
LLM_MODEL = os.environ.get("LLM_MODEL", "deepseek-flash")
# 每次请求额外带上的参数（JSON），按供应商填。DeepSeek 默认会先「思考」，客服用不着，关掉：更快、输出少三倍左右
LLM_EXTRA_BODY = json.loads(os.environ.get("LLM_EXTRA_BODY", '{"thinking": {"type": "disabled"}}'))
LLM_API_KEY = os.environ.get("LLM_API_KEY") or os.environ.get("DEEPSEEK_API_KEY", "")
