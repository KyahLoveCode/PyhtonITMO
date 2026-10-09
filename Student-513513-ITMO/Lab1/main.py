#!/usr/bin/env python3
"""
VI: Chương trình tìm kiếm danh mục sân bay theo biến thể được giao.
RU: Программа поиска по каталогу аэропортов для заданного варианта.
"""

# VI: csv đọc dữ liệu bảng; re xử lý từ khóa; shlex phân tích lệnh có dấu ngoặc kép.
# RU: csv читает табличные данные; re обрабатывает слова; shlex разбирает команды с кавычками.
import csv
import re
import shlex
import time
from pathlib import Path

# VI: Các tham số biến thể do giảng viên giao.
# RU: Параметры варианта, заданные преподавателем.
VARIANT = "airports-csv | all | fold | words-all | top10 | mark | boost"
# VI: Chỉ tìm kiếm trong tên sân bay, thành phố và từ khóa.
# RU: Поиск выполняется только по названию, городу и ключевым словам.
SEARCH_FIELDS = ("title", "city", "keywords")
# VI: Thứ tự các cột khi hiển thị hoặc lưu bản ghi.
# RU: Порядок полей при выводе и сохранении записи.
FIELD_ORDER = (
    "id", "title", "city", "keywords", "country", "kind",
    "elevation_ft", "latitude", "longitude", "scheduled", "url",
)
# VI: Phân loại trường để chuyển kiểu dữ liệu và kiểm tra bộ lọc.
# RU: Типы полей нужны для преобразования данных и проверки фильтров.
NUMERIC_FIELDS = {"elevation_ft", "latitude", "longitude"}
BOOLEAN_FIELDS = {"scheduled"}
STRING_FIELDS = set(FIELD_ORDER) - NUMERIC_FIELDS - BOOLEAN_FIELDS
OPERATORS = {
    "str": ("eq", "ne", "contains"),
    "float": ("eq", "ne", "lt", "le", "gt", "ge"),
    "bool": ("eq", "ne"),
}

# VI: Trạng thái chương trình: dữ liệu, bộ lọc, đánh giá và kết quả gần nhất.
# RU: Состояние программы: данные, фильтры, оценки и последние результаты.
records = []
filters = []
ratings = {}
last_results = []
threshold = 0.5


# VI: Chuẩn hóa văn bản để tìm kiếm không phân biệt chữ hoa/chữ thường.
# RU: Нормализуем текст, чтобы поиск не учитывал регистр букв.
def normalize(value):
    """fold: case-insensitive normalization; retain punctuation and accents."""
    return str(value or "").casefold()


# VI: Hiển thị giá trị rỗng bằng dấu gạch ngang, bool bằng true/false.
# RU: Пустые значения выводим тире, bool — как true/false.
def display_value(value):
    if value is None or value == "":
        return "—"
    if isinstance(value, bool):
        return "true" if value else "false"
    return str(value)


# VI: Xác định kiểu dữ liệu của trường theo danh sách đã khai báo.
# RU: Определяем тип поля по заранее заданным спискам.
def infer_field_type(field):
    if field in NUMERIC_FIELDS:
        return "float"
    if field in BOOLEAN_FIELDS:
        return "bool"
    return "str"


# VI: Chuyển văn bản thành giá trị đúng/sai; báo lỗi nếu định dạng không hợp lệ.
# RU: Преобразуем текст в true/false; сообщаем об ошибке при неверном формате.
def parse_bool(value):
    lowered = str(value).strip().casefold()
    if lowered in {"true", "1", "yes", "да"}:
        return True
    if lowered in {"false", "0", "no", "нет"}:
        return False
    raise ValueError("логическое значение должно быть true или false")


# VI: Chuyển giá trị bộ lọc sang kiểu phù hợp với trường.
# RU: Преобразуем значение фильтра в тип соответствующего поля.
def parse_filter_value(field, value):
    field_type = infer_field_type(field)
    if field_type == "float":
        try:
            return float(value)
        except ValueError as exc:
            raise ValueError(f"Для поля {field} нужно числовое значение") from exc
    if field_type == "bool":
        return parse_bool(value)
    return str(value)


# VI: Chuẩn hóa một dòng CSV thành bản ghi với kiểu dữ liệu phù hợp.
# RU: Преобразуем строку CSV в запись с подходящими типами данных.
def typed_record(raw):
    record = {key: raw.get(key, "") for key in FIELD_ORDER}
    for field in NUMERIC_FIELDS:
        value = record.get(field, "")
        try:
            record[field] = float(value) if value not in (None, "") else None
        except (ValueError, TypeError):
            record[field] = None
    for field in BOOLEAN_FIELDS:
        value = record.get(field, "")
        try:
            record[field] = parse_bool(value) if value not in (None, "") else None
        except ValueError:
            record[field] = None
    for field in STRING_FIELDS:
        if record.get(field) is None:
            record[field] = ""
        else:
            record[field] = str(record[field])
    return record


