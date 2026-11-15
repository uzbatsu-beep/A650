# ONI A650 Configurator

Проект для разработки ПО конфигурирования векторного преобразователя частоты ONI A650.

Основной интерфейс связи — Modbus RTU по RS-485.

## Цель проекта

- читать параметры и мониторинговые регистры A650;
- записывать разрешённые параметры;
- управлять пуском/остановом;
- формировать профили конфигурации;
- предоставлять безопасный CLI/GUI инструмент.

## Важно

Это проект для работы с промышленным оборудованием.  
Любая запись параметров должна выполняться только после проверки:

- двигатель отключён или находится в безопасном режиме;
- известен адрес ПЧ;
- известны скорость, формат данных, чётность;
- включена возможность аварийного останова;
- сделана резервная копия параметров.

См. [docs/SAFETY.md](docs/SAFETY.md).

## Документация

- [Версионируемые профили редакторов](docs/EDITOR_PROFILES.md)

- [Фактическое состояние разработки](docs/DEVELOPMENT_STATUS.md)

- [Офлайн-редакторы и проверенные параметры](docs/OFFLINE_EDITORS.md)

- [Дизайн интерфейса и критерии альфы](docs/INTERFACE_DESIGN.md)

- [Разбор архива A650.zip: полезные материалы и противоречия](docs/ARCHIVE_REVIEW.md)

- [Формат OniDriveStudio .ods, предпросмотр и перенос enum](docs/ODS_FORMAT.md)

- [Загруженные PDF и исследование OniDriveStudio EXE](docs/UPLOADED_MATERIALS.md)

- [Сверка официальных параметров и русский экран подключения](docs/PARAMETER_VERIFICATION.md)

- [План разработки, источники и статус проверки протокола](docs/DEVELOPMENT_PLAN.md)
- [Protocol](docs/PROTOCOL.md)
- [Registers](docs/REGISTERS.md)
- [Parameters](docs/PARAMETERS.md)
- [Examples](docs/EXAMPLES.md)
- [Errors](docs/ERRORS.md)
- [Wiring](docs/WIRING.md)
- [Architecture](docs/ARCHITECTURE.md)
- [Testing](docs/TESTING.md)

## Машиночитаемые данные

- [data/registers.csv](data/registers.csv)
- [data/parameters.csv](data/parameters.csv)
- [data/errors.csv](data/errors.csv)
- [data/profile.schema.json](data/profile.schema.json)

## Статус

Промежуточный релиз **0.2.0.dev2**: [описание и сценарии оценки](docs/releases/0.2.0.dev2.md).
Windows ZIP и контрольная сумма публикуются в
[GitHub Releases](https://github.com/uzbatsu-beep/A650/releases) после успешной сборки.

Технический прототип с интерактивным офлайн-редактором. Есть каталог A650/A650M,
14 типизированных редакторов, проекты, undo/redo, сравнение, чтение enum из
Modbus-симулятора и предпросмотр ODS с переносом выбранных enum в проект.
Управление каталогом перенесено в сворачиваемую левую панель. Отдельная
экспериментальная команда `a650 diagnostics` выполняет стендовый опрос только
для чтения; [инструкция и ограничения](docs/BENCH_DIAGNOSTICS.md).
Совместимость ODS, физическое параметрирование и полный Windows-сценарий
требуют проверки. Это ещё не завершённая альфа конфигуратора.

- **[Что реализовано и проверено](docs/DEVELOPMENT_STATUS.md)** — актуальный срез и ограничения.
- **[План продолжения](docs/DEVELOPMENT_PLAN.md)** — приоритеты и условия завершения.
- **[Дизайн интерфейса](docs/INTERFACE_DESIGN.md)** — целевые сценарии и редакторы.

## Структура репозитория

```text
A650/
├── README.md
├── LICENSE
├── CHANGELOG.md
├── CONTRIBUTING.md
├── SECURITY.md
├── SUPPORT.md
├── .gitignore
├── .github/
│   ├── ISSUE_TEMPLATE/
│   │   ├── bug_report.md
│   │   └── feature_request.md
│   └── PULL_REQUEST_TEMPLATE.md
├── docs/
│   ├── PROTOCOL.md
│   ├── REGISTERS.md
│   ├── PARAMETERS.md
│   ├── ERRORS.md
│   ├── EXAMPLES.md
│   ├── SAFETY.md
│   ├── WIRING.md
│   ├── ARCHITECTURE.md
│   ├── TESTING.md
│   └── decisions/
│       └── ADR-0001-use-modbus-rtu.md
├── data/
│   ├── registers.csv
│   ├── parameters.csv
│   ├── errors.csv
│   ├── profile.schema.json
│   └── frames/
│       ├── read_output_frequency.json
│       ├── set_frequency_30hz.json
│       ├── start_forward.json
│       ├── stop_deceleration.json
│       └── error_read_only.json
├── examples/
│   ├── python/
│   └── cli/
└── tests/
    ├── protocol/
    └── fixtures/
```
