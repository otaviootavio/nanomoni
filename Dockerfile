FROM python:3.9.23-slim

# Python
ENV PYTHONFAULTHANDLER=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONHASHSEED=random \
    PIP_NO_CACHE_DIR=off \
    PIP_DISABLE_PIP_VERSION_CHECK=on \
    PIP_DEFAULT_TIMEOUT=100

# Poetry
ENV POETRY_NO_INTERACTION=1 \
    POETRY_VIRTUALENVS_CREATE=false \
    POETRY_CACHE_DIR='/var/cache/pypoetry' \
    POETRY_HOME='/usr/local'

# Application environment variables
ENV ENVIRONMENT=${ENVIRONMENT} \
    DATABASE_URL=${DATABASE_URL} \
    DATABASE_ECHO=${DATABASE_ECHO} \
    API_HOST=${API_HOST} \
    API_PORT=${API_PORT} \
    API_DEBUG=${API_DEBUG} \
    API_CORS_ORIGINS=${API_CORS_ORIGINS} \
    APP_NAME=${APP_NAME} \
    APP_VERSION=${APP_VERSION}

RUN apt-get update && apt-get install -y curl && rm -rf /var/lib/apt/lists/*
RUN pip install pipx
RUN pipx install poetry==2.1.3
ENV PATH="/root/.local/bin:$PATH"

WORKDIR /app

COPY pyproject.toml poetry.lock /app/
COPY . /app

RUN poetry install

CMD ["poetry", "run", "python", "-m", "src.nanomoni.main"]