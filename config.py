"""
Модуль конфигурации проекта.
Загружает переменные окружения, пути и список прокси.
"""

import os
from pathlib import Path
from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent
ENV_PATH = BASE_DIR / ".env"

load_dotenv(dotenv_path=ENV_PATH, override=True)

BOT_TOKEN = os.getenv("BOT_TOKEN", "").strip().strip('"').strip("'")
ADMIN_ID = int(os.getenv("ADMIN_ID", "0") or "0")
SCHEDULE_INTERVAL_MINUTES = int(os.getenv("SCHEDULE_INTERVAL_MINUTES", "60") or "60")

DB_PATH = BASE_DIR / "encar_cars.db"
EXPORTS_DIR = BASE_DIR / "exports"
EXPORTS_DIR.mkdir(exist_ok=True)

PROXIES_FILE = BASE_DIR / "proxies.txt"

def load_proxies() -> list[str]:
    """Загружает список прокси из proxies.txt (формат http://user:pass@ip:port или http://ip:port)."""
    if not PROXIES_FILE.exists():
        return []
    with open(PROXIES_FILE, "r", encoding="utf-8") as f:
        proxies = [line.strip() for line in f if line.strip() and not line.startswith("#")]
    return proxies

ENCAR_API_URL = "https://api.encar.com/search/car/list/general"
ENCAR_IMAGE_CDN = "https://ci.encar.com"

DEFAULT_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/129.0.0.0 Safari/537.36"
    ),
    "Referer": "https://www.encar.com/",
    "Accept": "application/json, text/javascript, */*; q=0.01",
}