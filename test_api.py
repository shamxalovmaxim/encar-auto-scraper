import httpx

URL = "https://api.encar.com/search/car/list/general"

PARAMS = {
    "count": "true",
    "q": "(And.Hidden.N._.CarType.A.)",
    "sr": "|ModifiedDate|0|3",
}

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/129.0.0.0 Safari/537.36"
    ),
    "Referer": "https://www.encar.com/",
    "Accept": "application/json, text/javascript, */*; q=0.01",
}


def test_fetch():
    print("Отправка тестового запроса к Encar...")
    with httpx.Client(headers=HEADERS, timeout=15.0) as client:
        response = client.get(URL, params=PARAMS)

    print(f"HTTP Статус: {response.status_code}")
    if response.status_code != 200:
        print("Ошибка:", response.text[:300])
        return

    data = response.json()
    cars = data.get("SearchResults", [])
    print(f"Всего авто в базе: {data.get('Count')}")
    print(f"Получено записей: {len(cars)}\n")

    for i, car in enumerate(cars, 1):
        car_id = car.get("Id")
        manufacturer = car.get("Manufacturer")
        model = car.get("Model")
        badge = car.get("Badge")
        price = car.get("Price")
        photos = car.get("Photos", [])

        print(f"[{i}] ID: {car_id} | {manufacturer} {model} ({badge}) | Цена: {price}")
        if photos:
            print(f"    Фото (первые 2 ссылки):")
            for p in photos[:2]:
                print(f"      https://ci.encar.com{p.get('location')}")


if __name__ == "__main__":
    test_fetch()