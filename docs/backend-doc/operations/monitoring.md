# Monitoring and Observability

**Purpose:** Documentation for monitoring, metrics collection, alerting, and observability strategies.

**Scope:** Metrics collection strategy, critical metrics, dashboard setup, alerting rules, log aggregation, and distributed tracing.

---

## Overview

This document outlines the monitoring and observability strategy for the RIDP Form Platform, ensuring proactive system health monitoring, performance tracking, and incident response capabilities.

**Target Audience:** DevOps engineers, SREs, system administrators

---

## Monitoring Strategy

### Monitoring Stack

```
┌─────────────────────────────────────────────────────────┐
│                    Monitoring Stack                    │
├─────────────────────────────────────────────────────────┤
│                                                         │
│  ┌─────────────┐     ┌─────────────┐               │
│  │  Prometheus  │────▶│  Grafana    │               │
│  │  (Metrics)   │     │  (Dashboards)│              │
│  └─────────────┘     └─────────────┘               │
│         │                                            │
│         ▼                                            │
│  ┌─────────────┐     ┌─────────────┐               │
│  │  Alertmanager│────▶│ PagerDuty   │               │
│  │  (Alerting) │     │  (On-call)   │              │
│  └─────────────┘     └─────────────┘               │
│         │                                            │
│         ▼                                            │
│  ┌─────────────┐     ┌─────────────┐               │
│  │  Loki       │     │  Sentry     │               │
│  │  (Logs)     │     │  (Errors)   │              │
│  └─────────────┘     └─────────────┘               │
│                                                         │
└─────────────────────────────────────────────────────────┘
```

---

## Metrics Collection

### Flask Metrics

**Prometheus Flask Exporter:**

```python
# utils/metrics.py
from prometheus_client import Counter, Histogram, Gauge, generate_latest

# Request metrics
http_requests_total = Counter(
    'http_requests_total',
    'Total HTTP requests',
    ['method', 'endpoint', 'status']
)

http_request_duration_seconds = Histogram(
    'http_request_duration_seconds',
    'HTTP request latency',
    ['method', 'endpoint'],
    buckets=[0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0]
)

# Database metrics
db_query_duration_seconds = Histogram(
    'db_query_duration_seconds',
    'Database query latency',
    buckets=[0.001, 0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0]
)

db_connections_active = Gauge(
    'db_connections_active',
    'Active database connections'
)

db_query_total = Counter(
    'db_query_total',
    'Total database queries',
    ['collection', 'operation']
)

# Cache metrics
cache_hits_total = Counter('cache_hits_total', 'Cache hits', ['cache'])
cache_misses_total = Counter('cache_misses_total', 'Cache misses', ['cache'])
cache_latency_seconds = Histogram(
    'cache_latency_seconds',
    'Cache latency',
    ['cache', 'operation']
)

# Security metrics
waf_blocks_total = Counter(
    'waf_blocks_total',
    'WAF blocks',
    ['attack_type', 'source']
)

rate_limit_violations_total = Counter(
    'rate_limit_violations_total',
    'Rate limit violations',
    ['endpoint', 'limit_type']
)

auth_failures_total = Counter(
    'auth_failures_total',
    'Authentication failures',
    ['method']
)

# Business metrics
forms_total = Gauge('forms_total', 'Total forms')
forms_published_total = Gauge('forms_published_total', 'Total published forms')
responses_total = Counter('responses_total', 'Total form responses', ['form_id'])
```

**Middleware Integration:**

```python
# middleware/metrics_middleware.py
from utils.metrics import (
    http_requests_total,
    http_request_duration_seconds
)
from prometheus_client import make_wsgi_app

@app.before_request
def before_request():
    request.start_time = time.time()

@app.after_request
def after_request(response):
    duration = time.time() - request.start_time

    # Record request metrics
    http_requests_total.labels(
        method=request.method,
        endpoint=request.path,
        status=response.status_code
    ).inc()

    http_request_duration_seconds.labels(
        method=request.method,
        endpoint=request.path
    ).observe(duration)

    return response

# Prometheus endpoint
app.wsgi_app = make_wsgi_app(app.wsgi_app)
```

