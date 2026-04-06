# Backup and Restore

**Purpose:** Documentation for backup and restore procedures, verification, and disaster recovery.

**Scope:** MongoDB backup, Redis backup, backup frequency, retention policies, restore procedures, and backup testing.

---

## Overview

This document outlines the backup and restore procedures for the RIDP Form Platform, ensuring data protection and business continuity. It covers backup strategies, retention policies, restoration procedures, and verification testing.

**Target Audience:** DevOps engineers, system administrators, database administrators

---

## Backup Strategy

### 3-2-1 Backup Rule

The platform follows the 3-2-1 backup rule:

- **3 copies** of data (1 production + 2 backups)
- **2 different media** (disk + cloud/tape)
- **1 offsite copy** (cloud backup)

### Backup Components

| Component | Type | Frequency | Retention | Location |
|-----------|------|------------|------------|----------|
| MongoDB | Full | Daily | 30 days | Local + Cloud |
| MongoDB | Incremental | Hourly | 7 days | Local |
| Redis | RDB | Hourly | 7 days | Local |
| Redis | AOF | Every write | 24 hours | Local |
| Files | Full | Daily | 30 days | Local + Cloud |
| Logs | Archive | Daily | 90 days | Cloud |

---

## MongoDB Backup Procedures

### Point-in-Time Recovery

**Using mongodump:**
```bash
#!/bin/bash
# scripts/backup_mongodb.sh

# Configuration
MONGODB_URI="mongodb://localhost:27017"
BACKUP_DIR="/backups/mongodb"
TIMESTAMP=$(date +%Y%m%d_%H%M%S)
BACKUP_PATH="${BACKUP_DIR}/${TIMESTAMP}"

# Create backup directory
mkdir -p ${BACKUP_PATH}

# Perform backup
mongodump \
  --uri="${MONGODB_URI}" \
  --out="${BACKUP_PATH}" \
  --gzip \
  --quiet

# Upload to cloud storage
aws s3 sync ${BACKUP_PATH} s3://backups/mongodb/${TIMESTAMP}/

# Clean old backups (keep 30 days)
find ${BACKUP_DIR} -type d -mtime +30 -exec rm -rf {} \;

echo "MongoDB backup completed: ${TIMESTAMP}"
```

**Using MongoDB Atlas (if applicable):**
```bash
# Atlas automated backups
# Configure in Atlas UI:
# - Retention: 30 days
# - Point-in-time recovery: 7 days
# - Snapshot schedule: Daily at 2 AM UTC
```

### Incremental Backups

**Using MongoDB Change Streams:**
```python
# scripts/incremental_backup.py
from pymongo import MongoClient
from datetime import datetime

def incremental_backup():
    """Perform incremental backup using change streams."""
    client = MongoClient("mongodb://localhost:27017")

    # Get last backup timestamp
    last_backup = get_last_backup_timestamp()

    # Stream changes since last backup
    pipeline = [
        {"$match": {"clusterTime": {"$gt": last_backup}}}
    ]

    change_stream = client.watch(pipeline)

    changes = []
    for change in change_stream:
        changes.append(change)

        # Backup every 1000 changes or hourly
        if len(changes) >= 1000 or time_since_last_backup() > 3600:
            save_incremental_backup(changes)
            changes = []

def save_incremental_backup(changes):
    """Save incremental backup."""
    timestamp = datetime.utcnow()
    backup_file = f"/backups/mongodb/incremental/{timestamp}.json"

    with open(backup_file, 'w') as f:
        json.dump(changes, f)

    update_last_backup_timestamp(timestamp)
```

---

## Redis Backup Procedures

### RDB Snapshots

**Configuration:**
```bash
# redis.conf
save 900 1      # Save after 900 sec (15 min) if at least 1 key changed
save 300 10     # Save after 300 sec (5 min) if at least 10 keys changed
save 60 10000   # Save after 60 sec if at least 10000 keys changed
```