# VI: Đọc CSV, kiểm tra các cột bắt buộc và chuyển từng dòng thành bản ghi.
# RU: Читаем CSV, проверяем обязательные столбцы и преобразуем строки в записи.
def load_file(filename):
    path = Path(filename)
    with path.open("r", encoding="utf-8-sig", newline="") as file:
        reader = csv.DictReader(file)
        if not reader.fieldnames:
            raise ValueError("CSV-файл пуст или не содержит заголовков")
        missing = [field for field in FIELD_ORDER if field not in reader.fieldnames]
        if missing:
            raise ValueError("В CSV отсутствуют поля: " + ", ".join(missing))
        loaded = [typed_record(row) for row in reader]
    return loaded


# VI: Hiển thị tên trường, kiểu dữ liệu và toán tử lọc được hỗ trợ.
# RU: Показываем поля, типы данных и поддерживаемые операторы фильтрации.
def show_fields():
    print("Поиск по полям: " + ", ".join(SEARCH_FIELDS))
    print()
    print(f"{'Поле':<14} {'Тип':<6} Фильтры")
    print(f"{'-' * 14} {'-' * 6} {'-' * 17}")
    for field in FIELD_ORDER:
        field_type = infer_field_type(field)
        ops = " ".join(OPERATORS[field_type]) if field in {"country", "kind", *NUMERIC_FIELDS, *BOOLEAN_FIELDS} else "-"
        print(f"{field:<14} {field_type:<6} {ops}")
    print("\neq = равно; ne = не равно; contains = содержит текст.")
    print("lt <; le <=; gt >; ge >=. true = да; false = нет.")


# VI: In đầy đủ bản ghi; kết quả tìm kiếm có thêm độ liên quan, đánh giá và điểm.
# RU: Печатаем запись целиком; в результатах поиска добавляем релевантность, оценку и баллы.
def print_record(record, highlight_terms=None, relevance=None, score=None):
    highlight_terms = highlight_terms or []
    title = str(record.get("title", ""))
    if highlight_terms:
        title = mark_text(title, highlight_terms)
    print(f"\n[{display_value(record.get('id'))}] {title}")
    for field in FIELD_ORDER:
        if field in {"id", "title"}:
            continue
        value = display_value(record.get(field))
        if highlight_terms and field in SEARCH_FIELDS:
            value = mark_text(value, highlight_terms)
        print(f"  {field}: {value}")
    if relevance is not None:
        print(f"  Релевантность: {relevance:.2f}")
        rating = ratings.get(str(record.get("id", "")))
        print(f"  Оценка: {rating}/5" if rating is not None else "  Оценка: нет")
        print(f"  Баллы: {score:.2f}")


# VI: Đánh dấu đoạn khớp bằng [[...]], giữ nguyên chữ hoa/thường ban đầu.
# RU: Выделяем совпадения через [[...]], сохраняя исходный регистр.
def mark_text(text, terms):
    """Highlight matching query words while preserving original letter case."""
    if not text or not terms:
        return text
    unique_terms = sorted({term for term in terms if term}, key=len, reverse=True)
    if not unique_terms:
        return text
    pattern = re.compile("(" + "|".join(re.escape(term) for term in unique_terms) + ")", re.IGNORECASE)
    return pattern.sub(lambda match: "[[" + match.group(0) + "]]", text)


# VI: Bản ghi chỉ được giữ lại khi thỏa mãn tất cả bộ lọc đang bật.
# RU: Запись проходит проверку, только если удовлетворяет всем активным фильтрам.
def record_passes_filters(record):
    for field, operator, expected in filters:
        actual = record.get(field)
        if actual is None or actual == "":
            return False
        if operator == "eq":
            passed = normalize(actual) == normalize(expected) if isinstance(actual, str) else actual == expected
        elif operator == "ne":
            passed = normalize(actual) != normalize(expected) if isinstance(actual, str) else actual != expected
        elif operator == "contains":
            passed = normalize(expected) in normalize(actual)
        elif operator == "lt":
            passed = actual < expected
        elif operator == "le":
            passed = actual <= expected
        elif operator == "gt":
            passed = actual > expected
        elif operator == "ge":
            passed = actual >= expected
        else:
            passed = False
        if not passed:
            return False
    return True


