# Scrapper Service

Микросервис для фонового отслеживания изменений по ссылкам (GitHub, Stack Overflow, Reddit и др.). Является частью модульной архитектуры проекта LinkTracker.

---

## 🛠 Стек технологий

| Компонент | Технология |
|-----------|------------|
| **Язык** | Python 3.12+ |
| **API** | [FastAPI](https://fastapi.tiangolo.com/) (асинхронный веб-фреймворк) |
| **База данных** | [PostgreSQL 16](https://www.postgresql.org/docs/) (реляционная СУБД) |
| **Брокер сообщений** | [Apache Kafka](https://kafka.apache.org/42/getting-started/introduction/) (обмен данными) |
| **ORM** | [SQLAlchemy 2.x](https://www.sqlalchemy.org/) (асинхронная работа с БД) |
| **Драйвер БД** | [asyncpg](https://magicstack.github.io/asyncpg/) / [psycopg2](https://www.psycopg.org/) |
| **Миграции** | [Alembic](https://alembic.sqlalchemy.org/) (управление схемой БД) |
| **Кэширование** | [Redis](https://redis.io/) (кэширование запросов `/list`) |
| **Конфигурация** | [pydantic-settings](https://docs.pydantic.dev/latest/concepts/pydantic_settings/) (типобезопасная валидация) |
| **Логирование** | [structlog](https://www.structlog.org/) (структурное JSON-логирование) |
| **Тестирование** | [pytest](https://docs.pytest.org/) + [Testcontainers](https://www.testcontainers.org/) |
| **Менеджер зависимостей** | [Poetry](https://python-poetry.org/) |
| **Контейнеризация** | [Docker](https://www.docker.com/) + [Docker Compose](https://docs.docker.com/compose/) |

---

## Параметры запуска Apache Kafka (в docker-compose)

При запуске контейнера Apache Kafka используются следующие параметры:

- `--topic`: Название топика, где будут сохраняться обновления
- `--bootstrap-server`: Точка входа (указывает, к какому брокеру подключиться для выполнения команды)
- `--partitions`: Количество партиций.
*Значение 3 позволяет сбалансировать нагрузку по брокерам, дает возможность инициализировать несколько консьюмеров*
- `--replication-factor`: Фактор репликации партиций.
*Значение 3 дает максимальную отказоустойчивость кластеру*
- `--config min.insync.replicas`: Минимальное число синхронных реплик.
*Значение 2 при факторе репликации 3 позволяет безболезненно пережить падение одного брокера, что дает баланс доступности и надежности*

## 🚀 Инструкция по локальному запуску

### 1. Подготовка окружения

Убедитесь, что у вас установлены:

- **Python** версии 3.12 или выше
- **Poetry** (менеджер пакетов)
- **Docker** и **Docker Compose** (для запуска PostgreSQL и Kafka)

Проверьте версии:

```bash
python --version      # Должно быть 3.12+
poetry --version      # Должно быть 1.8+
docker --version      # Должно быть 24+
docker compose version # Должно быть 2.20+
```

---

### 2. Установка зависимостей

Клонируйте репозиторий и установите все зависимости проекта:

```bash
# Перейдите в корневую папку проекта
cd project-scrapper-service

# Установите зависимости через Poetry
poetry install
```

---

### 3. Настройка конфигурации (.env)

Проект использует переменные окружения для защиты секретных данных.

В корне проекта (там же, где находится `pyproject.toml`) создайте файл `.env`.

> ⚠️ **Важно:** Файл `.env` добавлен в `.gitignore` и **не подлежит коммиту** в систему контроля версий.

---

### 4. Запуск контейнеров (база данных и брокер сообщений)

Запустите Docker Compose:

```bash
# Запустить в фоновом режиме
docker compose up -d

# Проверить статус контейнера
docker compose ps
```

---

### 5. Запуск приложения

```bash
# Запустить сервис через Poetry
poetry run python -m src.main

# Или через uvicorn напрямую
poetry run uvicorn src.main:app --host 0.0.0.0 --port 8080 --reload
```

После запуска:

- Миграции применятся автоматически
- Сервис будет доступен на `http://localhost:8080`
- Health endpoint: `http://localhost:8080/ping`

---

## 🧪 Запуск автотестов

В проекте реализованы интеграционные тесты с использованием **Testcontainers**.

### Запустить все тесты

```bash
poetry run pytest tests/
```

### Запустить тесты с покрытием

```bash
poetry run pytest tests/ --cov=src --cov-report=html
```

### Запустить конкретный тест

```bash
# Тесты управления чатами
poetry run pytest tests/test_api.py::TestChatManagement

# Тесты управления ссылками
poetry run pytest tests/test_api.py::TestLinkManagement

# Конкретный тест
poetry run pytest tests/test_api.py::TestChatManagement::test_register_chat
```

---

## 🛠 Полезные команды

```bash
# Установка зависимостей
poetry install

# Запуск тестов
poetry run pytest tests/ -v

# Запуск тестов с покрытием
poetry run pytest tests/ --cov=src --cov-report=html

# Создать новую миграцию
poetry run alembic revision --autogenerate -m "description"

# Применить миграции
poetry run alembic upgrade head

# Откатить миграции
poetry run alembic downgrade -1

# Остановить контейнеры
docker compose down

# Остановить с удалением данных
docker compose down -v
```

---

## 📝 API Документация

После запуска приложения доступна интерактивная документация:

- **Swagger UI:** <http://localhost:8080/docs>
- **ReDoc:** <http://localhost:8080/redoc>
