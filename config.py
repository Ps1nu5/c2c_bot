import os
from dotenv import load_dotenv

load_dotenv()

BOT_TOKEN: str = os.environ["BOT_TOKEN"]
DATABASE_URL: str = os.getenv("DATABASE_URL", "sqlite+aiosqlite:///./data/bot.db")
LOG_LEVEL: str = os.getenv("LOG_LEVEL", "INFO")
HEADLESS: bool = os.getenv("HEADLESS", "true").lower() != "false"

BASE_URL = "https://dashboard.cards2cards.com"
LOGIN_URL = f"{BASE_URL}/login?t=22314268-b9f0-48fd-8901-30419acd2419"
TRADER_URL = f"{BASE_URL}/trader?t=22314268-b9f0-48fd-8901-30419acd2419"
ORDERS_URL = f"{BASE_URL}/trader/orders?from=2026-02-01T00%3A00%3A00%2B03%3A00&status=new&t=22314268-b9f0-48fd-8901-30419acd2419"
ORDERS_BASE_URL = f"{BASE_URL}/trader/orders"

POLL_INTERVAL: float = 0.5
PAGE_LOAD_TIMEOUT: int = 20
ELEMENT_WAIT_TIMEOUT: int = 10
ALERT_WAIT_TIMEOUT: int = 5