### Database Metrics

**MongoDB Metrics:**

```python
# utils/mongodb_metrics.py
from mongoengine import connection
from prometheus_client import Gauge

db_connections_active = Gauge(
    'db_connections_active',
    'Active database connections'
)

def collect_mongodb_metrics():
    """Collect MongoDB metrics."""
    # Get connection pool stats
    conn = connection.get_db()
    pool = conn.client._MongoClient__pool

    db_connections_active.set(pool.available + pool.in_use)
```

### Cache Metrics

**Redis Metrics:**

```python
# utils/redis_metrics.py
import redis
from prometheus_client import Gauge, Counter

redis_memory_used = Gauge('redis_memory_used_bytes', 'Redis memory used')
redis_keys_total = Gauge('redis_keys_total', 'Total Redis keys')
redis_connected_clients = Gauge('redis_connected_clients', 'Connected Redis clients')

cache_hits_total = Counter('cache_hits_total', 'Cache hits')
cache_misses_total = Counter('cache_misses_total', 'Cache misses')

def collect_redis_metrics():
    """Collect Redis metrics."""
    info = redis_client.info()

    redis_memory_used.set(info['used_memory'])
    redis_keys_total.set(info['db0']['keys'])
    redis_connected_clients.set(info['connected_clients'])
```

### System Metrics

**Node Exporter:**

```yaml
# docker-compose.yml
services:
  node_exporter:
    image: prom/node-exporter:latest
    container_name: node_exporter
    ports:
      - "9100:9100"
    command:
      - '--path.procfs=/host/proc'
      - '--path.sysfs=/host/sys'
      - '--collector.filesystem.mount-points-exclude=^/(sys|proc|dev|host|etc)($|/)'
    volumes:
      - /proc:/host/proc:ro
      - /sys:/host/sys:ro
      - /:/rootfs:ro
```

---

## Critical Metrics

### Health Metrics

| Metric | Type | Alert Condition | Severity |
|--------|------|-----------------|----------|
| Application uptime | Gauge | < 99.9% | Critical |
| Error rate | Rate | > 1% | Critical |
| Response time (p95) | Histogram | > 1s | Warning |
| Response time (p99) | Histogram | > 2s | Critical |

### Infrastructure Metrics

| Metric | Type | Alert Condition | Severity |
|--------|------|-----------------|----------|
| CPU usage | Gauge | > 80% | Warning |
| CPU usage | Gauge | > 95% | Critical |
| Memory usage | Gauge | > 80% | Warning |
| Memory usage | Gauge | > 95% | Critical |
| Disk usage | Gauge | > 80% | Warning |
| Disk usage | Gauge | > 95% | Critical |
| Network I/O | Gauge | > 80% bandwidth | Warning |

### Database Metrics

| Metric | Type | Alert Condition | Severity |
|--------|------|-----------------|----------|
| DB connections | Gauge | > 80% max | Warning |
| DB connections | Gauge | > 95% max | Critical |
| Query latency (p95) | Histogram | > 100ms | Warning |
| Query latency (p99) | Histogram | > 200ms | Critical |
| Replication lag | Gauge | > 10s | Warning |
| Replication lag | Gauge | > 60s | Critical |

### Cache Metrics

| Metric | Type | Alert Condition | Severity |
|--------|------|-----------------|----------|
| Cache hit rate | Gauge | < 80% | Warning |
| Cache memory | Gauge | > 80% | Warning |
| Cache memory | Gauge | > 95% | Critical |
| Cache latency (p95) | Histogram | > 10ms | Warning |

### Security Metrics

| Metric | Type | Alert Condition | Severity |
|--------|------|-----------------|----------|
| WAF blocks | Rate | > 100/min | Warning |
| WAF blocks | Rate | > 1000/min | Critical |
| Rate limit violations | Rate | > 50/min | Warning |
| Auth failures | Rate | > 10/min | Warning |
| Auth failures | Rate | > 100/min | Critical |

---

## Dashboard Setup

### Grafana Dashboards

**1. Application Overview Dashboard:**