# VI: Tính điểm: từ khớp trong title được 3 điểm, city/keywords được 1 điểm.
# RU: Подсчёт релевантности: совпадение в title даёт 3 балла, в city/keywords — 1 балл.
def relevance_for(record, terms):
    """Score matches by field: title=3, city=1, keywords=1 per query word."""
    if not terms:
        return 0.0
    combined = " ".join(str(record.get(field) or "") for field in SEARCH_FIELDS)
    folded_combined = normalize(combined)
    if not all(term in folded_combined for term in terms):
        return None
    score = 0.0
    for term in terms:
        if term in normalize(record.get("title", "")):
            score += 3.0
        if term in normalize(record.get("city", "")):
            score += 1.0
        if term in normalize(record.get("keywords", "")):
            score += 1.0
    return score


# VI: Tìm bản ghi thỏa bộ lọc và chứa mọi từ truy vấn; xếp hạng, sau đó hiện tối đa 10.
# RU: Ищем записи, прошедшие фильтры и содержащие все слова запроса; сортируем и выводим максимум 10.
def search(query):
    started = time.perf_counter()
    # VI: Tách truy vấn thành các từ; words-all yêu cầu tất cả từ đều xuất hiện.
    # RU: Разбиваем запрос на слова; words-all требует наличия каждого слова.
    terms = [normalize(term) for term in re.findall(r"\w+", query, flags=re.UNICODE)]
    found = []
    for record in records:
        if not record_passes_filters(record):
            continue
        if not query.strip():
            relevance = 0.0
        else:
            relevance = relevance_for(record, terms)
            if relevance is None:
                continue
        rating = ratings.get(str(record.get("id", "")))
        boost_score = relevance + (0.5 * rating if rating is not None else 0.0)
        found.append({"record": record, "relevance": relevance, "score": boost_score})
    # VI: boost chỉ đổi thứ tự sắp xếp, không thay đổi điểm liên quan.
    # RU: boost меняет только порядок сортировки, но не релевантность.
    # VI: Điểm cao hơn đứng trước; nếu bằng nhau, ưu tiên liên quan rồi đến ID.
    # RU: Сначала больший балл; при равенстве — релевантность, затем ID.
    found.sort(key=lambda item: (-item["score"], -item["relevance"], str(item["record"].get("id", ""))))
    shown = found[:10]
    elapsed_ms = (time.perf_counter() - started) * 1000
    print(f"Найдено: {len(found)}; показано: {len(shown)}")
    for item in shown:
        print_record(item["record"], terms if query.strip() else [], item["relevance"], item["score"])
    print(f"\nВремя поиска: {elapsed_ms:.2f} мс")
    global last_results
    last_results = shown


# VI: Lệnh show luôn hiển thị toàn bộ dữ liệu, không phụ thuộc bộ lọc.
# RU: Команда show выводит все записи независимо от активных фильтров.
def show_all():
    print(f"Записей: {len(records)}")
    for record in records:
        print_record(record)


# VI: Kiểm tra cú pháp, trường, toán tử và kiểu giá trị trước khi thêm bộ lọc.
# RU: Перед добавлением фильтра проверяем синтаксис, поле, оператор и тип значения.
def add_filter(parts):
    if len(parts) < 5:
        raise ValueError("Формат: filter add <поле> <оператор> <значение>")
    field, operator = parts[2], parts[3]
    value_text = " ".join(parts[4:])
    if field not in FIELD_ORDER:
        raise ValueError(f"Неизвестное поле: {field}")
    field_type = infer_field_type(field)
    if operator not in OPERATORS[field_type]:
        raise ValueError(f"Оператор {operator} не поддерживается для поля {field}")
    expected = parse_filter_value(field, value_text)
    filters.append((field, operator, expected))
    print(f"Добавлен фильтр {len(filters)}: {field} {operator} {value_text}")


# VI: Liệt kê các bộ lọc theo số thứ tự để có thể xóa từng bộ lọc.
# RU: Выводим фильтры с номерами, чтобы можно было удалить отдельный фильтр.
def list_filters():
    if not filters:
        print("Фильтров нет")
        return
    for index, (field, operator, value) in enumerate(filters, start=1):
        print(f"{index}. {field} {operator} {display_value(value)}")


# VI: Lưu kết quả của lần tìm kiếm gần nhất vào tệp văn bản.
# RU: Сохраняем результаты последнего поиска в текстовый файл.
def save_results(filename):
    with open(filename, "w", encoding="utf-8") as file:
        if not last_results:
            file.write("Нет сохранённых результатов поиска. Выполните search.\n")
        else:
            for item in last_results:
                record = item["record"]
                file.write(f"[{display_value(record.get('id'))}] {display_value(record.get('title'))}\n")
                for field in FIELD_ORDER:
                    if field != "id":
                        file.write(f"  {field}: {display_value(record.get(field))}\n")
                file.write(f"  Релевантность: {item['relevance']:.2f}\n")
                rating = ratings.get(str(record.get("id", "")))
                file.write(f"  Оценка: {rating}/5\n" if rating is not None else "  Оценка: нет\n")
                file.write(f"  Баллы: {item['score']:.2f}\n\n")
    print(f"Сохранено: {filename}")


