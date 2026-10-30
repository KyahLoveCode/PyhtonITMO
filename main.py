
"""
Консольное приложение для поиска в каталоге книг.
Вариант: books-json | title | raw | fuzzy-text | ranked | plain | boost

Запуск:
    python main.py

Загрузка:
    load books.json
"""

import json
import shlex
import time
from difflib import SequenceMatcher
from pathlib import Path
from typing import Any


# Настройки варианта / Cấu hình biến thể
DATA_TYPE = "books-json"
SEARCH_FIELD = "title"
PROCESSING = "raw"
SEARCH_TYPE = "fuzzy-text"
OUTPUT_TYPE = "ranked"
HIGHLIGHTING = "plain"
RATING_MODE = "boost"

DEFAULT_THRESHOLD = 0.35
BOOST_PER_STAR = 0.5


class BookSearchApp:
    def __init__(self) -> None:
        self.records: list[dict[str, Any]] = []
        self.data_loaded = False
        self.filters: list[dict[str, Any]] = []
        self.threshold = DEFAULT_THRESHOLD
        self.ratings: dict[str, int] = {}

        # Chỉ lưu ID của kết quả tìm kiếm gần nhất / ID последнего поиска
        self.last_search_ids: set[str] = set()
        self.last_output = ""

    @staticmethod
    def record_id(record: dict[str, Any], index: int) -> str:
        # Nếu thiếu ID thì dùng vị trí trong danh sách / Если ID отсутствует, используем номер записи
        return str(record.get("id", index + 1))

    def get_fields(self) -> list[str]:
        # Thu thập tất cả tên trường / Собираем названия всех полей
        fields = []
        for record in self.records:
            for field in record:
                if field not in fields:
                    fields.append(field)

        if "id" not in fields:
            fields.insert(0, "id")
        return fields

    def get_value(
        self, record: dict[str, Any], index: int, field: str
    ) -> Any:
        if field == "id" and "id" not in record:
            return index + 1
        return record.get(field)

    @staticmethod
    def value_type(values: list[Any]) -> str:
        # Xác định kiểu dữ liệu của trường / Определяем тип данных поля
        values = [value for value in values if value is not None]

        if not values:
            return "unknown"
        if all(isinstance(v, bool) for v in values):
            return "bool"
        if all(
            isinstance(v, (int, float)) and not isinstance(v, bool)
            for v in values
        ):
            return "number"
        if all(isinstance(v, str) for v in values):
            return "string"
        return "mixed"

    def field_type(self, field: str) -> str:
        values = [
            self.get_value(record, index, field)
            for index, record in enumerate(self.records)
        ]
        return self.value_type(values)

    def load_data(self, filename: str) -> None:
        path = Path(filename).expanduser()

        if not path.is_absolute():
            path = Path.cwd() / path

        if not path.exists() or not path.is_file():
            raise FileNotFoundError(
                f"Файл не найден: {path}"
            )

        with path.open("r", encoding="utf-8-sig") as file:
            data = json.load(file)

        # Поддерживаем массив JSON и распространённые обёртки
        # Hỗ trợ mảng JSON và một số cấu trúc bọc dữ liệu phổ biến
        if isinstance(data, dict):
            for key in ("books", "data", "items"):
                if isinstance(data.get(key), list):
                    data = data[key]
                    break

        if not isinstance(data, list):
            raise ValueError(
                "Некорректная структура JSON. "
                "Ожидается массив объектов или объект с массивом "
                "'books', 'data' либо 'items'."
            )

        if not all(isinstance(item, dict) for item in data):
            raise ValueError(
                "Каждая запись каталога должна быть JSON-объектом."
            )

        if data and not any("title" in item for item in data):
            raise ValueError(
                "В загруженных данных отсутствует поле 'title'."
            )

        # Chỉ cập nhật trạng thái sau khi tải thành công
        # Обновляем состояние только после успешной загрузки
        self.records = data
        self.data_loaded = True
        self.filters.clear()
        self.threshold = DEFAULT_THRESHOLD
        self.ratings.clear()
        self.last_search_ids.clear()
        self.last_output = ""

        print(f"Загружено записей: {len(self.records)}")
        print("Фильтры, оценки и порог поиска сброшены.")

    def print_help(self) -> None:
        print("""
ДОСТУПНЫЕ КОМАНДЫ

  help                                      Показать справку
  load <file>                               Загрузить JSON-файл
  show                                      Показать все записи
  fields                                    Показать поля и их типы
  filter add <field> <operator> <value>     Добавить фильтр
  filter list                               Показать фильтры
  filter remove <number>                    Удалить фильтр по номеру
  filter clear                              Удалить все фильтры
  threshold <number>                        Установить порог (0, 1]
  search "<query>"                          Выполнить поиск
  save <file>                               Сохранить последние результаты
  rate <id> <1..5>                          Оценить запись из последнего поиска
  ratings                                   Показать сохранённые оценки
  exit                                      Завершить программу

ОПЕРАТОРЫ ФИЛЬТРАЦИИ

  number: eq, ne, lt, le, gt, ge
  string: eq, ne, contains
  bool:   eq, ne

ПРИМЕРЫ

  load books.json
  fields
  filter add title contains "Harry Potter"
  search "Harry Potter"
  rate 3 5
  ratings
  save results.txt
""")

    def show_fields(self) -> None:
        operators = {
            "number": "eq, ne, lt, le, gt, ge",
            "string": "eq, ne, contains",
            "bool": "eq, ne",
            "mixed": "eq, ne",
            "unknown": "не определён",
        }

        print("\nПОЛЯ КАТАЛОГА")
        for field in self.get_fields():
            kind = self.field_type(field)
            print(
                f"  {field:<20} "
                f"тип: {kind:<8} "
                f"операторы: {operators[kind]}"
            )

    def add_filter(self, args: list[str]) -> None:
        if len(args) < 3:
            raise ValueError(
                'Формат: filter add <field> <operator> <value>'
            )

        field = args[0]
        operator = args[1].lower()
        value = " ".join(args[2:])

        if field not in self.get_fields():
            raise ValueError(f"Поле не найдено: {field}")

        kind = self.field_type(field)

        allowed = {
            "number": {"eq", "ne", "lt", "le", "gt", "ge"},
            "string": {"eq", "ne", "contains"},
            "bool": {"eq", "ne"},
            "mixed": {"eq", "ne"},
            "unknown": set(),
        }

        if operator not in allowed[kind]:
            valid = ", ".join(sorted(allowed[kind])) or "нет"
            raise ValueError(
                f"Оператор '{operator}' недопустим для типа '{kind}'. "
                f"Допустимые операторы: {valid}"
            )

        if kind == "number":
            try:
                parsed_value: Any = float(value)
            except ValueError:
                raise ValueError("Для числового поля требуется число.")

        elif kind == "bool":
            lowered = value.lower()
            if lowered not in ("true", "false"):
                raise ValueError(
                    "Для логического поля используйте true или false."
                )
            parsed_value = lowered == "true"

        else:
            parsed_value = value

        self.filters.append({
            "field": field,
            "operator": operator,
            "value": parsed_value,
            "display_value": value,
        })

        print(f"Фильтр №{len(self.filters)} добавлен.")

    def list_filters(self) -> None:
        if not self.filters:
            print("Фильтры отсутствуют.")
            return

        print("\nСПИСОК ФИЛЬТРОВ")
        for number, item in enumerate(self.filters, start=1):
            print(
                f"{number}. {item['field']} "
                f"{item['operator']} {item['display_value']}"
            )

    def remove_filter(self, args: list[str]) -> None:
        if len(args) != 1:
            raise ValueError("Формат: filter remove <number>")

        try:
            number = int(args[0])
        except ValueError:
            raise ValueError("Номер фильтра должен быть целым числом.")

        if number < 1 or number > len(self.filters):
            raise ValueError("Фильтр с таким номером не существует.")

        removed = self.filters.pop(number - 1)
        print(
            f"Фильтр удалён: {removed['field']} "
            f"{removed['operator']} {removed['display_value']}"
        )

    @staticmethod
    def compare(actual: Any, operator: str, expected: Any) -> bool:
        # Пустые значения не проходят фильтрацию
        # Пустые значения не удовлетворяют условиям фильтра
        if actual is None or actual == "":
            return False

        if operator == "contains":
            return isinstance(actual, str) and expected in actual

        if operator in ("eq", "ne"):
            result = actual == expected
            return result if operator == "eq" else not result

        try:
            if operator == "lt":
                return actual < expected
            if operator == "le":
                return actual <= expected
            if operator == "gt":
                return actual > expected
            if operator == "ge":
                return actual >= expected
        except TypeError:
            return False

        return False

    def passes_filters(
        self, record: dict[str, Any], index: int
    ) -> bool:
        # Все фильтры объединяются логическим И
        # Tất cả bộ lọc được kết hợp bằng phép AND
        for item in self.filters:
            actual = self.get_value(record, index, item["field"])

            if not self.compare(
                actual, item["operator"], item["value"]
            ):
                return False

        return True

    @staticmethod
    def similarity(query: str, text: str) -> float:
        # raw: không chuẩn hoá chữ hoa, chữ thường hoặc dấu câu
        # raw: без нормализации регистра, пробелов и знаков препинания
        return SequenceMatcher(None, query, text).ratio()

    @staticmethod
    def format_value(value: Any) -> str:
        if isinstance(value, (dict, list)):
            return json.dumps(
                value, ensure_ascii=False, indent=2
            )
        return str(value)

    def render_records(
        self,
        results: list[dict[str, Any]],
        heading: str,
        show_scores: bool,
    ) -> str:
        lines = [heading, "=" * max(10, len(heading))]

        for item in results:
            record = item["record"]
            index = item["index"]
            rid = self.record_id(record, index)

            lines.append(f"\n[ID: {rid}]")

            for field in self.get_fields():
                value = self.get_value(record, index, field)
                lines.append(
                    f"{field}: {self.format_value(value)}"
                )

            if show_scores:
                rating = self.ratings.get(rid)
                rating_text = (
                    str(rating) if rating is not None else "нет"
                )

                lines.append(
                    f"Релевантность: {item['relevance']:.4f}"
                )
                lines.append(f"Оценка: {rating_text}")
                lines.append(f"Бонус: {item['boost']:.2f}")
                lines.append(f"Итоговый балл: {item['score']:.4f}")

            lines.append("-" * 50)

        if not results:
            lines.append("Подходящие записи не найдены.")

        return "\n".join(lines)

    def show_all(self) -> None:
        results = [
            {
                "record": record,
                "index": index,
                "relevance": 0.0,
                "boost": 0.0,
                "score": 0.0,
            }
            for index, record in enumerate(self.records)
        ]

        output = self.render_records(
            results, "ВСЕ ЗАПИСИ КАТАЛОГА", False
        )
        print(output)

        # show не должен разрешать оценку через команду rate
        # Команда show не даёт права оценивать записи
        self.last_search_ids.clear()
        self.last_output = output

    def search(self, query: str) -> None:
        started = time.perf_counter()
        results = []

        for index, record in enumerate(self.records):
            if not self.passes_filters(record, index):
                continue

            title = record.get(SEARCH_FIELD)

            # Пустой запрос означает поиск только по фильтрам
            # Пустой запрос запускает фильтрацию без сравнения названия
            if query == "":
                relevance = 0.0
            else:
                if title is None:
                    continue

                relevance = self.similarity(query, str(title))

                # Сначала проверяем релевантность, затем добавляем бонус
                # Сначала проверяется порог, затем учитывается оценка
                if relevance < self.threshold:
                    continue

            rid = self.record_id(record, index)
            rating = self.ratings.get(rid, 0)
            boost = rating * BOOST_PER_STAR
            score = relevance + boost

            results.append({
                "record": record,
                "index": index,
                "relevance": relevance,
                "rating": rating,
                "boost": boost,
                "score": score,
            })

        # Сортировка по итоговому баллу и релевантности
        # Sắp xếp theo điểm cuối cùng, sau đó theo độ phù hợp
        results.sort(
            key=lambda item: (
                item["score"],
                item["relevance"]
            ),
            reverse=True,
        )

        elapsed = time.perf_counter() - started

        output = self.render_records(
            results,
            f"РЕЗУЛЬТАТЫ ПОИСКА: {query!r}",
            True,
        )

        output += (
            f"\nНайдено записей: {len(results)}"
            f"\nОтображено записей: {len(results)}"
            f"\nВремя поиска: {elapsed:.6f} сек."
            f"\nПорог релевантности: {self.threshold:.2f}"
        )

        print(output)

        # Сохраняем ID только найденных записей
        # Lưu ID của những bản ghi thực sự tìm thấy
        self.last_search_ids = {
            self.record_id(item["record"], item["index"])
            for item in results
        }
        self.last_output = output

    def set_threshold(self, args: list[str]) -> None:
        if len(args) != 1:
            raise ValueError("Формат: threshold <number>")

        try:
            value = float(args[0])
        except ValueError:
            raise ValueError("Порог должен быть числом.")

        if not 0 < value <= 1:
            raise ValueError("Порог должен находиться в диапазоне (0, 1].")

        self.threshold = value
        print(f"Порог поиска установлен: {value:.4f}")

    def rate_record(self, args: list[str]) -> None:
        if len(args) != 2:
            raise ValueError("Формат: rate <id> <1..5>")

        rid = args[0]

        try:
            rating = int(args[1])
        except ValueError:
            raise ValueError("Оценка должна быть целым числом от 1 до 5.")

        if not 1 <= rating <= 5:
            raise ValueError("Оценка должна находиться в диапазоне 1..5.")

        # Chỉ cho phép đánh giá kết quả search gần nhất
        # Разрешается оценивать только результаты последнего поиска
        if rid not in self.last_search_ids:
            raise ValueError(
                f"Запись с ID {rid} отсутствует "
                "в результатах последнего поиска."
            )

        # Đánh giá mới thay thế đánh giá cũ / Новая оценка заменяет старую
        self.ratings[rid] = rating

        print(
            f"Для записи ID {rid} сохранена оценка {rating}/5. "
            "Бонус будет учтён при следующем поиске."
        )

    def show_ratings(self) -> None:
        if not self.ratings:
            print("Сохранённые оценки отсутствуют.")
            return

        print("\nСОХРАНЁННЫЕ ОЦЕНКИ")

        for rid, rating in self.ratings.items():
            title = "Без названия"

            for index, record in enumerate(self.records):
                if self.record_id(record, index) == rid:
                    title = str(record.get("title", title))
                    break

            print(
                f"ID: {rid} | Название: {title} | "
                f"Оценка: {rating}/5"
            )

    def save_results(self, args: list[str]) -> None:
        if len(args) != 1:
            raise ValueError("Формат: save <file>")

        if not self.last_output:
            raise ValueError(
                "Нет результатов для сохранения. "
                "Сначала выполните show или search."
            )

        path = Path(args[0]).expanduser()

        if not path.is_absolute():
            path = Path.cwd() / path

        path.write_text(
            self.last_output + "\n",
            encoding="utf-8"
        )

        print(f"Результаты сохранены в файл: {path}")

    def execute(self, raw_command: str) -> bool:
        try:
            parts = shlex.split(raw_command)
        except ValueError as error:
            print(f"Ошибка синтаксиса: {error}")
            return True

        if not parts:
            return True

        command = parts[0].lower()
        args = parts[1:]

        if command == "exit":
            return False

        if command == "help":
            if args:
                print("Формат: help")
            else:
                self.print_help()
            return True

        if command == "load":
            if len(args) != 1:
                print("Формат: load <file>")
                return True

            try:
                self.load_data(args[0])
            except (OSError, json.JSONDecodeError, ValueError) as error:
                print(f"Ошибка загрузки данных: {error}")

            return True

        # До загрузки доступны только help, load и exit
        # Trước khi tải dữ liệu chỉ cho phép help, load và exit
        if not self.data_loaded:
            print("Сначала загрузите данные командой load <file>.")
            return True

        try:
            if command == "show":
                if args:
                    raise ValueError("Формат: show")
                self.show_all()

            elif command == "fields":
                if args:
                    raise ValueError("Формат: fields")
                self.show_fields()

            elif command == "filter":
                if not args:
                    raise ValueError(
                        "Формат: filter add/list/remove/clear"
                    )

                subcommand = args[0].lower()
                subargs = args[1:]

                if subcommand == "add":
                    self.add_filter(subargs)

                elif subcommand == "list":
                    if subargs:
                        raise ValueError("Формат: filter list")
                    self.list_filters()

                elif subcommand == "remove":
                    self.remove_filter(subargs)

                elif subcommand == "clear":
                    if subargs:
                        raise ValueError("Формат: filter clear")
                    self.filters.clear()
                    print("Все фильтры удалены.")

                else:
                    raise ValueError("Неизвестная команда filter.")

            elif command == "threshold":
                self.set_threshold(args)

            elif command == "search":
                if len(args) > 1:
                    raise ValueError('Формат: search "<query>"')
                self.search(args[0] if args else "")

            elif command == "save":
                self.save_results(args)

            elif command == "rate":
                self.rate_record(args)

            elif command == "ratings":
                if args:
                    raise ValueError("Формат: ratings")
                self.show_ratings()

            else:
                print(
                    f"Неизвестная команда: {command}. "
                    "Введите help для просмотра справки."
                )

        except (ValueError, OSError) as error:
            print(f"Ошибка: {error}")

        return True

    def run(self) -> None:
        print(
            "ПОИСК ПО КАТАЛОГУ КНИГ — "
            "books-json | title | raw | fuzzy-text | ranked | plain | boost"
        )
        print("Введите help для просмотра списка команд.")

        while True:
            try:
                raw_command = input("\n> ")
            except (EOFError, KeyboardInterrupt):
                print("\nРабота программы завершена.")
                break

            if not self.execute(raw_command):
                print("Работа программы завершена.")
                break


def main() -> None:
    app = BookSearchApp()
    app.run()


if __name__ == "__main__":
    main()
