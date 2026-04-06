# Deployment Security

**Purpose:** Documentation for production deployment security hardening, infrastructure security, and operational security baselines.

**Scope:** TLS/SSL configuration, secrets management, network security, container security, infrastructure monitoring, and compliance logging.

---

## Overview

This document outlines security hardening procedures for deploying the RIDP Form Platform to production environments. It covers infrastructure security, secrets management, container security, monitoring, and compliance requirements.

**Target Audience:** DevOps engineers, system administrators, security engineers

---

## Infrastructure Security

### Network Security

**1. VPC Configuration**

```yaml
# AWS VPC Configuration
VPC:
  CIDR: 10.0.0.0/16

  Subnets:
    Public:
      CIDR: 10.0.1.0/24
      AvailabilityZones: [us-east-1a, us-east-1b]
      RouteTable:
        - Destination: 0.0.0.0/0
          Target: Internet Gateway

    Private:
      CIDR: 10.0.2.0/24
      AvailabilityZones: [us-east-1a, us-east-1b]
      RouteTable:
        - Destination: 0.0.0.0/0
          Target: NAT Gateway

    Database:
      CIDR: 10.0.3.0/24
      AvailabilityZones: [us-east-1a, us-east-1b]
      RouteTable:
        - No internet access

  SecurityGroups:
    WebServer:
      Ingress:
        - Protocol: TCP
          Port: 443
          Source: 0.0.0.0/0
        - Protocol: TCP
          Port: 22
          Source: VPN_CIDR
      Egress:
        - Protocol: ALL
          Destination: 0.0.0.0/0

    Database:
      Ingress:
        - Protocol: TCP
          Port: 27017
          Source: WebServer_CIDR
      Egress:
        - None
```

**2. Network Segmentation**

```
Internet → [Public Subnet: Load Balancer]
           ↓
    [Private Subnet: Application Servers]
           ↓
    [Database Subnet: MongoDB, Redis]
```

**3. Firewall Rules**

```bash
# iptables rules for application servers
# Allow only necessary traffic
iptables -A INPUT -p tcp --dport 443 -j ACCEPT  # HTTPS
iptables -A INPUT -p tcp --dport 22 -s VPN_IP -j ACCEPT  # SSH from VPN
iptables -A INPUT -j DROP  # Drop all other traffic

# Allow outbound traffic
iptables -A OUTPUT -j ACCEPT
```

### TLS/SSL Configuration

**Nginx Configuration:**
```nginx
# /etc/nginx/conf.d/backend.conf
server {
    listen 443 ssl http2;
    server_name api.example.com;

    # SSL Configuration
    ssl_certificate /etc/ssl/certs/example.com.crt;
    ssl_certificate_key /etc/ssl/private/example.com.key;
    ssl_protocols TLSv1.2 TLSv1.3;
    ssl_ciphers 'ECDHE-ECDSA-AES128-GCM-SHA256:ECDHE-RSA-AES128-GCM-SHA256';
    ssl_prefer_server_ciphers on;
    ssl_session_timeout 1d;
    ssl_session_cache shared:SSL:10m;
    ssl_stapling on;
    ssl_stapling_verify on;

    # Security Headers
    add_header Strict-Transport-Security "max-age=31536000; includeSubDomains; preload" always;
    add_header X-Frame-Options "DENY" always;
    add_header X-Content-Type-Options "nosniff" always;
    add_header X-XSS-Protection "1; mode=block" always;
    add_header Content-Security-Policy "default-src 'self'" always;

    # Proxy to Flask application
    location /form/ {
        proxy_pass http://localhost:5000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
}
```

**SSL Certificate Management:**
```bash
# Use Let's Encrypt for free certificates
certbot --nginx -d api.example.com

# Or use commercial certificate
openssl req -new -newkey rsa:2048 -nodes -keyout example.com.key -out example.com.csr
```

---

## Secrets Management

### Environment Variables

**Never commit secrets to version control:**

```bash
# .gitignore
.env
.env.local
.env.*.local
*.key
*.pem
secrets/
```

**Use environment-specific config:**

