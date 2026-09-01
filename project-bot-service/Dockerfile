FROM python:3.12-slim AS app

ENV POETRY_HOME="/opt/poetry" \
    POETRY_VIRTUALENVS_IN_PROJECT=true \
    POETRY_NO_INTERACTION=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

ENV PATH="$POETRY_HOME/bin:$PATH"
RUN apt-get update && apt-get install -y curl
RUN curl -sSL https://install.python-poetry.org | python -

WORKDIR /app
COPY pyproject.toml poetry.lock ./
RUN poetry install --no-root --with main

COPY src /app
ENTRYPOINT ["poetry", "run", "python", "-m", "src.main"]