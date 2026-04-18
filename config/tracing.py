"""
config/tracing.py
OpenTelemetry configuration for distributed tracing.
"""
import os
from opentelemetry import trace
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor, ConsoleSpanExporter
from opentelemetry.instrumentation.flask import FlaskInstrumentor
from opentelemetry.instrumentation.celery import CeleryInstrumentor
from opentelemetry.sdk.resources import Resource
from config.settings import settings

def init_tracing(app=None):
    """Initializes OpenTelemetry tracing."""
    resource = Resource(attributes={
        "service.name": settings.APP_NAME,
        "environment": settings.APP_ENV
    })

    provider = TracerProvider(resource=resource)
    
    # Keep tracing available, but avoid dumping raw span JSON into the console
    # unless explicitly requested for local debugging.
    if os.getenv("OTEL_CONSOLE_SPANS", "false").lower() in {"1", "true", "yes"}:
        processor = BatchSpanProcessor(ConsoleSpanExporter())
        provider.add_span_processor(processor)
    
    trace.set_tracer_provider(provider)

    if app:
        FlaskInstrumentor().instrument_app(app)

def init_celery_tracing():
    """Instruments Celery for tracing."""
    CeleryInstrumentor().instrument()
