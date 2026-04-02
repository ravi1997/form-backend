# Blueprint: Forms — Translation (`translation_bp`)

## Registration

| Property | Value |
|----------|-------|
| Blueprint name | `translation` |
| URL prefix | `/form/api/v1/forms/translations` |
| Module | `routes/v1/form/translation.py` |
| Services used | `AIService` |

---

## Overview

The translation blueprint provides AI-powered and manual translation management for forms. It supports:
- Manual reading and saving of translation strings
- Supported language listing
- AI translation preview
- Async translation jobs (batch AI translation across multiple languages)

**Critical architectural note:** Translation jobs run in Python `threading.Thread` (NOT Celery). This means jobs do NOT survive worker restarts, have no retry capability, and are not visible in Celery monitoring. See `risks-and-gaps.md` R-01.

---

## Route Reference

### GET /form/api/v1/forms/translations

**Summary:** Retrieve stored translations for a form.

**Authentication:** `@jwt_required()`

**Query parameters:**
- `form_id` (required) — UUID of the form
- `language` (optional) — specific language code (e.g., `hi`, `fr`). Omit to get all languages.

**Permission check:** `has_form_permission(user, form, "view")` — 403 if lacking.

**Behavior:**
- Returns translations from the latest `FormVersion` (`form.versions[-1].translations`)
- If no versions exist, returns empty translations dict
- If `language` is specified, returns only that language's translations
- If `language` is omitted, returns the full translations object for all languages

**Response (200) — specific language:**
```json
{
  "success": true,
  "data": {
    "language": "hi",
    "translations": {
      "title": "मरीज फॉर्म",
      "q_name": "नाम",
      "q_age": "आयु"
    }
  }
}
```

**Response (200) — all languages:**
```json
{
  "success": true,
  "data": {
    "hi": { "title": "...", "q_name": "..." },
    "fr": { "title": "...", "q_name": "..." }
  }
}
```

---

### POST /form/api/v1/forms/translations

**Summary:** Save/update translations for a form in a specific language.

**Authentication:** `@jwt_required()`

**Request body:**
```json
{
  "form_id": "uuid",
  "language": "hi",
  "translations": {
    "title": "मरीज फॉर्म",
    "q_name": "नाम",
    "q_age": "आयु"
  }
}
```

All three fields are required.

**Permission check:** `has_form_permission(user, form, "edit")` — 403 if lacking.

**Behavior:**
- Requires form to have at least one version (`form.versions`)
- Stores translations directly into the latest version: `latest_version.translations[language] = translations`
- Does NOT overwrite other languages' translations

**Success response (200):**
```json
{
  "success": true,
  "message": "Translations saved successfully"
}
```

**Audit log:** Structured with `user_id`, `form_id`, `language`, `action: save_translations`

---

### GET /form/api/v1/forms/translations/languages

**Summary:** List all supported languages.

**Authentication:** `@jwt_required()`

**Behavior:** Returns a hardcoded list of 12 supported languages.

**Response (200):**
```json
{
  "success": true,
  "data": [
    { "code": "en", "name": "English", "native_name": "English" },
    { "code": "es", "name": "Spanish", "native_name": "Español" },
    { "code": "fr", "name": "French", "native_name": "Français" },
    { "code": "de", "name": "German", "native_name": "Deutsch" },
    { "code": "it", "name": "Italian", "native_name": "Italiano" },
    { "code": "pt", "name": "Portuguese", "native_name": "Português" },
    { "code": "ru", "name": "Russian", "native_name": "Русский" },
    { "code": "zh", "name": "Chinese", "native_name": "中文" },
    { "code": "ja", "name": "Japanese", "native_name": "日本語" },
    { "code": "ko", "name": "Korean", "native_name": "한국어" },
    { "code": "hi", "name": "Hindi", "native_name": "हिन्दी" },
    { "code": "ar", "name": "Arabic", "native_name": "العربية" }
  ]
}
```

---

### POST /form/api/v1/forms/translations/preview

**Summary:** Preview a single text translation using AI.

**Authentication:** `@jwt_required()`

**Request body:**
```json
{
  "text": "Patient Name",
  "source_language": "en",
  "target_language": "hi"
}
```

`source_language` defaults to `"en"` if omitted. `text` and `target_language` are required.

**Behavior:** Calls `AIService.translate_text(text, source_lang, target_lang)` — translates a single string using the configured AI provider.

**Response (200):**
```json
{
  "success": true,
  "data": { "translated_text": "रोगी का नाम" }
}
```

**Error responses:**
- `400` — Missing `text` or `target_language`
- `500` — Translation failed (AI provider error)

---

### GET /form/api/v1/forms/translations/jobs

**Summary:** List translation jobs for a form.

**Authentication:** `@jwt_required()`

**Query parameters:** `form_id` (required)

