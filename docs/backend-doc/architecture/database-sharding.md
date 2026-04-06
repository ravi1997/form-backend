# Database Sharding Strategy

**Purpose:** Documentation for MongoDB sharding strategy for horizontal scalability.

**Scope:** Sharding strategy, shard key selection, chunk distribution, balancing considerations, and migration procedures.

---

## Overview

This document outlines the database sharding strategy for the RIDP Form Platform to enable horizontal scalability. Sharding distributes data across multiple MongoDB instances to handle large datasets and high throughput.

**Target Audience:** Database administrators, system architects, DevOps engineers

---

## Sharding Architecture

### Sharded Cluster Topology

```
┌─────────────────────────────────────────────────┐
│             MongoDB Sharded Cluster            │
│                                                 │
│  ┌──────────────┐  ┌──────────────┐           │
│  │  Config Svr  │  │  Mongos       │           │
│  │  (Primary)   │  │ (Routers)     │           │
│  └──────────────┘  └──────────────┘           │
│         │               │                   │
│         └───────────────┘                   │
│                   │                          │
│         ┌────────────────────────┐        │
│         │  Shard 1 (Primary)   │        │
│         │  Shard 2 (Primary)   │        │
│         │  Shard 3 (Primary)   │        │
│         └────────────────────────┘        │
│                                                 │
│  Each shard:                                    │
│  - 1 Primary replica set                         │
│  - 2 Secondary replicas (optional)              │
└─────────────────────────────────────────────────┘
```

---

## Shard Key Selection

### Shard Key Design Principles

**1. Cardinality:**
- High cardinality ensures even distribution
- Avoid low cardinality fields (e.g., status)

**2. Frequency:**
- High frequency ensures even distribution
- Avoid fields with few distinct values

**3. Monotonicity:**
- Avoid monotonically increasing values (creates hotspots)
- If needed, use hashed shard key

### Recommended Shard Keys

**Form Collection:**

```python
# Shard key: organization_id (hashed)
# Reason: Even distribution across tenants
# Cardinality: High (many organizations)
# Frequency: High (many forms per organization)

shard_key = {"organization_id": "hashed"}

# Alternative: Compound key for better data locality
# shard_key = {"organization_id": 1, "created_at": 1}
# Reason: Data locality for queries by organization
```

**FormResponse Collection:**

```python
# Shard key: organization_id (hashed)
# Reason: Even distribution across tenants
# Queries: Typically by form_id within organization

shard_key = {"organization_id": "hashed"}

# Alternative: Compound key
# shard_key = {"form_id": 1, "created_at": 1}
# Reason: Good for queries by form_id, but may cause hotspots
```

**User Collection:**

```python
# Shard key: organization_id (hashed)
# Reason: Even distribution across tenants
# Queries: Always scoped to organization_id

shard_key = {"organization_id": "hashed"}
```

---

## Sharding Strategy

### Hashed Sharding

**Use Case:** Even distribution across all shards

**Implementation:**

```javascript
// MongoDB shell
db.forms.createIndex(
    { "organization_id": "hashed" }
)

sh.shardCollection(
    "forms_db.forms",
    { "organization_id": "hashed" }
)
```

### Ranged Sharding

**Use Case:** Range queries and data locality

**Implementation:**

```javascript
// MongoDB shell
db.forms.createIndex(
    { "organization_id": 1, "created_at": 1 }
)

sh.shardCollection(
    "forms_db.forms",
    { "organization_id": 1, "created_at": 1 }
)
```

---

## Chunk Distribution

### Chunk Size

**Default:** 64 MB per chunk

**Configuration:**

```javascript
// MongoDB shell
use config
db.settings.save({
    _id: "chunksize",
    value: 64  // MB
})
```

### Balancing

**Balancer:** Background process that migrates chunks

**Configuration:**

```javascript
// MongoDB shell
use config

sh.setBalancerState(
    "forms_db",
    true  // Enable balancer
)

// Configure balancing window
sh.updateZoneKeyRange(
    "forms_db.forms",
    { "organization_id": 1 },
    { "organization_id": 1 },
    {
        "organization_id": MinKey,
        "organization_id": MaxKey
    },
    true  // No balancing during maintenance
)
```

---

## Performance Considerations

### Query Optimization

**Ensure Queries Use Shard Key:**

```python
# CORRECT - Uses shard key (organization_id)
forms = Form.objects(
    organization_id=user.organization_id,
    created_at__gte=start_date
)

# WRONG - Doesn't use shard key (scatter-gather)
forms = Form.objects(
    name__icontains="search term"  # Hits all shards
)
```

**Covered Queries:**

```python
# Ensure indexes cover queries
# Index: { "organization_id": 1, "created_at": 1, "status": 1 }

forms = Form.objects(
    organization_id=user.organization_id,
    created_at__gte=start_date,
    created_at__lte=end_date,
    status="published"
)
```

