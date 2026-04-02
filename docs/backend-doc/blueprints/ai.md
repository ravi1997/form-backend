# Blueprint: AI (`ai_bp`)

## Registration

| Property | Value |
|----------|-------|
| Blueprint name | `ai` |
| URL prefix | `/form/api/v1/ai` |
| Module | `routes/v1/form/ai.py` |
| Services used | `OllamaService`, `AIService` |

Also registered at `/form/api/v1/ai/search` is `nlp_search_bp` from `routes/v1/form/nlp_search.py`.

---

## Overview

The AI blueprint exposes a public health check endpoint for the AI service layer. It also serves as the parent module for the NLP search blueprint registered at the `/ai/search` sub-prefix.

The blueprint contains significant additional routing for NLP search but these routes are handled by `nlp_search_bp` (a separate blueprint registered at the `/ai/search` prefix). The `ai.py` file also imports and sets up the Ollama and AI service clients.

---

## Route Reference

### GET /form/api/v1/ai/health

**Summary:** Health check for AI services.

**Authentication:** None required — public endpoint, no `@jwt_required()`

**Behavior:**
1. Calls `OllamaService.health_check()` to verify Ollama availability and model list
2. Determines overall status based on Ollama status:
   - If Ollama is `"unavailable"` → overall `"unavailable"`
   - If Ollama is `"degraded"` → overall `"degraded"`
   - Otherwise → overall `"healthy"`

**Response (200):**
```json
{
  "status": "healthy",
  "ollama": {
    "status": "healthy",
    "available": true,
    "models": ["llama3.2", "nomic-embed-text"],
    "default_model": "llama3.2",
    "embedding_model": "nomic-embed-text",
    "latency_ms": 45
  },
  "timestamp": "2026-04-02T10:00:00Z"
}
```

When Ollama is unavailable:
```json
{
  "status": "unavailable",
  "ollama": {
    "status": "unavailable",
    "available": false,
    "models": [],
    "default_model": "llama3.2",
    "embedding_model": "nomic-embed-text",
    "latency_ms": null
  },
  "timestamp": "2026-04-02T10:00:00Z"
}
```

---

## NLP Search Routes (registered at `/form/api/v1/ai/search`)

The following routes are defined in `routes/v1/form/nlp_search.py` and registered at the `/ai/search` sub-prefix.

### GET /form/api/v1/ai/search/nlp-search

**Authentication:** `@jwt_required()`

**Query parameters:** `q` — search query string

Performs keyword-based search across forms and responses.

---

### POST /form/api/v1/ai/search/semantic-search

**Authentication:** `@jwt_required()`

**Request body:**
```json
{ "query": "patient with fever", "form_id": "optional-uuid" }
```

Generates Ollama embeddings for the query, searches against pre-computed response embeddings. Results are cached in Redis with 1-hour TTL. Falls back to keyword search if Ollama is unavailable.

---

### POST /form/api/v1/ai/search/semantic-search/stream

**Authentication:** `@jwt_required()`

Streaming version of semantic search. Returns SSE stream.

---

### GET /form/api/v1/ai/search/search-stats

**Authentication:** `@jwt_required()`

Returns search usage statistics for the current user.

---

### GET /form/api/v1/ai/search/query-suggestions

**Authentication:** `@jwt_required()`

Returns suggested query completions based on search history.

---

### GET /form/api/v1/ai/search/health

**Authentication:** `@jwt_required()`

Health check specific to NLP/semantic search services.

---

### GET /form/api/v1/ai/search/search-history

**Authentication:** `@jwt_required()`

Returns the current user's search history.

### DELETE /form/api/v1/ai/search/search-history

**Authentication:** `@jwt_required()`

Clears the current user's search history.

---

### GET /form/api/v1/ai/search/popular-queries

**Authentication:** `@jwt_required()`

Returns the most frequently searched queries.

---

## AI Service Architecture

| Service | Role |
|---------|------|
| `OllamaService` | Direct Ollama API client. Health check, model listing, embedding generation, text generation. |
| `AIService` | Higher-level service. Wraps Ollama for translation, summarization, batch translation. Respects `AI_PROVIDER` env var. |
| `SummarizationService` | Uses Ollama for response summarization. |

**Configured models (defaults):**
- Generation: `llama3.2`
- Embeddings: `nomic-embed-text`

**AI provider selection:** Controlled by `AI_PROVIDER` env var (`local`, `ollama`, `openai`).

---

## Known Issues

- `nlp_search_bp` has `url_prefix="/ai/search"` in its Blueprint constructor AND is registered at `/form/api/v1/ai/search`. The constructor prefix is ignored at registration — actual prefix is `/form/api/v1/ai/search`. See `risks-and-gaps.md` R-02.