**Manual Backup:**
```bash
#!/bin/bash
# scripts/backup_redis.sh

# Configuration
REDIS_HOST="localhost"
REDIS_PORT=6379
BACKUP_DIR="/backups/redis"
TIMESTAMP=$(date +%Y%m%d_%H%M%S)
BACKUP_FILE="${BACKUP_DIR}/redis_${TIMESTAMP}.rdb"

# Create backup directory
mkdir -p ${BACKUP_DIR}

# Trigger RDB save
redis-cli -h ${REDIS_HOST} -p ${REDIS_PORT} BGSAVE

# Wait for save to complete
while [ $(redis-cli -h ${REDIS_HOST} -p ${REDIS_PORT} LASTSAVE) -eq $(redis-cli -h ${REDIS_HOST} -p ${REDIS_PORT} LASTSAVE) ]; do
    sleep 1
done

# Copy RDB file
cp /var/lib/redis/dump.rdb ${BACKUP_FILE}

# Upload to cloud storage
aws s3 cp ${BACKUP_FILE} s3://backups/redis/

# Clean old backups (keep 7 days)
find ${BACKUP_DIR} -name "*.rdb" -mtime +7 -delete

echo "Redis backup completed: ${TIMESTAMP}"
```

### AOF Persistence

**Configuration:**
```bash
# redis.conf
appendonly yes
appendfilename "appendonly.aof"
appendfsync everysec
auto-aof-rewrite-percentage 100
auto-aof-rewrite-min-size 64mb
```

**Manual Backup:**
```bash
# Backup AOF file
cp /var/lib/redis/appendonly.aof /backups/redis/appendonly_${TIMESTAMP}.aof
```

---

## File Storage Backup

### Upload Directory Backup

```bash
#!/bin/bash
# scripts/backup_files.sh

# Configuration
UPLOAD_DIR="/uploads"
BACKUP_DIR="/backups/files"
TIMESTAMP=$(date +%Y%m%d_%H%M%S)

# Create backup directory
mkdir -p ${BACKUP_DIR}

# Create tarball
tar -czf ${BACKUP_DIR}/uploads_${TIMESTAMP}.tar.gz ${UPLOAD_DIR}

# Upload to cloud storage
aws s3 cp ${BACKUP_DIR}/uploads_${TIMESTAMP}.tar.gz s3://backups/files/

# Clean old backups (keep 30 days)
find ${BACKUP_DIR} -name "uploads_*.tar.gz" -mtime +30 -delete

echo "File backup completed: ${TIMESTAMP}"
```

### Incremental File Backup

**Using rsync:**
```bash
#!/bin/bash
# scripts/incremental_file_backup.sh

# Configuration
UPLOAD_DIR="/uploads"
BACKUP_DIR="/backups/files"
LINK_DIR="/backups/files/latest"

# Create incremental backup
rsync -av --delete --link-dest=${LINK_DIR} ${UPLOAD_DIR}/ ${BACKUP_DIR}/$(date +%Y%m%d_%H%M%S)/

# Update latest link
ln -sfn ${BACKUP_DIR}/$(date +%Y%m%d_%H%M%S) ${LINK_DIR}

echo "Incremental file backup completed"
```

---

## Backup Verification

### Automated Verification

**MongoDB Verification:**
```python
# scripts/verify_mongodb_backup.py
from pymongo import MongoClient
import subprocess

def verify_mongodb_backup(backup_path):
    """Verify MongoDB backup integrity."""
    # 1. Check backup file exists
    if not os.path.exists(backup_path):
        return False, "Backup file not found"

    # 2. Check backup size
    backup_size = os.path.getsize(backup_path)
    if backup_size < 1024:  # Less than 1KB
        return False, "Backup too small"

    # 3. Restore to temporary database
    temp_db_name = f"verify_{int(time.time())}"

    try:
        subprocess.run([
            "mongorestore",
            "--uri=mongodb://localhost:27017",
            f"--db={temp_db_name}",
            backup_path
        ], check=True)

        # 4. Verify data count
        client = MongoClient("mongodb://localhost:27017")
        temp_db = client[temp_db_name]
        collection_count = len(temp_db.list_collection_names())

        if collection_count == 0:
            return False, "No collections found"

        # 5. Drop temporary database
        client.drop_database(temp_db_name)

        return True, "Backup verified successfully"

    except Exception as e:
        return False, f"Verification failed: {str(e)}"
```