```python
# config/settings.py
class Settings(BaseSettings):
    # Load from environment
    JWT_SECRET_KEY: str = Field(...)
    MONGODB_URI: str = Field(...)
    REDIS_PASSWORD: Optional[str] = None

    @model_validator(mode="after")
    def validate_secrets(self) -> "Settings":
        # Enforce secure secrets in production
        if self.APP_ENV != "development":
            if self.JWT_SECRET_KEY == "super-secret-key-change-me":
                raise ValueError("JWT_SECRET_KEY must be changed for production")

            if "localhost" in self.MONGODB_URI:
                raise ValueError("MONGODB_URI must not point to localhost in production")

        return self
```

### AWS Secrets Manager

**Store secrets in AWS Secrets Manager:**

```python
# config/secrets.py
import boto3

def get_secret(secret_name: str) -> str:
    """Retrieve secret from AWS Secrets Manager."""
    client = boto3.client('secretsmanager')

    try:
        response = client.get_secret_value(SecretId=secret_name)
        secret = response['SecretString']

        if secret:
            return secret
        else:
            # Secret is binary
            return response['SecretBinary']

    except Exception as e:
        raise Exception(f"Failed to retrieve secret {secret_name}: {str(e)}")

# Usage
JWT_SECRET_KEY = get_secret("ridp-form/jwt-secret")
MONGODB_URI = get_secret("ridp-form/mongodb-uri")
```

**Rotate secrets regularly:**

```python
# scripts/rotate_secrets.py
def rotate_jwt_secret():
    """Rotate JWT secret."""
    import secrets

    # Generate new secret
    new_secret = secrets.token_hex(32)

    # Update in Secrets Manager
    client = boto3.client('secretsmanager')
    client.update_secret(
        SecretId="ridp-form/jwt-secret",
        SecretString=new_secret
    )

    # Restart application to load new secret
    restart_application()

    print(f"JWT secret rotated: {datetime.utcnow()}")
```

### HashiCorp Vault (Alternative)

```python
import hvac

def get_secret_from_vault(path: str, key: str) -> str:
    """Retrieve secret from HashiCorp Vault."""
    client = hvac.Client(
        url='https://vault.example.com',
        token=get_vault_token()
    )

    secret = client.read(path)
    return secret['data'][key]
```

---

## Container Security

### Docker Image Security

**1. Use Minimal Base Image**

```dockerfile
# CORRECT - Use minimal base
FROM python:3.11-slim

# WRONG - Use full image
FROM python:3.11
```

**2. Scan Images for Vulnerabilities**

```bash
# Scan with Trivy
trivy image ridp-form-backend:latest

# Scan with Clair
clairctl analyze ridp-form-backend:latest

# Scan with Docker Bench
docker run --net host --pid host --userns host --cap-add audit_control \
    -e DOCKER_CONTENT_TRUST=$DOCKER_CONTENT_TRUST \
    -v /var/lib:/var/lib \
    -v /var/run/docker.sock:/var/run/docker.sock \
    -v /usr/lib/systemd:/usr/lib/systemd \
    -v /etc:/etc --label docker_bench_security \
    docker/docker-bench-security
```

**3. Fix Vulnerabilities**

```bash
# Update base image
FROM python:3.11.1-slim  # Update to latest patch

# Or use Alpine with security updates
FROM alpine:3.18
RUN apk add --no-cache --update python3
```

### Dockerfile Best Practices

```dockerfile
# Multi-stage build
FROM python:3.11-slim as builder

WORKDIR /app
COPY requirements.txt .
RUN pip install --user --no-cache-dir -r requirements.txt

# Final stage
FROM python:3.11-slim

# Create non-root user
RUN useradd -m -u 1000 appuser

# Install runtime dependencies only
COPY --from=builder /root/.local /root/.local

# Set working directory
WORKDIR /app
COPY . .

# Set permissions
RUN chown -R appuser:appuser /app
USER appuser

# Expose only necessary ports
EXPOSE 5000

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD curl -f http://localhost:5000/health || exit 1

# Run application
CMD ["gunicorn", "--bind", "0.0.0.0:5000", "--workers", "4", "app:app"]
```

### Container Runtime Security

**1. Resource Limits**

```yaml
# docker-compose.yml
services:
  backend:
    image: ridp-form-backend:latest
    deploy:
      resources:
        limits:
          cpus: '2'
          memory: 2G
        reservations:
          cpus: '1'
          memory: 1G
    restart_policy:
      condition: on-failure
      max_attempts: 3
```

**2. Security Options**

