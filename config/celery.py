from celery import Celery
from kombu import Queue, Exchange
from config.settings import settings


def get_redis_url(db):
    if settings.REDIS_PASSWORD:
        return f"redis://:{settings.REDIS_PASSWORD}@{settings.REDIS_HOST}:{settings.REDIS_PORT}/{db}"
    return f"redis://{settings.REDIS_HOST}:{settings.REDIS_PORT}/{db}"


broker_url = get_redis_url(settings.CELERY_BROKER_DB)
result_backend = get_redis_url(settings.CELERY_RESULT_DB)

celery_app = Celery(
    "forms_backend",
    broker=broker_url,
    backend=result_backend,
    include=[
        "tasks.notification_tasks",
        "tasks.services",
        "tasks.form_tasks",
        "tasks.ai_tasks",
    ],
)

# ── Tracing ────────────────────────────────────────────────────────────
from config.tracing import init_celery_tracing
init_celery_tracing()

# Advanced Configuration
celery_app.conf.update(
    # Serialization
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    # Timezone
    timezone="UTC",
    enable_utc=True,
    # Task execution settings
    task_time_limit=3600,  # Hard limit (1 hour)
    task_soft_time_limit=300,  # Soft limit (5 minutes)
    worker_concurrency=4,  # Number of concurrent worker processes
    # Reliability
    task_acks_late=True,  # Task is acknowledged after execution
    task_reject_on_worker_lost=True,  # Re-queue task if worker crashes
    task_track_started=True,
    # Retry policy for broker connection
    broker_connection_retry_on_startup=True,
    # Result settings
    result_expires=86400,  # Results expire in 24 hours
    # Task routing and priority setting
    task_queues=(
        Queue(
            "celery",
            Exchange("celery"),
            routing_key="celery",
            queue_arguments={"x-max-priority": 10},
        ),
        Queue(
            "sms",
            Exchange("sms"),
            routing_key="sms",
            queue_arguments={"x-max-priority": 10},
        ),
        Queue(
            "mail",
            Exchange("mail"),
            routing_key="mail",
            queue_arguments={"x-max-priority": 10},
        ),
        Queue(
            "ehospital",
            Exchange("ehospital"),
            routing_key="ehospital",
            queue_arguments={"x-max-priority": 10},
        ),
        Queue(
            "request",
            Exchange("request"),
            routing_key="request",
            queue_arguments={"x-max-priority": 10},
        ),
        Queue(
            "employee",
            Exchange("employee"),
            routing_key="employee",
            queue_arguments={"x-max-priority": 10},
        ),
    ),
    task_default_queue="celery",
    task_default_exchange="celery",
    task_default_routing_key="celery",
    task_routes={
        "tasks.form_tasks.async_clone_form": {"queue": "celery"},
        "tasks.form_tasks.async_publish_form": {"queue": "celery"},
        "tasks.form_tasks.async_recalculate_materialized_view": {"queue": "celery"},
        "tasks.ai_tasks.async_generate_form_summary": {"queue": "celery"},
        "tasks.ai_tasks.async_index_response_vector": {"queue": "celery"},
        "tasks.ai_tasks.async_export_to_olap": {"queue": "celery"},
        "tasks.services.process_sms": {"queue": "sms"},
        "tasks.services.process_mail": {"queue": "mail"},
        "tasks.services.process_ehospital": {"queue": "ehospital"},
        "tasks.services.process_request": {"queue": "request"},
        "tasks.services.process_employee": {"queue": "employee"},
    },
    broker_transport_options={
        "priority_steps": list(range(10)),
        "queue_order_strategy": "priority",
    },
)


_flask_app = None


def get_flask_app():
    global _flask_app
    if _flask_app is None:
        from app import create_app

        _flask_app = create_app()
    return _flask_app


class FlaskContextTask(celery_app.Task):
    abstract = True

    def __call__(self, *args, **kwargs):
        with get_flask_app().app_context():
            return super().__call__(*args, **kwargs)


celery_app.Task = FlaskContextTask
