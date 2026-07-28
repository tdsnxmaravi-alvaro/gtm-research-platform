# Cloud-agnostic image: installs the gtm engine + the DRF API, serves via gunicorn.
# Deploys to Azure Container Apps / App Service, AWS ECS/Fargate/App Runner, etc.
FROM python:3.13-slim

ENV PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1 DJANGO_SETTINGS_MODULE=gtm_api.settings

WORKDIR /app

# Install the gtm engine (editable) first for better layer caching.
COPY pyproject.toml README.md ./
COPY gtm ./gtm
RUN pip install --no-cache-dir -e .

# Install backend deps + copy the backend.
COPY backend/requirements.txt ./backend/requirements.txt
RUN pip install --no-cache-dir -r backend/requirements.txt
COPY backend ./backend

WORKDIR /app/backend
EXPOSE 8000

# Run migrations then serve. PORT is honored by most PaaS platforms.
CMD ["sh", "-c", "python manage.py migrate --noinput && gunicorn gtm_api.wsgi:application --bind 0.0.0.0:${PORT:-8000} --workers 3"]
