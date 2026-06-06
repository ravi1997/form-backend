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
        "tasks.report_tasks",
        "tasks.gdpr_tasks",
        "tasks.compliance_tasks",
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
        Queue(
            "analytics_write",
            Exchange("analytics_write"),
            routing_key="analytics_write",
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
        "tasks.ai_tasks.async_export_to_olap": {"queue": "analytics_write"},
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


class ReliabilityTask(celery_app.Task):
    abstract = True

    def __call__(self, *args, **kwargs):
        with get_flask_app().app_context():
            return super().__call__(*args, **kwargs)

    def on_failure(self, exc, task_id, args, kwargs, einfo):
        super().on_failure(exc, task_id, args, kwargs, einfo)
        retries = self.request.retries if self.request.retries is not None else 0
        max_retries = self.max_retries if self.max_retries is not None else 0
        if retries >= max_retries:
            from logger.unified_logger import error_logger, audit_logger
            error_logger.error(
                f"Task {self.name} [{task_id}] failed permanently after {retries} retries: {exc}",
                exc_info=True
            )
            try:
                from models.DeadLetterTask import DeadLetterTask
                import json
                try:
                    s_args = json.loads(json.dumps(args, default=str))
                    s_kwargs = json.loads(json.dumps(kwargs, default=str))
                except Exception:
                    s_args = {"raw": str(args)}
                    s_kwargs = {"raw": str(kwargs)}

                org_id = kwargs.get("organization_id") if isinstance(kwargs, dict) else None
                if not org_id and self.request.headers:
                    org_id = self.request.headers.get("organization_id")

                dlq = DeadLetterTask(
                    task_id=task_id,
                    task_name=self.name,
                    args=s_args,
                    kwargs=s_kwargs,
                    exception=str(exc),
                    traceback=str(einfo),
                    organization_id=org_id or "system"
                )
                dlq.save()
                audit_logger.info(f"Task {self.name} [{task_id}] routed to dead-letter storage.")
            except Exception as dlq_err:
                error_logger.critical(f"Failed to save DeadLetterTask for task {task_id}: {dlq_err}", exc_info=True)


celery_app.Task = ReliabilityTask



# ── Context and Tracing Propagation Signals ─────────────────────────────
from celery.signals import before_task_publish, task_prerun
from flask_jwt_extended import current_user


@before_task_publish.connect
def before_task_publish_handler(headers=None, body=None, **kwargs):
    from flask import g, has_request_context
    if has_request_context():
        # Propagate request correlation ID
        req_id = getattr(g, "request_id", None)
        if req_id and headers:
            headers["request_id"] = req_id

        # Propagate tenant context organization_id
        org_id = None
        try:
            if current_user:
                org_id = getattr(current_user, "organization_id", None)
        except Exception:
            pass
        if org_id and headers:
            headers["organization_id"] = org_id


@task_prerun.connect
def task_prerun_handler(task, **kwargs):
    from flask import g
    request = task.request
    req_id = request.headers.get("request_id") if request.headers else None
    org_id = request.headers.get("organization_id") if request.headers else None

    if req_id:
        g.request_id = req_id
    if org_id:
        g.tenant_db_alias = f"conn_{org_id}"