### Chunk Migration

**Monitor Chunks:**

```javascript
// Check chunk distribution
db.chunks.find({ ns: "forms_db.forms" }).forEach(function(chunk) {
    print(`Shard: ${chunk.shard}, Size: ${chunk.size}`);
});

// Move large chunks
sh.moveChunk(
    "forms_db.forms",
    { "organization_id": ObjectId("..."), "created_at": ISODate("...") },
    "shard02"
)
```

---

## Migration Procedures

### Initial Sharding

**1. Deploy Config Servers:**

```bash
# Start config servers (replica set)
mongod --configsvr --replSet configRS --port 27019
mongod --configsvr --replSet configRS --port 27020
mongod --configsvr --replSet configRS --port 27021

# Initiate replica set
mongosh --port 27019
rs.initiate({
    _id: "configRS",
    configsvrs: [
        { _host: "localhost:27019" },
        { _host: "localhost:27020" },
        { _host: "localhost:27021" }
    ]
})
```

**2. Deploy Shard Servers:**

```bash
# Start shard servers (replica sets)
# Shard 1
mongod --shardsvr --replSet shard1RS --port 27022
mongod --shardsvr --replSet shard1RS --port 27023
mongod --shardsvr --replSet shard1RS --port 27024

# Shard 2
mongod --shardsvr --replSet shard2RS --port 27025
mongod --shardsvr --replSet shard2RS --port 27026
mongod --shardsvr --replSet shard2RS --port 27027
```

**3. Deploy Mongos (Routers):**

```bash
# Start mongos routers
mongos --configdb configRS/localhost:27019,localhost:27020,localhost:27021 --port 27017
mongos --configdb configRS/localhost:27019,localhost:27020,localhost:27021 --port 27018
```

**4. Enable Sharding:**

```javascript
// Connect to mongos
mongosh --port 27017

// Enable sharding for database
sh.enableSharding("forms_db")

// Shard collections
sh.shardCollection(
    "forms_db.forms",
    { "organization_id": "hashed" }
)

sh.shardCollection(
    "forms_db.form_responses",
    { "organization_id": "hashed" }
)
```

### Adding Shards

```javascript
// Add new shard
sh.addShard("shard3RS/localhost:27028,localhost:27029,localhost:27030")
```

---

## Configuration

### MongoDB Configuration

**mongod.conf:**

```conf
# MongoDB Configuration File

# Network
bind_ip: 0.0.0.0
port: 27017

# Storage
dbPath: /data/db
journal:
  enabled: true

# Replication
replication:
  replSet: shard1RS

# Sharding
sharding:
  clusterRole: shardsvr

# Security
security:
  authorization: enabled
  keyFile: /etc/mongodb/keyfile

# Log
systemLog:
  destination: file
  path: /var/log/mongodb/mongod.log
  logAppend: true
```

---

## Monitoring

### Shard Status Monitoring

```javascript
// Check shard status
sh.status()

// Check balancer status
sh.getBalancerState()

// Check chunk distribution
sh.disableBalancing("forms_db")
```

### Metrics to Monitor

**Chunk Statistics:**
- Number of chunks per shard
- Chunk migration status
- Chunk size distribution

**Performance Metrics:**
- Query performance by shard
- Write distribution by shard
- Replication lag

**Operational Metrics:**
- Config server health
- Mongos performance
- Shard server health

---

## Best Practices

### 1. Choose Appropriate Shard Keys

```javascript
// CORRECT - High cardinality, high frequency
shard_key = { "organization_id": "hashed" }

// WRONG - Low cardinality
shard_key = { "status" }  // Only 3-4 values
```

### 2. Monitor Chunk Distribution

```python
# CORRECT - Monitor chunks
check_chunk_distribution()

# WRONG - Assume even distribution
# May have hotspots
```

### 3. Plan for Future Growth

```python
# CORRECT - Design for 10x growth
# Shard key supports 1000+ tenants

// WRONG - Design for current load
# Will need re-sharding soon
```

### 4. Use Indexes to Support Queries

```python
# CORRECT - Create indexes that support queries
# Index: { organization_id: 1, created_at: -1 }

// WRONG - No indexes
# Queries scan all shards
```

### 5. Test Sharded Queries

```python
# CORRECT - Test sharded queries
# Verify queries use shard key

// WRONG - Don't test
# Queries may be slow
```

---

## References

- [MongoDB Sharding](https://www.mongodb.com/docs/manual/sharding/)
- [MongoDB Shard Keys](https://www.mongodb.com/docs/manual/sharding/shard-key/)
- [MongoDB Cluster Planning](https://www.mongodb.com/docs/manual/tutorial/deploy-shard-cluster/)
- [MongoDB Horizontal Scaling](https://www.mongodb.com/docs/manual/administration/horizontal-scaling/)