```yaml
# docker-compose.yml
services:
  backend:
    security_opt:
      - no-new-privileges:true
    read_only: true
    tmpfs:
      - /tmp
    cap_drop:
      - ALL
    cap_add:
      - NET_BIND_SERVICE
```

**3. Network Isolation**

```yaml
# docker-compose.yml
services:
  backend:
    networks:
      - backend-network
    depends_on:
      - mongodb
      - redis

  mongodb:
    networks:
      - database-network

  redis:
    networks:
      - database-network

networks:
  backend-network:
    driver: bridge
  database-network:
    driver: bridge
    internal: true  # No internet access
```

---

## Infrastructure Monitoring

### Health Checks

**Application Health Check:**

```python
# routes/v1/health_route.py
@bp.route("/health", methods=["GET"])
def health_check():
    """Health check endpoint."""
    checks = {
        "status": "healthy",
        "timestamp": datetime.utcnow().isoformat(),
        "checks": {}
    }

    # Check database connection
    try:
        User.objects().count()
        checks["checks"]["database"] = "ok"
    except Exception:
        checks["checks"]["database"] = "error"
        checks["status"] = "degraded"

    # Check cache connection
    try:
        redis_client.ping()
        checks["checks"]["cache"] = "ok"
    except Exception:
        checks["checks"]["cache"] = "error"
        checks["status"] = "degraded"

    # Check disk space
    disk_usage = psutil.disk_usage("/")
    if disk_usage.percent > 90:
        checks["checks"]["disk"] = "warning"
        checks["status"] = "degraded"
    else:
        checks["checks"]["disk"] = "ok"

    status_code = 200 if checks["status"] == "healthy" else 503
    return jsonify(checks), status_code
```

**Infrastructure Monitoring:**

```yaml
# prometheus/alerts.yml
groups:
  - name: backend_alerts
    rules:
      - alert: HighErrorRate
        expr: rate(http_requests_total{status=~"5.."}[5m]) > 0.1
        for: 5m
        labels:
          severity: critical
        annotations:
          summary: "High error rate detected"

      - alert: HighLatency
        expr: histogram_quantile(0.95, http_request_duration_seconds) > 1
        for: 10m
        labels:
          severity: warning
        annotations:
          summary: "High latency detected"

      - alert: DatabaseDown
        expr: up{job="mongodb"} == 0
        for: 1m
        labels:
          severity: critical
        annotations:
          summary: "Database is down"

      - alert: CacheDown
        expr: up{job="redis"} == 0
        for: 1m
        labels:
          severity: critical
        annotations:
          summary: "Cache is down"
```

### Metrics Collection

**Prometheus Metrics:**

```python
# utils/metrics.py
from prometheus_client import Counter, Histogram, Gauge

# Request metrics
http_requests_total = Counter(
    'http_requests_total',
    'Total HTTP requests',
    ['method', 'endpoint', 'status']
)

http_request_duration_seconds = Histogram(
    'http_request_duration_seconds',
    'HTTP request latency',
    ['method', 'endpoint']
)

# Database metrics
db_query_duration_seconds = Histogram(
    'db_query_duration_seconds',
    'Database query latency'
)

db_connections_active = Gauge(
    'db_connections_active',
    'Active database connections'
)

# Cache metrics
cache_hits_total = Counter('cache_hits_total', 'Cache hits')
cache_misses_total = Counter('cache_misses_total', 'Cache misses')

# Security metrics
waf_blocks_total = Counter(
    'waf_blocks_total',
    'WAF blocks',
    ['attack_type']
)

rate_limit_violations_total = Counter(
    'rate_limit_violations_total',
    'Rate limit violations',
    ['endpoint']
)
```

---

## Compliance Logging

### Audit Trail Requirements

**What to Log:**

```python
# All state-changing operations
audit_logger.info(
    f"User {user.email} created form {form.name} "
    f"(form_id={form_id})"
)

# All authentication events
audit_logger.info(
    f"User {email} logged in from {ip_address}"
)

# All authorization failures
audit_logger.warning(
    f"User {user.email} denied access to {resource} "
    f"(permission: {permission})"
)

# All data exports
audit_logger.info(
    f"User {user.email} exported form {form_id} "
    f"(record_count={count})"
)
```

**Log Retention:**

```python
# Different data types have different retention
AUDIT_LOG_RETENTION = 7 * 365  # 7 years for compliance
ACCESS_LOG_RETENTION = 1 * 365  # 1 year
ERROR_LOG_RETENTION = 90  # 90 days
DEBUG_LOG_RETENTION = 30  # 30 days
```

