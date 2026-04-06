# Blueprint: Anomaly Detection (`anomaly_bp`)

## Registration

| Property | Value |
|----------|-------|
| Blueprint name | `anomaly_bp` |
| URL prefix | `/form/api/v1/forms` |
| Module | `routes/v1/form/anomaly.py` |
| Services used | `AnomalyDetectionService` |

---

## Overview

The anomaly detection blueprint provides machine learning-based detection of anomalous form responses. It supports multiple detection types including spam, outlier detection, impossible values, and duplicate detection. The system uses statistical methods and can be configured with dynamic thresholds that adapt to form-specific data patterns.

**Key Features:**
- Multiple detection types: spam, outlier, impossible_value, duplicate
- Sensitivity levels: auto, low, medium, high
- Dynamic threshold calculation based on form response history
- Batch scanning support for processing multiple responses
- Manual threshold override capability
- Threshold history tracking

---

## Route Reference

### POST /form/api/v1/forms/<form_id>/detect-anomalies

**Summary:** Run anomaly detection on form responses.

**Authentication:** `@jwt_required()`

**Request body:**
```json
{
  "scan_type": "full" | "incremental",
  "response_ids": ["id1", "id2"],
  "detection_types": ["spam", "outlier", "impossible_value", "duplicate"],
  "sensitivity": "auto" | "low" | "medium" | "high",
  "use_dynamic_thresholds": true,
  "save_results": true
}
```

**Parameters:**
- `scan_type` (string, required): "full" for all responses, "incremental" for recent 100
- `response_ids` (array, optional): Specific response IDs to scan
- `detection_types` (array, optional): Detection types to apply (default: ["spam", "outlier"])
- `sensitivity` (string, optional): Detection sensitivity (default: "medium")
- `use_dynamic_thresholds` (boolean, optional): Use form-specific thresholds (default: false)
- `save_results` (boolean, optional): Save detection results to database (default: false)

**Response (200):**
```json
{
  "form_id": "form-uuid",
  "scan_type": "full",
  "responses_scanned": 250,
  "anomalies_detected": 12,
  "scan_duration_ms": 1250,
  "baseline": {
    "mean": 45.2,
    "std_dev": 12.5,
    "median": 42.0
  },
  "thresholds_used": {
    "z_score_threshold": 2.5,
    "iqr_multiplier": 1.5
  },
  "use_dynamic_thresholds": true,
  "anomalies": [
    {
      "response_id": "resp-1",
      "detection_type": "spam",
      "score": 0.92,
      "indicators": ["excessive_links", "suspicious_keywords"]
    }
  ],
  "summary_by_type": {
    "spam": 5,
    "outlier": 4,
    "impossible_value": 2,
    "duplicate": 1
  }
}
```

**Error responses:**
- `400` — Invalid parameters
- `404` — Form not found
- `500` — Internal server error

**Audit log:** `Anomaly detection run for form_id: <id> by user: <id>. Scanned: <count>, Detected: <count>`

---

### GET /form/api/v1/forms/<form_id>/anomalies/<response_id>

**Summary:** Get detailed anomaly information for a specific response.

**Authentication:** `@jwt_required()`

**Response (200):**
```json
{
  "response_id": "resp-789",
  "anomaly_flags": {
    "spam": {
      "score": 85,
      "indicators": ["excessive_links", "suspicious_keywords", "repeated_text"],
      "confidence": 0.85
    },
    "outlier": {
      "z_score": 3.2,
      "deviation_from_mean": "high"
    }
  },
  "response_data": {
    "text": "Form submission content...",
    "submitted_at": "2026-04-02T10:30:00Z"
  },
  "review_status": "pending",
  "suggested_actions": ["review", "flag_response", "ignore"]
}
```

**Error responses:**
- `404` — Response not found
- `500` — Internal server error

---

### POST /form/api/v1/forms/<form_id>/thresholds/update-baseline

**Summary:** Update baseline statistics and calculate dynamic thresholds for a form.

**Authentication:** `@jwt_required()`

**Request body:** Empty (uses all current form responses)

**Response (200):**
```json
{
  "message": "Baseline updated successfully",
  "baseline_stats": {
    "total_responses": 150,
    "mean": 42.5,
    "std_dev": 11.2,
    "median": 40.0,
    "min": 10.0,
    "max": 95.0
  },
  "thresholds": {
    "z_score_threshold": 2.5,
    "iqr_multiplier": 1.5,
    "spam_threshold": 0.75
  },
  "response_count": 150,
  "threshold_id": "threshold-uuid"
}
```

