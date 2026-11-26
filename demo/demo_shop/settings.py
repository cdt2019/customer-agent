"""配置，全部来自环境变量。本机的值放 demo/.env。"""

import os
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).parents[1]
load_dotenv(ROOT / ".env")

AGENT_URL = os.environ.get("AGENT_URL", "http://127.0.0.1:8000")
AGENT_KEY = os.environ.get("AGENT_KEY", "")  # 客服服务的服务密钥
INDEX_ID = int(os.environ.get("INDEX_ID", 1))  # 聊天窗用哪个索引版本
SHOP_API_KEY = os.environ.get("SHOP_API_KEY", "")  # 客服服务调店铺接口时带的密钥
TOKEN_SECRET = os.environ.get("TOKEN_SECRET", "")  # 签访客令牌
TOKEN_MINUTES = int(os.environ.get("TOKEN_MINUTES", 10))
DATA_DIR = Path(os.environ.get("DATA_DIR", ROOT / "data"))
WIDGET_DIR = Path(os.environ.get("WIDGET_DIR", ROOT.parent / "widget/dist"))
