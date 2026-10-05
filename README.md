# ONI A650 Configurator

Проект для разработки ПО конфигурирования векторного преобразователя частоты ONI A650.

Основной интерфейс связи — Modbus RTU по RS-485.

##Начальная структура:
.
├── README.md
├── LICENSE
├── CHANGELOG.md
├── CONTRIBUTING.md
├── SECURITY.md
├── SUPPORT.md
├── .gitignore
│
├── .github/
│   ├── ISSUE_TEMPLATE/
│   │   ├── bug_report.md
│   │   └── feature_request.md
│   └── PULL_REQUEST_TEMPLATE.md
│
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
│
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
│
├── examples/
│   ├── python/
│   └── cli/
│
└── tests/
    ├── protocol/
    └── fixtures/

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

Проект находится на стадии исследования протокола и каталогизации регистров.  
Адресная карта известна частично и требует проверки на реальном устройстве.