**Redis Verification:**
```python
# scripts/verify_redis_backup.py
import redis

def verify_redis_backup(backup_file):
    """Verify Redis backup integrity."""
    # 1. Check backup file exists
    if not os.path.exists(backup_file):
        return False, "Backup file not found"

    # 2. Load backup to temporary Redis instance
    temp_redis_port = 6380
    subprocess.run([
        "redis-server",
        f"--port {temp_redis_port}",
        f"--dir {os.path.dirname(backup_file)}",
        f"--dbfilename {os.path.basename(backup_file)}"
    ])

    # 3. Connect and verify
    temp_redis = redis.Redis(port=temp_redis_port)

    try:
        info = temp_redis.info()
        if info.get("used_memory_human") == "0B":
            return False, "Backup is empty"

        return True, "Backup verified successfully"

    finally:
        # 4. Shutdown temporary instance
        temp_redis.shutdown()
```

### Regular Verification Schedule

**Weekly:**
- Verify latest full backup
- Test restore procedure on staging
- Check backup file integrity

**Monthly:**
- Verify all backups in retention window
- Perform full restore test
- Update backup documentation

---

## Restore Procedures

### MongoDB Restore

**Full Restore:**
```bash
#!/bin/bash
# scripts/restore_mongodb.sh

BACKUP_PATH=$1
MONGODB_URI="mongodb://localhost:27017"

# Stop application
systemctl stop backend

# Restore from backup
mongorestore \
  --uri="${MONGODB_URI}" \
  --drop \
  --gzip \
  ${BACKUP_PATH}

# Start application
systemctl start backend

echo "MongoDB restore completed"
```

**Point-in-Time Recovery:**
```bash
# Using MongoDB Atlas
# 1. Select backup snapshot
# 2. Choose point-in-time
# 3. Restore to new database or overwrite existing
```

### Redis Restore

**RDB Restore:**
```bash
#!/bin/bash
# scripts/restore_redis.sh

BACKUP_FILE=$1
REDIS_DIR="/var/lib/redis"

# Stop Redis
systemctl stop redis

# Copy backup file
cp ${BACKUP_FILE} ${REDIS_DIR}/dump.rdb

# Start Redis
systemctl start redis

echo "Redis restore completed"
```

**AOF Restore:**
```bash
# Copy AOF file
cp appendonly.aof /var/lib/redis/appendonly.aof

# Start Redis (will load AOF)
systemctl start redis
```

### File Storage Restore

```bash
#!/bin/bash
# scripts/restore_files.sh

BACKUP_FILE=$1
UPLOAD_DIR="/uploads"

# Stop application
systemctl stop backend

# Extract backup
tar -xzf ${BACKUP_FILE} -C /

# Start application
systemctl start backend

echo "File restore completed"
```

---

## Disaster Recovery

### Disaster Recovery Activation

**Trigger Conditions:**
- Primary data center failure
- Database corruption
- Ransomware infection
- Extended outage (> 4 hours)

**Activation Steps:**
1. Declare disaster (P1 incident)
2. Activate disaster recovery plan
3. Switch to backup infrastructure
4. Restore from latest backup
5. Verify system integrity
6. Redirect traffic
7. Monitor system health

### Infrastructure Redundancy

**Primary Site:**
- Region: us-east-1
- Services: API, Database, Cache, Storage

**Secondary Site (Hot Standby):**
- Region: us-west-2
- Services: API, Database, Cache, Storage
- Replication: Real-time

**Failover Procedure:**
```python
# scripts/failover_to_secondary.py
def failover_to_secondary():
    """Failover to secondary site."""
    # 1. Stop writes to primary
    enable_read_only_mode(primary_site)

    # 2. Verify secondary is up-to-date
    if not verify_replication_lag():
        raise Exception("Replication lag too high")

    # 3. Switch DNS to secondary
    update_dns_records(secondary_site_ip)

    # 4. Verify traffic is flowing to secondary
    if not verify_traffic(secondary_site):
        raise Exception("Traffic verification failed")

    # 5. Mark secondary as primary
    promote_secondary_to_primary()

    print("Failover completed successfully")
```

---

## Backup Storage Management

### Local Storage

**Configuration:**
```bash
# Backup directories
/backups/mongodb     # MongoDB backups
/backups/redis       # Redis backups
/backups/files       # File backups
/backups/logs        # Log archives
```

**Disk Requirements:**
- MongoDB: 2x production size
- Redis: 2x production size
- Files: 2x production size
- Logs: 1x monthly log volume

### Cloud Storage