### Log Forwarding

**Send logs to centralized logging:**

```python
# config/logging.py
import logging
from loggly import LogglyHandler

# Forward to Loggly
loggly_handler = LogglyHandler(
    token=os.environ.get('LOGGLY_TOKEN'),
    tags=['backend', 'production']
)

logger.addHandler(loggly_handler)
```

---

## Security Hardening Checklist

### Pre-Deployment Checklist

- [ ] All secrets stored in Secrets Manager (not in code)
- [ ] TLS/SSL certificates valid and properly configured
- [ ] Security headers enabled (HSTS, CSP, etc.)
- [ ] Firewall rules configured (only necessary ports open)
- [ ] Database access restricted to application servers only
- [ ] Docker images scanned for vulnerabilities
- [ ] Resource limits configured
- [ ] Health checks configured
- [ ] Monitoring and alerting configured
- [ ] Backup and restore procedures tested
- [ ] Rate limiting enabled
- [ ] WAF enabled
- [ ] CORS configured correctly (no wildcards)
- [ ] Log aggregation configured
- [ ] Audit logging enabled
- [ ] Security monitoring enabled
- [ ] Incident response plan documented
- [ ] Team trained on procedures

### Post-Deployment Monitoring

- [ ] Monitor error rates
- [ ] Monitor response times
- [ ] Monitor resource usage
- [ ] Monitor security events
- [ ] Review logs for anomalies
- [ ] Verify backups are running
- [ ] Verify backups are successful
- [ ] Test restore procedures

---

## Best Practices

### 1. Use Infrastructure as Code

```yaml
# CORRECT - IaC (Terraform)
resource "aws_instance" "backend" {
  ami           = "ami-12345678"
  instance_type = "t3.medium"
  security_groups = [aws_security_group.backend.name]
}

# WRONG - Manual configuration
# Create instances in AWS console manually
```

### 2. Encrypt All Sensitive Data

```python
# CORRECT - Encrypted at rest
ENCRYPTION_KEY = get_secret("encryption_key")
encrypted_data = encrypt(data, ENCRYPTION_KEY)

# WRONG - Plain text
# Store sensitive data in plain text
```

### 3. Use Least Privilege

```python
# CORRECT - Minimal permissions
IAM policy: only allow necessary actions

# WRONG - Excessive permissions
IAM policy: allow all actions (*)
```

### 4. Regularly Update Dependencies

```bash
# CORRECT - Regular updates
pip install --upgrade -r requirements.txt

# WRONG - Never update
# Use outdated packages with vulnerabilities
```

### 5. Test Backups Regularly

```python
# CORRECT - Regular testing
schedule.every().month.do(test_restore_procedure)

# WRONG - Never test
# Assume backups work
```

---

## Configuration Reference

### Environment Variables

```bash
# .env.production
APP_ENV=production
MONGODB_URI=mongodb://user:pass@mongodb.internal:27017/forms_db
REDIS_HOST=redis.internal
REDIS_PASSWORD=<from_secrets_manager>
JWT_SECRET_KEY=<from_secrets_manager>
ALLOWED_ORIGINS=["https://example.com"]
SENTRY_DSN=<from_secrets_manager>
```

### Docker Configuration

```yaml
# docker-compose.production.yml
version: '3.8'
services:
  backend:
    image: ridp-form-backend:${VERSION}
    environment:
      - APP_ENV=production
      - MONGODB_URI=${MONGODB_URI}
      - JWT_SECRET_KEY=${JWT_SECRET_KEY}
    deploy:
      resources:
        limits:
          cpus: '2'
          memory: 2G
    networks:
      - backend-network
    depends_on:
      - mongodb
      - redis

networks:
  backend-network:
    external: true
```

---

## References

- [NIST SP 800-53 - Security and Privacy Controls](https://csrc.nist.gov/publications/detail/sp/800-53/rev-5/final)
- [CIS Docker Benchmark](https://www.cisecurity.org/benchmark/docker)
- [AWS Security Best Practices](https://docs.aws.amazon.com/whitepapers/latest/security-overview-aws-services/)
- [OWASP Deployment Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Deployment_Cheat_Sheet.html)
- [PCI DSS Requirement 1 - Install and Maintain Firewalls](https://www.pcisecuritystandards.org/document_library)