```json
{
  "dashboard": {
    "title": "Application Overview",
    "panels": [
      {
        "title": "Request Rate",
        "targets": [
          {
            "expr": "rate(http_requests_total[5m])"
          }
        ]
      },
      {
        "title": "Error Rate",
        "targets": [
          {
            "expr": "rate(http_requests_total{status=~\"5..\"}[5m])"
          }
        ]
      },
      {
        "title": "Response Time (p95)",
        "targets": [
          {
            "expr": "histogram_quantile(0.95, rate(http_request_duration_seconds_bucket[5m]))"
          }
        ]
      }
    ]
  }
}
```

**2. Database Dashboard:**

```json
{
  "dashboard": {
    "title": "Database Metrics",
    "panels": [
      {
        "title": "Active Connections",
        "targets": [
          {
            "expr": "db_connections_active"
          }
        ]
      },
      {
        "title": "Query Latency (p95)",
        "targets": [
          {
            "expr": "histogram_quantile(0.95, rate(db_query_duration_seconds_bucket[5m]))"
          }
        ]
      }
    ]
  }
}
```

**3. Security Dashboard:**

```json
{
  "dashboard": {
    "title": "Security Overview",
    "panels": [
      {
        "title": "WAF Blocks",
        "targets": [
          {
            "expr": "sum(rate(waf_blocks_total[5m])) by (attack_type)"
          }
        ]
      },
      {
        "title": "Rate Limit Violations",
        "targets": [
          {
            "expr": "sum(rate(rate_limit_violations_total[5m])) by (endpoint)"
          }
        ]
      }
    ]
  }
}
```

---

## Alerting Rules

### Prometheus Alert Rules

**File:** `prometheus/alerts.yml`

```yaml
groups:
  - name: application_alerts
    rules:
      - alert: HighErrorRate
        expr: |
          rate(http_requests_total{status=~"5.."}[5m]) > 0.1
        for: 5m
        labels:
          severity: critical
          team: backend
        annotations:
          summary: "High error rate detected"
          description: "Error rate is {{ $value }} errors/sec"

      - alert: HighLatency
        expr: |
          histogram_quantile(0.95, rate(http_request_duration_seconds_bucket[5m])) > 1
        for: 10m
        labels:
          severity: warning
          team: backend
        annotations:
          summary: "High latency detected"
          description: "P95 latency is {{ $value }} seconds"

      - alert: ApplicationDown
        expr: up{job="backend"} == 0
        for: 1m
        labels:
          severity: critical
          team: backend
        annotations:
          summary: "Application is down"
          description: "Backend application is not responding"

  - name: database_alerts
    rules:
      - alert: DatabaseConnectionsHigh
        expr: |
          db_connections_active > 80
        for: 5m
        labels:
          severity: warning
          team: database
        annotations:
          summary: "High database connection usage"
          description: "Database connections at {{ $value }}% of max"

      - alert: DatabaseDown
        expr: up{job="mongodb"} == 0
        for: 1m
        labels:
          severity: critical
          team: database
        annotations:
          summary: "Database is down"
          description: "MongoDB is not responding"

      - alert: HighQueryLatency
        expr: |
          histogram_quantile(0.95, rate(db_query_duration_seconds_bucket[5m])) > 0.1
        for: 10m
        labels:
          severity: warning
          team: database
        annotations:
          summary: "High database query latency"
          description: "P95 query latency is {{ $value }} seconds"

  - name: cache_alerts
    rules:
      - alert: CacheDown
        expr: up{job="redis"} == 0
        for: 1m
        labels:
          severity: critical
          team: cache
        annotations:
          summary: "Cache is down"
          description: "Redis is not responding"

      - alert: LowCacheHitRate
        expr: |
          rate(cache_hits_total[5m]) / (rate(cache_hits_total[5m]) + rate(cache_misses_total[5m])) < 0.8
        for: 15m
        labels:
          severity: warning
          team: cache
        annotations:
          summary: "Low cache hit rate"
          description: "Cache hit rate is {{ $value }}%"

  - name: security_alerts
    rules:
      - alert: HighWAFBlocks
        expr: |
          sum(rate(waf_blocks_total[5m])) > 100
        for: 5m
        labels:
          severity: warning
          team: security
        annotations:
          summary: "High WAF block rate"
          description: "{{ $value }} blocks/sec"

      - alert: CriticalWAFBlocks
        expr: |
          sum(rate(waf_blocks_total[5m])) > 1000
        for: 1m
        labels:
          severity: critical
          team: security
        annotations:
          summary: "Critical WAF block rate"
          description: "{{ $value }} blocks/sec"

      - alert: HighAuthFailures
        expr: |
          sum(rate(auth_failures_total[5m])) > 10
        for: 5m
        labels:
          severity: warning
          team: security
        annotations:
          summary: "High authentication failure rate"
          description: "{{ $value }} failures/sec"
```

