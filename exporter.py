"""
Модуль мгновенного экспорта данных в Excel (.xlsx) и CSV.
Работает на 100% локально через оптимизированный лексический токенизатор и Regex:
- Генерация файла за доли секунды без зависаний и сетевых лимитов.
- Полный перевод марок, моделей, поколений, типов кузова, топлива и комплектаций.
- Кликабельные ссылки на интерактивную галерею Encar и главное фото CDN.
"""

from datetime import datetime
from pathlib import Path
import json
import re
import aiosqlite
import pandas as pd
from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
from openpyxl.utils import get_column_letter

from config import DB_PATH, EXPORTS_DIR

# 1. Словарь характеристик (Топливо и КПП)
TRANSLATIONS_CORE = {
    "fuel": {
        "가솔린": "Бензин",
        "디젤": "Дизель",
        "가솔린+전기": "Гибрид (Бензин)",
        "디젤+전기": "Гибрид (Дизель)",
        "전기": "Электро",
        "수소": "Водород",
        "LPG": "Газ (LPG)",
        "LPG(일반인 구입)": "Газ (LPG)",
        "가솔린+LPG": "Бензин + Газ",
    },
    "transmission": {
        "오토": "Автомат",
        "수동": "Механика",
        "CVT": "Вариатор",
        "듀얼클러치": "Робот (DCT)",
        "": "Автомат",
        None: "Автомат",
    },
}

# 2. Полный локальный автомобильный словарь Encar
KOREAN_AUTO_DICTIONARY = {
    # Марки
    "현대": "Hyundai",
    "기아": "Kia",
    "제네시스": "Genesis",
    "쉐보레(GM대우)": "Chevrolet",
    "쉐보레": "Chevrolet",
    "르노코리아(삼성)": "Renault Korea",
    "르노코리아": "Renault Korea",
    "르노삼성": "Renault Samsung",
    "KG모빌리티(쌍용)": "KGM (SsangYong)",
    "KG모빌리티": "KGM",
    "쌍용": "SsangYong",
    "벤츠": "Mercedes-Benz",
    "BMW": "BMW",
    "아우ди": "Audi",
    "폭스바겐": "Volkswagen",
    "볼보": "Volvo",
    "포르쉐": "Porsche",
    "랜드로버": "Land Rover",
    "지프": "Jeep",
    "미니": "MINI",
    "렉서스": "Lexus",
    "토요타": "Toyota",
    "혼да": "Honda",
    "포д": "Ford",
    "테슬라": "Tesla",
    "인피니티": "Infiniti",
    "푸조": "Peugeot",
    "링컨": "Lincoln",
    "캐딜락": "Cadillac",
    "재규어": "Jaguar",
    "마세라티": "Maserati",
    "벤틀리": "Bentley",

    # Серии, классы, кузова
    "-클래스": "-Class",
    "클래스": " Class",
    "시리즈": " Series",
    "모델 ": "Model ",
    "모델": "Model",
    "쿠페": "Coupe",
    "컨버터블": "Convertible",
    "투어링": "Touring",
    "세단": "Sedan",
    "해치백": "Hatchback",
    "더 뉴 ": "The New ",
    "더 뉴": "The New",
    "올 뉴 ": "All New ",
    "올 뉴": "All New",
    "더 넥스트 ": "The Next ",
    "더 넥스트": "The Next",
    "디 엣지": "The Edge",
    "뉴 라이즈": "New Rise",
    "노바": "Nova",
    "더 볼드": "The Bold",
    "더 프라임": "The Prime",
    "콰트로": "Quattro",

    # Модели Hyundai & Kia
    "쏘나타": "Sonata",
    "아반떼": "Avante (Elantra)",
    "그랜저": "Grandeur",
    "싼타페": "Santa Fe",
    "팰리세이드": "Palisade",
    "투싼": "Tucson",
    "코나": "Kona",
    "스타리아": "Staria",
    "쏠라티": "Solati",
    "넥쏘": "Nexo",
    "베뉴": "Venue",
    "아이오닉": "Ioniq",
    "캐스퍼": "Casper",
    "맥스크루즈": "Maxcruz",
    "에쿠스": "Equus",
    "스포티지": "Sportage",
    "쏘렌토": "Sorento",
    "카니발": "Carnival",
    "모닝": "Morning",
    "레이": "Ray",
    "셀토스": "Seltos",
    "모하비": "Mohave",
    "니ро": "Niro",
    "스팅어": "Stinger",
    "K3": "K3",
    "K5": "K5",
    "K7": "K7",
    "K8": "K8",
    "K9": "K9",
    "EV6": "EV6",
    "EV9": "EV9",

    # Модели прочие
    "토레스": "Torres",
    "렉스턴": "Rexton",
    "티볼리": "Tivoli",
    "코란도": "Korando",
    "뷰ти풀": "Beautiful",
    "트레일블레이저": "Trailblazer",
    "트래버스": "Traverse",
    "콜로라도": "Colorado",
    "트랙스": "Trax",
    "스파크": "Spark",
    "말리부": "Malibu",
    "그랑 콜레오스": "Grand Koleos",
    "필랑트": "Filante",
    "탈리스만": "Talisman",
    "쿠퍼 클럽맨": "Cooper Clubman",
    "쿠퍼 컨트리맨": "Cooper Countryman",
    "쿠퍼": "Cooper",
    "클럽맨": "Clubman",
    "컨트리맨": "Countryman",
    "디스커버리": "Discovery",
    "레인지로버": "Range Rover",
    "이보크": "Evoque",
    "벨라": "Velar",
    "디펜더": "Defender",
    "랭글러": "Wrangler",
    "체로키": "Cherokee",
    "그랜드 체로키": "Grand Cherokee",
    "익스플로러": "Explorer",
    "머스탱": "Mustang",
    "타이칸": "Taycan",
    "파나메라": "Panamera",
    "카이엔": "Cayenne",
    "마кан": "Macan",
    "박스터": "Boxster",

    # Двигатель и привод
    "가솔린": "Бензин",
    "디젤": "Дизель",
    "터보": "Турбо",
    "전기": "Электро",
    "수소": "Водород",
    "하이브리드": "Hybrid",
    "바이퓨얼": "Бензин+Газ",

    # Комплектации (Trim) и опции
    "프레스티지": "Prestige",
    "노블레스": "Noblesse",
    "익스클루시브": "Exclusive",
    "인스퍼레이션": "Inspiration",
    "시그니처": "Signature",
    "프리미엄": "Premium",
    "스마트": "Smart",
    "트렌디": "Trendy",
    "럭셔리": "Luxury",
    "모던": "Modern",
    "에어": "Air",
    "어스": "Earth",
    "캘리그래피": "Calligraphy",
    "르블랑": "Le Blanc",
    "그래비티": "Gravity",
    "스타일": "Style",
    "패션": "Fashion",
    "클래식": "Classic",
    "스페셜": "Special",
    "마스터": "Master",
    "플러스": "Plus",
    "인스파이어": "Inspire",
    "에스프리 알핀": "Esprit Alpine",
    "디 에센셜 라이트": "The Essential Light",
    "디 에센셜": "The Essential",
    "롱 레인지": "Long Range",
    "롱레인지": "Long Range",
    "스탠다드": "Standard",
    "스포츠": "Sport",
    "아이코닉": "Iconic",
    "장애인용": "Для инвалидов",
    "렌터카용": "Для проката",
    "영업용": "Коммерческий",
    "(세부등급 없음)": "Базовая",
    "세부등급 없음": "Базовая",
    "하이리무진": "Hi-Limousine",
}


