"""Celery application for the GTM API.

Broker + result backend are Redis by default (one dependency, cloud-portable).
Swap CELERY_BROKER_URL to RabbitMQ later without code changes if needed.
"""

import os

from celery import Celery

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "gtm_api.settings")

app = Celery("gtm_api")
app.config_from_object("django.conf:settings", namespace="CELERY")
app.autodiscover_tasks()