### Alert Routing

**Alertmanager Configuration:**

```yaml
# alertmanager.yml
global:
  resolve_timeout: 5m
  slack_api_url: 'https://hooks.slack.com/services/YOUR/SLACK/WEBHOOK'

route:
  group_by: ['alertname', 'severity']
  group_wait: 10s
  group_interval: 10s
  repeat_interval: 1h
  receiver: 'default'

  routes:
    - match:
        severity: critical
      receiver: 'pagerduty'
      continue: true

    - match:
        severity: warning
      receiver: 'slack'

receivers:
  - name: 'default'
    slack_configs:
      - channel: '#alerts'

  - name: 'pagerduty'
    pagerduty_configs:
      - service_key: 'YOUR_PAGERDUTY_SERVICE_KEY'
        severity: 'critical'

  - name: 'slack'
    slack_configs:
      - channel: '#alerts'
        send_resolved: true
```

---

## Log Aggregation

### Loki Configuration

**Promtail Configuration:**

```yaml
# promtail-config.yml
server:
  http_listen_port: 9080

positions:
  filename: /tmp/positions.yaml

clients:
  - url: http://loki:3100/loki/api/v1/push

scrape_configs:
  - job_name: backend
    static_configs:
      - targets:
          - localhost
        labels:
          job: backend
          __path__: /var/log/backend/*.log
```

### Log Formatting

**Structured Logging:**

```python
# config/logging.py
import structlog

structlog.configure(
    processors=[
        structlog.stdlib.filter_by_level,
        structlog.stdlib.add_logger_name,
        structlog.stdlib.add_log_level,
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.StackInfoRenderer(),
        structlog.processors.format_exc_info,
        structlog.processors.JSONRenderer()
    ],
    context_class=dict,
    logger_factory=structlog.stdlib.LoggerFactory(),
    cache_logger_on_first_use=True,
)

logger = structlog.get_logger()
```

---

## Distributed Tracing

### OpenTelemetry Setup

**Initialization:**

```python
# config/tracing.py
from opentelemetry import trace
from opentelemetry import metrics
from opentelemetry.exporter.jaeger.thrift import JaegerExporter
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.metrics import MeterProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor

def init_tracing():
    """Initialize distributed tracing."""
    # Set up tracing
    trace.set_tracer_provider(TracerProvider())
    tracer = trace.get_tracer(__name__)

    # Export to Jaeger
    jaeger_exporter = JaegerExporter(
        agent_host_name="jaeger",
        agent_port=6831,
    )

    span_processor = BatchSpanProcessor(jaeger_exporter)
    trace.get_tracer_provider().add_span_processor(span_processor)

    return tracer
```

**Tracing Middleware:**

```python
# middleware/tracing_middleware.py
from opentelemetry import trace

tracer = trace.get_tracer(__name__)

@app.before_request
def before_request():
    # Create span for request
    span = tracer.start_span(request.path)
    request.span = span

    # Add attributes
    span.set_attribute("http.method", request.method)
    span.set_attribute("http.url", request.url)
    span.set_attribute("http.headers", dict(request.headers))

@app.after_request
def after_request(response):
    # End span
    if hasattr(request, 'span'):
        request.span.set_attribute("http.status_code", response.status_code)
        request.span.end()

    return response
```