def clean_korean(text: str) -> str:
    """Мгновенная локальная очистка и перевод без сетевых запросов."""
    if not text:
        return ""
    res = str(text)

    # 1. Заменяем числовые корейские суффиксы через Regex
    res = re.sub(r"(\d+)\s*세대", r"\1 поколение", res)
    res = re.sub(r"(\d+)\s*인승", r"\1 мест", res)

    # 2. Быстрая замена по словарю (в порядке убывания длины фраз)
    for k in sorted(KOREAN_AUTO_DICTIONARY.keys(), key=len, reverse=True):
        if k in res:
            res = res.replace(k, KOREAN_AUTO_DICTIONARY[k])

    return " ".join(res.split()).strip()


async def export_cars_to_file(format_type: str = "excel") -> Path:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("SELECT * FROM cars ORDER BY created_at DESC") as cursor:
            rows = await cursor.fetchall()

    if not rows:
        raise ValueError("База данных пуста. Нечего экспортировать.")

    data = [dict(row) for row in rows]

    for item in data:
        car_id = str(item.get("id", ""))

        # Характеристики
        fuel = item.get("fuel_type")
        item["fuel_type"] = TRANSLATIONS_CORE["fuel"].get(fuel, clean_korean(fuel) or "Не указано")

        trans = item.get("transmission")
        item["transmission"] = TRANSLATIONS_CORE["transmission"].get(trans, "Автомат")

        # Мгновенная локальная нормализация
        item["manufacturer"] = clean_korean(item.get("manufacturer", ""))
        item["model"] = clean_korean(item.get("model", ""))
        item["badge"] = clean_korean(item.get("badge", ""))
        item["badge_detail"] = clean_korean(item.get("badge_detail", "")) or "Базовая"

        # Ссылка на интерактивную карточку Encar со всеми фото
        item["encar_page_url"] = f"https://www.encar.com/dc/dc_cardetailview.do?carid={car_id}"

        # Главное фото CDN
        raw_photos = item.get("photos_json")
        first_url = ""
        photos_count = 0
        if raw_photos:
            try:
                photos_list = json.loads(raw_photos)
                if photos_list:
                    first_url = photos_list[0]
                    photos_count = len(photos_list)
            except Exception:
                pass

        if first_url:
            if not first_url.startswith("http"):
                first_url = f"https://{first_url}"
            elif first_url.startswith("http://"):
                first_url = first_url.replace("http://", "https://")

        item["photo_url"] = first_url
        item["photos_count"] = photos_count
        item.pop("photos_json", None)

    df = pd.DataFrame(data)

    columns_mapping = {
        "id": "ID авто",
        "manufacturer": "Марка",
        "model": "Модель",
        "badge": "Поколение / Мотор",
        "badge_detail": "Комплектация",
        "year": "Год",
        "form_year": "Модельный год",
        "mileage": "Пробег (км)",
        "price": "Цена (тыс. вон)",
        "fuel_type": "Топливо",
        "transmission": "КПП",
        "encar_page_url": "Объявление на Encar",
        "photo_url": "Главное фото (CDN)",
        "photos_count": "Всего фото",
        "created_at": "Добавлено",
        "updated_at": "Обновлено",
    }
    df = df.rename(columns=columns_mapping)

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

    # Сохранение в формате CSV с точкой с запятой для корректного отображения в Excel
    if format_type.lower() == "csv":
        file_path = EXPORTS_DIR / f"encar_cars_{timestamp}.csv"
        df.to_csv(file_path, index=False, sep=";", encoding="utf-8-sig")
        return file_path

    # Сохранение в формате Excel с нативной стилизацией
    file_path = EXPORTS_DIR / f"encar_cars_{timestamp}.xlsx"

    with pd.ExcelWriter(file_path, engine="openpyxl") as writer:
        df.to_excel(writer, index=False, sheet_name="Каталог Encar")
        ws = writer.sheets["Каталог Encar"]

        # Оформление заголовка
        header_fill = PatternFill(start_color="1A365D", end_color="1A365D", fill_type="solid")
        header_font = Font(name="Calibri", size=11, bold=True, color="FFFFFF")
        link_font = Font(name="Calibri", size=10, color="004C99", underline="single")
        regular_font = Font(name="Calibri", size=10)

        center_align = Alignment(horizontal="center", vertical="center")
        left_align = Alignment(horizontal="left", vertical="center")
        right_align = Alignment(horizontal="right", vertical="center")

        thin_border = Border(
            left=Side(style="thin", color="E2E8F0"),
            right=Side(style="thin", color="E2E8F0"),
            top=Side(style="thin", color="E2E8F0"),
            bottom=Side(style="thin", color="E2E8F0"),
        )

        for col_num in range(1, len(df.columns) + 1):
            cell = ws.cell(row=1, column=col_num)
            cell.fill = header_fill
            cell.font = header_font
            cell.alignment = center_align

        cols = list(df.columns)
        encar_page_idx = cols.index("Объявление на Encar") + 1
        photo_col_idx = cols.index("Главное фото (CDN)") + 1
        photos_count_idx = cols.index("Всего фото") + 1
        mileage_col_idx = cols.index("Пробег (км)") + 1
        price_col_idx = cols.index("Цена (тыс. вон)") + 1
        year_col_idx = cols.index("Год") + 1

        for row in range(2, len(df) + 2):
            for col in range(1, len(df.columns) + 1):
                c = ws.cell(row=row, column=col)
                c.border = thin_border
                c.font = regular_font

                if col in [mileage_col_idx, price_col_idx]:
                    c.number_format = "#,##0"
                    c.alignment = right_align
                elif col in [year_col_idx, year_col_idx + 1, photos_count_idx]:
                    c.alignment = center_align
                else:
                    c.alignment = left_align

            # Гиперссылка на интерактивную страницу Encar (все фото, 360°, салон)
            page_cell = ws.cell(row=row, column=encar_page_idx)
            page_url = str(page_cell.value or "").strip()
            if page_url.startswith("https://"):
                page_cell.value = "🔗 Открыть на Encar (Галерея)"
                page_cell.hyperlink = page_url
                page_cell.font = link_font
                page_cell.alignment = center_align

            # Прямая ссылка на первое фото
            photo_cell = ws.cell(row=row, column=photo_col_idx)
            raw_photo_url = str(photo_cell.value or "").strip()
            if raw_photo_url.startswith("https://"):
                photo_cell.value = "🖼 Главное фото"
                photo_cell.hyperlink = raw_photo_url
                photo_cell.font = link_font
                photo_cell.alignment = center_align

        # Автоматическая ширина колонок
        for col in ws.columns:
            max_len = max(len(str(cell.value or "")) for cell in col)
            col_letter = get_column_letter(col[0].column)
            ws.column_dimensions[col_letter].width = min(max(max_len + 4, 12), 40)

        ws.freeze_panes = "A2"
        ws.auto_filter.ref = ws.dimensions

    return file_path


def get_database_dump_file() -> Path:
    if not DB_PATH.exists():
        raise FileNotFoundError("Файл базы данных еще не создан.")
    return DB_PATH