"""
Асинхронный модуль парсинга Encar.com.
Поддерживает конкурентные запросы, ротацию прокси и Smart Upsert в БД.
"""

import asyncio
import itertools
import logging
from dataclasses import dataclass
from typing import Any
import httpx

from config import ENCAR_API_URL, ENCAR_IMAGE_CDN, DEFAULT_HEADERS, load_proxies
from database import upsert_car, upsert_cars_batch

logger = logging.getLogger(__name__)


@dataclass
class ParserState:
    is_running: bool = False
    stop_requested: bool = False
    current_page: int = 0
    total_parsed: int = 0
    last_error: str | None = None


state = ParserState()


class EncarParser:
    def __init__(self, concurrency_limit: int = 5, page_size: int = 20):
        self.concurrency_limit = concurrency_limit
        self.page_size = page_size
        self.semaphore = asyncio.Semaphore(concurrency_limit)
        
        # Настройка ротации прокси
        self.raw_proxies = load_proxies()
        if self.raw_proxies:
            self.proxy_pool = itertools.cycle(self.raw_proxies)
            logger.info(f"Загружен пул прокси: {len(self.raw_proxies)} шт.")
        else:
            self.proxy_pool = None
            logger.info("Прокси не заданы (proxies.txt пуст). Работа в прямом режиме.")

    def _get_next_proxy(self) -> str | None:
        if self.proxy_pool:
            return next(self.proxy_pool)
        return None

    def _extract_photo_urls(self, raw_photos: Any) -> list[str]:
        if not raw_photos or not isinstance(raw_photos, list):
            return []
        urls = []
        for p in raw_photos:
            if isinstance(p, dict) and "location" in p:
                urls.append(f"{ENCAR_IMAGE_CDN}{p['location']}")
            elif isinstance(p, str):
                path = p if p.startswith("/") else f"/{p}"
                urls.append(f"{ENCAR_IMAGE_CDN}{path}")
        return urls

    async def fetch_page(self, page_index: int) -> list[dict[str, Any]]:
        if state.stop_requested:
            return []

        start_index = page_index * self.page_size
        params = {
            "count": "true",
            "q": "(And.Hidden.N._.CarType.A.)",
            "sr": f"|ModifiedDate|{start_index}|{self.page_size}",
        }

        current_proxy = self._get_next_proxy()

        async with self.semaphore:
            transport = None
            if current_proxy:
                transport = httpx.AsyncHTTPTransport(proxy=current_proxy)

            try:
                async with httpx.AsyncClient(
                    headers=DEFAULT_HEADERS,
                    transport=transport,
                    timeout=15.0,
                    follow_redirects=True,
                ) as client:
                    resp = await client.get(ENCAR_API_URL, params=params)
                    resp.raise_for_status()
                    data = resp.json()
            except Exception as e:
                proxy_info = f" (через прокси {current_proxy})" if current_proxy else ""
                logger.error(f"Ошибка запроса страницы {page_index + 1}{proxy_info}: {e}")
                state.last_error = f"Стр {page_index + 1}: {str(e)[:50]}"
                return []

        search_results = data.get("SearchResults", [])
        cars = []
        for item in search_results:
            car_id = item.get("Id")
            if not car_id:
                continue

            photos = self._extract_photo_urls(item.get("Photos", []))
            car_record = {
                "id": str(car_id),
                "manufacturer": item.get("Manufacturer", ""),
                "model": item.get("Model", ""),
                "badge": item.get("Badge", ""),
                "badge_detail": item.get("BadgeDetail", ""),
                "year": item.get("Year"),
                "form_year": item.get("FormYear"),
                "mileage": item.get("Mileage"),
                "price": item.get("Price"),
                "fuel_type": item.get("FuelType", ""),
                "transmission": item.get("Transmission", ""),
                "photos": photos,
            }
            cars.append(car_record)

        return cars

    async def run(self, max_pages: int = 10):
        global state
        state.is_running = True
        state.stop_requested = False
        state.total_parsed = 0
        state.last_error = None
        logger.info(f"Запуск парсера. Лимит страниц: {max_pages}")

        try:
            for page in range(max_pages):
                if state.stop_requested:
                    logger.info("Парсер остановлен по запросу пользователя.")
                    break

                state.current_page = page + 1
                cars = await self.fetch_page(page)

                if not cars:
                    if not state.stop_requested:
                        logger.warning(f"Страница {page + 1} вернула пустой список. Завершаем.")
                    break

                await upsert_cars_batch(cars)
                state.total_parsed += len(cars)
                logger.info(f"Страница {page + 1}: сохранено {len(cars)} авто")

                await asyncio.sleep(0.5)

        except Exception as e:
            logger.exception(f"Критическая ошибка в цикле парсера: {e}")
            state.last_error = str(e)
        finally:
            state.is_running = False
            logger.info(f"Сессия парсинга завершена. Всего собрано: {state.total_parsed}")