**Response (200):**
```json
{
  "success": true,
  "data": [
    {
      "id": "job-uuid",
      "form_id": "form-uuid",
      "status": "completed",
      "source_language": "en",
      "target_languages": ["hi", "fr"],
      "progress": 100,
      "created_by": "user-uuid",
      "created_at": "...",
      "started_at": "...",
      "completed_at": "...",
      "results": { "hi": { "success": true, "success_count": 45 } }
    }
  ]
}
```

---

### POST /form/api/v1/forms/translations/jobs

**Summary:** Start a new AI batch translation job.

**Authentication:** `@jwt_required()`

**Request body:**
```json
{
  "form_id": "uuid",
  "source_language": "en",
  "target_languages": ["hi", "fr", "de"],
  "total_fields": 50
}
```

`source_language` defaults to `"en"`. `form_id` and `target_languages` are required.

**Permission check:** `has_form_permission(user, form, "edit")` — 403 if lacking.

**Behavior:**
1. Creates `TranslationJob` document with `status = "pending"`
2. Starts a Python `threading.Thread` running `process_translation_job(job_id, app)`
3. Returns 201 with job ID immediately

**Response (201):**
```json
{
  "success": true,
  "data": { "job_id": "uuid" },
  "message": "Translation job started"
}
```

**Thread behavior (`process_translation_job`):**
1. Sets `status = "inProgress"`, `started_at = now`
2. For each target language:
   a. Checks if job was cancelled (`job.reload().status == "cancelled"`)
   b. Calls `AIService.translate_bulk(translatable_items, source_lang, target_lang)`
   c. Saves translated dict to `latest_version.translations[lang]`
   d. Updates progress percentage
3. Sets `status = "completed"`, `completed_at = now`, saves `results`

Translatable items extracted: form title, description, section titles/descriptions, question labels/help_text/placeholders, option labels.

**Audit log:** Structured with `user_id`, `form_id`, `job_id`, `target_languages`, `action: start_translation_job`

---

### GET /form/api/v1/forms/translations/jobs/`<job_id>`

**Summary:** Get the status and progress of a translation job.

**Authentication:** `@jwt_required()`

**Response (200):** Full `TranslationJob` document.

Status lifecycle: `pending` → `inProgress` → `completed` | `failed` | `cancelled`

**Error responses:**
- `404` — Job not found

---

### PATCH /form/api/v1/forms/translations/jobs/`<job_id>`/cancel

**Summary:** Cancel a pending or in-progress translation job.

**Authentication:** `@jwt_required()`

**Behavior:**
- Sets `job.status = "cancelled"` if current status is `pending` or `in_progress`
- The background thread checks for cancellation between languages
- Cancellation is cooperative, not immediate

**Response (200):**
```json
{
  "success": true,
  "message": "Job cancelled"
}
```

**Error responses:**
- `400` — Job is in a terminal state (`completed`, `failed`) — cannot cancel
- `404` — Job not found

**Audit log:** `action: cancel_translation_job`

---

### DELETE /form/api/v1/forms/translations/jobs/`<job_id>`

**Summary:** Delete a translation job record.

**Authentication:** `@jwt_required()`

**Behavior:** Hard-deletes the `TranslationJob` document from MongoDB.

**Audit log:** `action: delete_translation_job`

---

### GET /form/api/v1/forms/translations/jobs/`<job_id>`/content

**Summary:** Retrieve translated content from a completed job.

**Authentication:** `@jwt_required()`

**Pre-condition:** Job must be in `completed` status (400 if not).

**Response (200):**
```json
{
  "success": true,
  "data": {
    "form_id": "uuid",
    "results": {
      "hi": { "success": true, "success_count": 45, "failure_count": 0 },
      "fr": { "success": true, "success_count": 45, "failure_count": 0 }
    }
  }
}
```

---

## Route Summary

| Method | Path | Auth |
|--------|------|------|
| GET | `/forms/translations` | JWT |
| POST | `/forms/translations` | JWT + edit permission |
| GET | `/forms/translations/languages` | JWT |
| POST | `/forms/translations/preview` | JWT |
| GET | `/forms/translations/jobs` | JWT |
| POST | `/forms/translations/jobs` | JWT + edit permission |
| GET | `/forms/translations/jobs/<id>` | JWT |
| PATCH | `/forms/translations/jobs/<id>/cancel` | JWT |
| DELETE | `/forms/translations/jobs/<id>` | JWT |
| GET | `/forms/translations/jobs/<id>/content` | JWT |

---

## Dependencies

- `TranslationJob` model (`models/TranslationJob.py`)
- `AIService` (`services/ai_service.py`) — `translate_text`, `translate_bulk`
- `Form` model
- `has_form_permission` (`routes/v1/form/helper.py`)
- `threading` (Python stdlib) — for background job execution
