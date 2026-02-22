"""
CareVerify - Celery Worker Entry Point

Start workers:
  celery -A celery_worker.celery worker --loglevel=info -Q ai_processing -c 2
  celery -A celery_worker.celery worker --loglevel=info -Q notifications,audit,default -c 4

Start beat (scheduler):
  celery -A celery_worker.celery beat --loglevel=info
"""

import os
from app import create_app
from app.extensions import celery_app

env = os.environ.get("FLASK_ENV", "production")
app = create_app(env)

# Register periodic tasks
from config.celery_schedule import CELERYBEAT_SCHEDULE
celery_app.conf.beat_schedule = CELERYBEAT_SCHEDULE

# Import all tasks to ensure they're registered
import app.tasks.ai_tasks
import app.tasks.maintenance_tasks