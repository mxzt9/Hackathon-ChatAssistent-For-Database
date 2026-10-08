# Проверки проекта

Установите `requirements-dev.txt`. Обычный `python -m pytest` проверяет API,
выбор колонок, SQL-фильтр, формат ответа модели и поведение при сбое процесса Qwen.
Модель и работающий PostgreSQL для этих проверок не нужны.

## PostgreSQL

```powershell
docker compose up -d postgres
$env:TEST_LOCAL_POSTGRES='1'
python -m pytest tests/test_university.py -q
Remove-Item Env:TEST_LOCAL_POSTGRES
```

Проверка ожидает исходные учебные данные в базе `university`.

## Qwen и PostgreSQL

```powershell
python -m pip install -r requirements-qwen.txt
$env:RUN_QWEN_INTEGRATION='1'
python -m pytest tests/test_qwen_integration.py -q
Remove-Item Env:RUN_QWEN_INTEGRATION
```

Эта проверка сама загружает модель. Для большой базы дополнительно задайте
`TEST_LARGE_POSTGRES=1` после её создания по инструкции LARGE_DATABASE.md.
На машине с ограниченной видеопамятью выполняйте проверку при остановленном
сервере с Qwen, чтобы не загружать две копии модели одновременно.

## Работающий сервер

`python scripts/smoke_server.py` проверяет страницы, JavaScript и health endpoint.
`python scripts/load_test.py` измеряет нагрузку; детали в LOAD_TEST.md.
Оба скрипта принимают `--url http://127.0.0.1:8000`.

Исходники тестов входят в проект. Кэши, временные файлы `.test-tmp/`, отчёты
покрытия, логи, локальные настройки, веса моделей и бинарные выгрузки БД
исключены через `.gitignore`. В Docker-образ тесты и локальные артефакты не входят.