---

## Health Checks

### Synthetic Monitoring

**Uptime Robot / Pingdom:**

```python
# routes/v1/health_route.py
@bp.route("/health", methods=["GET"])
def health_check():
    """Health check endpoint for synthetic monitoring."""
    checks = {
        "status": "healthy",
        "timestamp": datetime.utcnow().isoformat(),
        "checks": {
            "database": check_database(),
            "cache": check_cache(),
            "disk": check_disk(),
        }
    }

    status_code = 200 if all(
        check == "ok" for check in checks["checks"].values()
    ) else 503

    return jsonify(checks), status_code

def check_database():
    """Check database connection."""
    try:
        User.objects().count()
        return "ok"
    except Exception:
        return "error"

def check_cache():
    """Check cache connection."""
    try:
        redis_client.ping()
        return "ok"
    except Exception:
        return "error"

def check_disk():
    """Check disk space."""
    disk_usage = psutil.disk_usage("/")
    if disk_usage.percent > 90:
        return "warning"
    return "ok"
```

---

## Best Practices

### 1. Define SLOs and SLAs

```python
# SLOs (Service Level Objectives)
SLO_ERROR_RATE = 0.01  # 1% error rate
SLO_LATENCY_P95 = 1.0  # 1 second
SLO_AVAILABILITY = 99.9  # 99.9% uptime

# SLAs (Service Level Agreements)
SLA_ERROR_RATE = 0.001  # 0.1% error rate
SLA_LATENCY_P95 = 0.5  # 500ms
SLA_AVAILABILITY = 99.99  # 99.99% uptime
```

### 2. Monitor the Right Metrics

```python
# CORRECT - Monitor business metrics
responses_total.labels(form_id=form_id).inc()

# CORRECT - Monitor system metrics
db_connections_active.set(pool.available)

# WRONG - Monitor everything
# Too many metrics make it hard to find issues
```

### 3. Set Appropriate Alert Thresholds

```python
# CORRECT - Realistic thresholds
alert if error_rate > 0.01  # 1% error rate

# WRONG - Too sensitive
alert if error_rate > 0.0001  # 0.01% error rate (too many false positives)

# WRONG - Not sensitive enough
alert if error_rate > 0.5  # 50% error rate (too late)
```

### 4. Use Meaningful Labels

```python
# CORRECT - Meaningful labels
http_requests_total.labels(method="POST", endpoint="/api/v1/forms", status="201").inc()

# WRONG - Generic labels
http_requests_total.labels(request="request1", response="response1").inc()
```

---

## Configuration Reference

### Prometheus Configuration

```yaml
# prometheus.yml
global:
  scrape_interval: 15s
  evaluation_interval: 15s

scrape_configs:
  - job_name: 'backend'
    static_configs:
      - targets: ['backend:5000']

  - job_name: 'node_exporter'
    static_configs:
      - targets: ['node_exporter:9100']

  - job_name: 'mongodb'
    static_configs:
      - targets: ['mongodb:27017']

  - job_name: 'redis'
    static_configs:
      - targets: ['redis:6379']
```

### Grafana Configuration

```yaml
# grafana.yml
version: '3.8'
services:
  grafana:
    image: grafana/grafana:latest
    ports:
      - "3000:3000"
    environment:
      - GF_SECURITY_ADMIN_PASSWORD=admin
      - GF_INSTALL_PLUGINS=grafana-piechart-panel
    volumes:
      - grafana-data:/var/lib/grafana
      - ./grafana/provisioning:/etc/grafana/provisioning
```

---

## References

- [Prometheus Documentation](https://prometheus.io/docs/)
- [Grafana Documentation](https://grafana.com/docs/)
- [Alertmanager Documentation](https://prometheus.io/docs/alerting/latest/alertmanager/)
- [OpenTelemetry Documentation](https://opentelemetry.io/docs/)
- [Google SRE Book](https://sre.google/sre-book/table-of-contents/)
- [NIST SP 800-37 - Risk Management Framework](https://csrc.nist.gov/publications/detail/sp/800-37/rev-2/final)
