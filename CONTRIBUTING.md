# Contributing

## Добавление регистра/параметра
1. Строка в `data/registers.csv` или `data/parameters.csv` с `source` и `confidence`.
2. Синхронизация readable‑дока (`docs/REGISTERS.md` / `PARAMETERS.md`).
3. Пример кадра в `docs/EXAMPLES.md` + фикстура в `data/frames/` (поля `verified_request`/`verified_response`).
4. Тест; запись в `CHANGELOG.md`.

## Уровни достоверности
high = подтверждено руководством/прибором; medium = выведено логически; low/unverified = гипотеза (не включать в golden и в safe‑запись без проверки).

## Безопасность
Не добавлять примеры, пускающие двигатель, без предупреждения и флага control. Не копировать таблицы мануала massово (лицензия).