**Audit log:** `Anomaly baseline updated for form_id: <id> by user: <id>`

---

### GET /form/api/v1/forms/<form_id>/thresholds/history

**Summary:** Get threshold history for a form.

**Authentication:** `@jwt_required()`

**Query parameters:**
- `limit` (int, optional): Maximum number of records to return (default: 50)

**Response (200):**
```json
{
  "form_id": "form-123",
  "threshold_history": [
    {
      "threshold_id": "threshold-1",
      "created_at": "2026-04-02T10:00:00Z",
      "created_by": "user-123",
      "baseline_stats": {...},
      "thresholds": {...},
      "sensitivity": "auto",
      "is_manual": false
    }
  ]
}
```

---

### GET /form/api/v1/forms/<form_id>/thresholds/latest

**Summary:** Get the latest threshold configuration for a form.

**Authentication:** `@jwt_required()`

**Query parameters:**
- `sensitivity` (string, optional): Filter by sensitivity (auto, low, medium, high)

**Response (200):**
```json
{
  "threshold_id": "threshold-uuid",
  "form_id": "form-123",
  "thresholds": {
    "z_score_threshold": 2.5,
    "iqr_multiplier": 1.5,
    "spam_threshold": 0.75
  },
  "sensitivity": "auto",
  "baseline_stats": {
    "total_responses": 150,
    "mean": 42.5,
    "std_dev": 11.2
  },
  "response_count": 150,
  "created_by": "user-123",
  "is_manual": false,
  "created_at": "2026-04-02T10:00:00Z"
}
```

**Error responses:**
- `404` — No threshold found for this form

---

### POST /form/api/v1/forms/<form_id>/thresholds/manual

**Summary:** Manually set a threshold configuration for a form.

**Authentication:** `@jwt_required()`

**Request body:**
```json
{
  "thresholds": {
    "z_score_threshold": 2.5,
    "iqr_multiplier": 1.5,
    "spam_threshold": 0.8,
    "sensitivity": "high"
  },
  "reason": "Too many false positives in current configuration"
}
```

**Response (200):**
```json
{
  "message": "Manual threshold set successfully",
  "threshold_id": "threshold-uuid",
  "thresholds": {
    "z_score_threshold": 2.5,
    "iqr_multiplier": 1.5,
    "spam_threshold": 0.8,
    "sensitivity": "high"
  },
  "baseline_stats": {
    "total_responses": 150,
    "mean": 42.5,
    "std_dev": 11.2
  },
  "created_at": "2026-04-02T10:00:00Z"
}
```

**Audit log:** `Manual anomaly threshold set for form_id: <id> by user: <id>. Reason: <reason>`

---

### POST /form/api/v1/forms/<form_id>/detect-anomalies/batch

**Summary:** Run anomaly detection on a batch of form responses asynchronously.

**Authentication:** `@jwt_required()`

**Request body:**
```json
{
  "response_ids": ["id1", "id2", "id3"],
  "scan_config": {
    "detection_types": ["spam", "outlier"],
    "sensitivity": "medium",
    "use_dynamic_thresholds": false
  },
  "batch_id": "custom-batch-id"
}
```

**Parameters:**
- `response_ids` (array, required): List of response IDs to scan
- `scan_config` (object, optional): Scan configuration
- `batch_id` (string, optional): Custom batch ID (auto-generated if not provided)

**Response (200):**
```json
{
  "batch_id": "batch-abc123_1234567890",
  "status": "in_progress",
  "form_id": "form-123",
  "total_responses": 100,
  "scanned_count": 0,
  "anomalies_detected": 0,
  "summary": {},
  "results": {},
  "started_at": "2026-04-02T10:00:00Z",
  "completed_at": null
}
```

**Audit log:** `Batch anomaly scan initiated for form_id: <id> by user: <id>. Batch ID: <batch_id>`

---

### GET /form/api/v1/forms/<form_id>/detect-anomalies/batch/<batch_id>/status

**Summary:** Get the status of a batch anomaly detection scan.

**Authentication:** `@jwt_required()`

**Query parameters:**
- `nocache` (string, optional): Set to "true" to bypass cache and fetch from database

**Response (200):**
```json
{
  "batch_id": "batch-abc123_1234567890",
  "form_id": "form-123",
  "status": "completed",
  "progress": 100.0,
  "total_responses": 100,
  "scanned_count": 100,
  "results_count": 12,
  "estimated_completion": "2026-04-02T10:01:30Z",
  "started_at": "2026-04-02T10:00:00Z",
  "completed_at": "2026-04-02T10:01:30Z",
  "error_message": null,
  "results": {
    "anomalies_detected": 12,
    "summary_by_type": {...},
    "anomalies": [...]
  },
  "summary": {
    "total_anomalies": 12,
    "high_severity": 3,
    "medium_severity": 7,
    "low_severity": 2
  }
}
```