**AWS S3 Configuration:**
```python
# config/storage.py
S3_BACKUP_BUCKET = "ridp-form-backups"
S3_BACKUP_PREFIX = "backups/"

# Lifecycle rules
lifecycle_rules = [
    {
        "Id": "DeleteOldBackups",
        "Status": "Enabled",
        "Prefix": "backups/",
        "Expiration": {"Days": 90}
    },
    {
        "Id": "ArchiveOldBackups",
        "Status": "Enabled",
        "Prefix": "backups/",
        "Transitions": [
            {
                "Days": 30,
                "StorageClass": "GLACIER"
            }
        ]
    }
]
```

### Encryption Requirements

**At Rest:**
- Local: LUKS encryption
- Cloud: S3 server-side encryption (AES-256)

**In Transit:**
- TLS 1.3 for all transfers
- SSH for file transfers

---

## Monitoring and Alerting

### Backup Success Monitoring

```python
# scripts/monitor_backups.py
def monitor_backups():
    """Monitor backup success/failure."""
    # Check recent backups
    recent_backups = get_recent_backups(hours=24)

    for backup in recent_backups:
        if backup["status"] != "success":
            send_alert(
                f"Backup failed: {backup['type']} - {backup['timestamp']}",
                severity="P2"
            )

        # Check backup age
        backup_age = (datetime.utcnow() - backup["timestamp"]).total_seconds()
        if backup_age > MAX_BACKUP_AGE:
            send_alert(
                f"Backup too old: {backup['type']} - {backup_age}s",
                severity="P3"
            )

    # Check backup size
    backup_size = get_total_backup_size()
    if backup_size < MINIMUM_BACKUP_SIZE:
        send_alert(
            f"Backup size too small: {backup_size} bytes",
            severity="P2"
        )
```

### Backup Storage Monitoring

```python
def monitor_backup_storage():
    """Monitor backup storage space."""
    # Check local storage
    disk_usage = psutil.disk_usage("/backups")
    usage_percent = disk_usage.used / disk_usage.total * 100

    if usage_percent > 80:
        send_alert(
            f"Backup storage at {usage_percent}% capacity",
            severity="P2"
        )

    # Check cloud storage costs
    monthly_cost = get_s3_storage_cost()
    if monthly_cost > MAX_MONTHLY_COST:
        send_alert(
            f"Cloud storage cost high: ${monthly_cost}",
            severity="P3"
        )
```

---

## Best Practices

### 1. Automate Backups

```python
# CORRECT - Automated backups
schedule.every().day.at("02:00").do(backup_mongodb)
schedule.every().hour.at(":00").do(backup_redis_incremental)

# WRONG - Manual backups
# Rely on human to run backup commands
```

### 2. Verify Backups Regularly

```python
# CORRECT - Regular verification
schedule.every().week.do(verify_latest_backup)

# WRONG - Never verify
# Assume backups are valid
```

### 3. Test Restore Procedures

```python
# CORRECT - Test restores on staging
schedule.every().month.do(test_restore_on_staging)

# WRONG - Never test restores
# First time testing is during disaster
```

### 4. Encrypt Backups

```python
# CORRECT - Encrypted backups
encrypt_backup(backup_file, encryption_key)

# WRONG - Unencrypted backups
# Store sensitive data in plain text
```

### 5. Document Recovery Procedures

```python
# CORRECT - Documented procedures
# Runbook available to all team members

# WRONG - Tribal knowledge
# Only one person knows how to restore
```

---

## Configuration Reference

### Backup Configuration

```bash
# scripts/config.sh
# MongoDB
MONGODB_URI="mongodb://localhost:27017"
MONGODB_BACKUP_DIR="/backups/mongodb"
MONGODB_RETENTION_DAYS=30

# Redis
REDIS_HOST="localhost"
REDIS_PORT=6379
REDIS_BACKUP_DIR="/backups/redis"
REDIS_RETENTION_DAYS=7

# Files
UPLOAD_DIR="/uploads"
FILE_BACKUP_DIR="/backups/files"
FILE_RETENTION_DAYS=30

# Cloud
S3_BACKUP_BUCKET="ridp-form-backups"
S3_BACKUP_PREFIX="backups/"
```

---

## References

- [MongoDB Backup and Restore](https://www.mongodb.com/docs/manual/administration/backup-restore/)
- [Redis Persistence](https://redis.io/topics/persistence)
- [AWS S3 Backup Best Practices](https://docs.aws.amazon.com/AmazonS3/latest/userguide/backup.html)
- [NIST SP 800-34 - Contingency Planning Guide](https://csrc.nist.gov/publications/detail/sp/800-34/rev-1/final)