# VI: In danh sách lệnh và cú pháp sử dụng.
# RU: Печатаем список команд и правила их использования.
def print_help():
    print("Команды:")
    print("  help                         — показать помощь")
    print("  load <файл.csv>              — загрузить каталог")
    print("  fields                       — показать поля и типы фильтров")
    print("  show                         — показать все записи")
    print("  filter add <поле> <оп> <значение>")
    print("  filter list                  — показать фильтры")
    print("  filter remove <номер>        — удалить фильтр")
    print("  filter clear                 — очистить фильтры")
    print('  search "<запрос>"             — поиск по title, city, keywords')
    print("  save <файл>                  — сохранить последние результаты")
    print("  rate <id> <1..5>             — поставить оценку")
    print("  ratings                      — показать оценки")
    print("  exit                         — выход")


# VI: Phân tích lệnh và gọi chức năng tương ứng; load đặt lại trạng thái.
# RU: Разбираем команду и вызываем нужную функцию; load сбрасывает состояние.
def handle_command(parts):
    global records, filters, ratings, last_results, threshold
    command = parts[0].casefold()
    if command == "exit" and len(parts) == 1:
        return False
    if command == "help" and len(parts) == 1:
        print_help()
    elif command == "load" and len(parts) == 2:
        # VI: Chỉ cập nhật trạng thái sau khi tệp mới được đọc thành công.
        # RU: Обновляем состояние только после успешного чтения нового файла.
        loaded = load_file(parts[1])
        records = loaded
        filters = []
        ratings = {}
        last_results = []
        threshold = 0.5
        print(f"Загружено записей: {len(records)}")
    elif not records and command not in {"help", "load", "exit"}:
        print("Сначала загрузите данные: load <файл.csv>")
    elif command == "fields" and len(parts) == 1:
        show_fields()
    elif command == "show" and len(parts) == 1:
        show_all()
    elif command == "filter" and len(parts) >= 2:
        subcommand = parts[1].casefold()
        if subcommand == "add":
            add_filter(parts)
        elif subcommand == "list" and len(parts) == 2:
            list_filters()
        elif subcommand == "remove" and len(parts) == 3:
            try:
                index = int(parts[2])
            except ValueError as exc:
                raise ValueError("Номер фильтра должен быть целым числом") from exc
            if not 1 <= index <= len(filters):
                raise ValueError("Фильтра с таким номером нет")
            filters.pop(index - 1)
            print("Фильтр удалён")
        elif subcommand == "clear" and len(parts) == 2:
            filters.clear()
            print("Фильтры удалены")
        else:
            raise ValueError("Неизвестная команда filter. Используйте filter add/list/remove/clear")
    elif command == "threshold" and len(parts) == 2:
        raise ValueError("Порог доступен только для режимов fuzzy; в вашем варианте используется words-all")
    elif command == "search" and len(parts) == 2:
        search(parts[1])
    elif command == "save" and len(parts) == 2:
        save_results(parts[1])
    elif command == "rate" and len(parts) == 3:
        record_id = parts[1]
        try:
            rating = int(parts[2])
        except ValueError as exc:
            raise ValueError("Оценка должна быть целым числом от 1 до 5") from exc
        if not 1 <= rating <= 5:
            raise ValueError("Оценка должна быть целым числом от 1 до 5")
        if not any(str(record.get("id")) == record_id for record in records):
            raise ValueError(f"Запись с id {record_id} не найдена")
        ratings[record_id] = rating
        print(f"Оценка: {record_id} — {rating}/5")
    elif command == "ratings" and len(parts) == 1:
        if not ratings:
            print("Оценок нет")
        else:
            for record_id in sorted(ratings):
                print(f"{record_id}: {ratings[record_id]}/5")
    else:
        print('Неизвестная команда. Введите help для списка команд.')
    return True


# VI: Vòng lặp dòng lệnh; lỗi được thông báo nhưng không làm chương trình dừng.
# RU: Цикл командной строки; ошибки выводятся, но не завершают программу.
def main():
    print("Поиск по каталогу. Команды: help. Выход: exit.")
    while True:
        try:
            parts = shlex.split(input("\nsearch> "))
            if not parts:
                continue
            if not handle_command(parts):
                break
        except EOFError:
            print()
            break
        # VI: Bắt lỗi thường gặp để người dùng có thể tiếp tục nhập lệnh.
        # RU: Перехватываем типичные ошибки, чтобы пользователь мог продолжить ввод команд.
        except (OSError, csv.Error, ValueError, TypeError) as error:
            print("Ошибка:", error)


if __name__ == "__main__":
    main()