**Error responses:**
- `400` — Batch scan does not belong to this form
- `404` — Batch scan not found

---

## Detection Types

### Spam Detection
Uses text analysis and pattern matching to identify spam submissions:
- Excessive links or URLs
- Suspicious keywords and phrases
- Repetitive text patterns
- Unusual formatting

### Outlier Detection
Statistical analysis to identify responses that deviate significantly:
- Z-score analysis (default threshold: 2.5)
- Interquartile range (IQR) method (default multiplier: 1.5)
- Percentile-based detection

### Impossible Value Detection
Identifies responses with logically impossible values:
- Negative values where only positive expected
- Values outside valid ranges
- Inconsistent data patterns

### Duplicate Detection
Identifies duplicate or near-duplicate submissions:
- Exact match detection
- Fuzzy matching for near-duplicates
- Time-based correlation

---

## Sensitivity Levels

| Level | Z-Score Threshold | IQR Multiplier | Spam Threshold |
|-------|------------------|----------------|----------------|
| low   | 3.0              | 2.0            | 0.85           |
| medium| 2.5              | 1.5            | 0.75           |
| high  | 2.0              | 1.0            | 0.65           |
| auto  | Calculated       | Calculated     | Calculated     |

**Auto sensitivity:** Dynamically calculates thresholds based on form response distribution and variance.

---

## Dynamic Thresholds

When `use_dynamic_thresholds` is enabled, the system:
1. Analyzes historical response data
2. Calculates form-specific baseline statistics
3. Adjusts thresholds based on data distribution
4. Updates thresholds periodically as more data is collected

**Benefits:**
- Reduces false positives for forms with high natural variance
- Increases sensitivity for forms with tight data distribution
- Adapts to seasonal or temporal patterns

---

## Performance Considerations

- **Full scan:** Processes all form responses - use with caution for large datasets
- **Incremental scan:** Only processes recent 100 responses - recommended for ongoing monitoring
- **Batch scan:** Asynchronous processing for large response sets
- **Caching:** Threshold history and batch status are cached in Redis

---

## Best Practices

1. **Start with incremental scans** to establish baseline before full scans
2. **Use dynamic thresholds** for forms with natural variance in responses
3. **Review false positives** regularly and adjust sensitivity or manual thresholds
4. **Combine detection types** for comprehensive anomaly coverage
5. **Use batch scanning** for processing large response sets asynchronously
6. **Document threshold changes** with reason tracking for audit trail

---

## Integration Example

### Running Initial Anomaly Detection

```bash
# 1. First, update baseline
curl -X POST "https://api.example.com/form/api/v1/forms/<form_id>/thresholds/update-baseline" \
  -H "Authorization: Bearer <token>"

# 2. Run incremental scan to test
curl -X POST "https://api.example.com/form/api/v1/forms/<form_id>/detect-anomalies" \
  -H "Authorization: Bearer <token>" \
  -H "Content-Type: application/json" \
  -d '{
    "scan_type": "incremental",
    "detection_types": ["spam", "outlier"],
    "sensitivity": "medium",
    "use_dynamic_thresholds": true,
    "save_results": false
  }'

# 3. Review results and adjust if needed
curl -X POST "https://api.example.com/form/api/v1/forms/<form_id>/thresholds/manual" \
  -H "Authorization: Bearer <token>" \
  -H "Content-Type: application/json" \
  -d '{
    "thresholds": {
      "z_score_threshold": 3.0,
      "sensitivity": "high"
    },
    "reason": "Reducing false positives"
  }'

# 4. Run full scan with new thresholds
curl -X POST "https://api.example.com/form/api/v1/forms/<form_id>/detect-anomalies" \
  -H "Authorization: Bearer <token>" \
  -H "Content-Type: application/json" \
  -d '{
    "scan_type": "full",
    "use_dynamic_thresholds": true,
    "save_results": true
  }'
```

---

## Dependencies

- `AnomalyDetectionService` (`services/anomaly_detection_service.py`) — Core detection logic
- `FormResponse` model — Response data source
- Redis — Threshold and batch status caching
- Flask-JWT-Extended — Authentication

---

## Related Documentation

- `overview.md` — Architecture overview
- `FLOW_DIAGRAMS.md` — Anomaly detection flow diagram
- `risks-and-gaps.md` — Known limitations (R-09)

---

**Last Updated:** 2026-04-02
