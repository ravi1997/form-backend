from . import form_bp
from flask import Blueprint, request, jsonify, current_app
from flask_jwt_extended import jwt_required
from models import Form, FormResponse
from routes.v1.form.helper import get_current_user, has_form_permission
from services.ai_service import AIService
from services.ollama_service import OllamaService
from datetime import datetime, timezone
import hashlib
import math
import re
import uuid
from typing import Any, List, Tuple

ai_bp = Blueprint("ai", __name__)


@ai_bp.route("/health", methods=["GET"])
def ai_health_check():
    logger = current_app.logger
    logger.info("--- AI Health Check branch started ---")
    """
    Health check endpoint for AI services.
    
    Returns overall AI service health status including Ollama model availability.
    
    Response format:
    {
        "status": "healthy" | "degraded" | "unavailable",
        "ollama": {
            "status": "healthy" | "degraded" | "unavailable",
            "available": true,
            "models": ["llama3.2", "nomic-embed-text"],
            "default_model": "llama3.2",
            "embedding_model": "nomic-embed-text",
            "latency_ms": 45
        },
        "timestamp": "2026-02-04T10:00:00Z"
    }
    """
    try:
        # Get Ollama health status
        ollama_health = OllamaService.health_check()

        # Determine overall status
        if ollama_health.get("status") == "unavailable":
            overall_status = "unavailable"
        elif ollama_health.get("status") == "degraded":
            overall_status = "degraded"
        else:
            overall_status = "healthy"

        # Build response
        response = {
            "status": overall_status,
            "ollama": {
                "status": ollama_health.get("status"),
                "available": ollama_health.get("available", False),
                "models": ollama_health.get("models", []),
                "default_model": ollama_health.get("default_model"),
                "embedding_model": ollama_health.get("embedding_model"),
                "latency_ms": ollama_health.get("latency_ms"),
            },
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }

        # Add error details if available
        if "error" in ollama_health:
            response["ollama"]["error"] = ollama_health["error"]

        return jsonify(response), 200

    except Exception as e:
        current_app.logger.error(f"AI health check error: {str(e)}")
        return (
            jsonify(
                {
                    "status": "unavailable",
                    "error": str(e),
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                }
            ),
            503,
        )


def simple_sentiment_analyzer(text: str) -> Tuple[str, int]:
    positive_words = {
        "good",
        "great",
        "excellent",
        "happy",
        "satisfied",
        "positive",
        "amazing",
        "wonderful",
        "best",
        "love",
        "perfect",
        "easy",
        "helpful",
        "fast",
        "efficient",
        "thanks",
    }
    negative_words = {
        "bad",
        "poor",
        "unhappy",
        "dissatisfied",
        "negative",
        "terrible",
        "worst",
        "error",
        "fail",
        "slow",
        "broken",
        "hate",
        "hard",
        "useless",
        "expensive",
        "issue",
        "problem",
        "difficult",
    }

    words = re.findall(r"\w+", text.lower())
    pos_count = sum(1 for w in words if w in positive_words)
    neg_count = sum(1 for w in words if w in negative_words)

    score = pos_count - neg_count
    if score > 0:
        return "positive", score
    elif score < 0:
        return "negative", score
    else:
        return "neutral", 0


@ai_bp.route("/<form_id>/responses/<response_id>/analyze", methods=["POST"])
@jwt_required()
def analyze_response_ai(form_id: str, response_id: str) -> Tuple[Any, int]:
    logger = current_app.logger
    logger.info(
        f"--- Analyze Response AI branch started for form_id: {form_id}, response_id: {response_id} ---"
    )
    """
    Perform AI tasks (Sentiment, PII detection) on a response.
    """
    try:
        current_user = get_current_user()
        form = Form.objects.get(id=form_id)
        if not has_form_permission(current_user, form, "view"):
            return jsonify({"error": "Unauthorized"}), 403

        response = FormResponse.objects.get(id=response_id, form=form.id)

        # 1. Sentiment Analysis
        all_text: List[str] = []

        def extract_text(obj: Any) -> None:
            if isinstance(obj, dict):
                for v in obj.values():
                    extract_text(v)
            elif isinstance(obj, list):
                for item in obj:
                    extract_text(item)
            elif isinstance(obj, str):
                all_text.append(obj)

        extract_text(response.data)
        combined_text = " ".join(all_text)

        sentiment, score = simple_sentiment_analyzer(combined_text)

        # 2. PII Detection (Basic)
        email_pattern = r"[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+"
        phone_pattern = r"\b\d{10}\b"

        pii_found = {
            "emails": re.findall(email_pattern, combined_text),
            "phones": re.findall(phone_pattern, combined_text),
        }

        # Update results
        ai_results = getattr(response, "ai_results", {})
        ai_results.update(
            {
                "sentiment": {
                    "label": sentiment,
                    "score": score,
                    "analyzed_at": datetime.now(timezone.utc).isoformat(),
                },
                "pii_scan": {
                    "found_count": len(pii_found["emails"]) + len(pii_found["phones"]),
                    "details": (
                        pii_found
                        if (len(pii_found["emails"]) + len(pii_found["phones"])) > 0
                        else None
                    ),
                },
                "summary": "Processed by Antigravity AI Helper",
            }
        )

        response.update(set__ai_results=ai_results)

        return jsonify({"message": "AI analysis complete", "results": ai_results}), 200

    except Exception as e:
        return jsonify({"error": str(e)}), 400


@ai_bp.route("/<form_id>/responses/<response_id>/moderate", methods=["POST"])
@jwt_required()
def moderate_response_ai(form_id: str, response_id: str) -> Tuple[Any, int]:
    logger = current_app.logger
    logger.info(
        f"--- Moderate Response AI branch started for form_id: {form_id}, response_id: {response_id} ---"
    )
    """
    Deep Content Moderation:
    - Extended PII (SSN, Credit Cards)
    - PHI (Medical terminology)
    - Profanity Filtering
    - Injection Detection (XSS/SQL)
    """
    try:
        current_user = get_current_user()
        form = Form.objects.get(id=form_id)
        if not has_form_permission(current_user, form, "view"):
            return jsonify({"error": "Unauthorized"}), 403

        response = FormResponse.objects.get(id=response_id, form=form.id)

        # 1. Extract all text
        all_text: List[str] = []

        def extract_text(obj: Any) -> None:
            if isinstance(obj, dict):
                for v in obj.values():
                    extract_text(v)
            elif isinstance(obj, list):
                for item in obj:
                    extract_text(item)
            elif isinstance(obj, str):
                all_text.append(obj)

        extract_text(response.data)
        text = " ".join(all_text)
        text_lower = text.lower()

        # 2. Moderation Engines
        flags = []

        # PII Detection (Sensitive)
        pii_patterns = {
            "ssn": r"\b\d{3}-\d{2}-\d{4}\b",
            "credit_card": r"\b(?:\d[ -]*?){13,16}\b",
            "email": r"[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+",
            "phone": r"\b\d{10}\b",
        }
        found_pii = {}
        for key, pattern in pii_patterns.items():
            matches = re.findall(pattern, text)
            if matches:
                found_pii[key] = len(matches)
                flags.append(f"PII Detected: {key.upper()}")

        # PHI Detection (Medical)
        phi_keywords = {
            "diabetes",
            "hiv",
            "cancer",
            "medication",
            "prescription",
            "diagnosis",
            "treatment",
            "therapy",
        }
        found_phi = [w for w in phi_keywords if w in text_lower]
        if found_phi:
            flags.append(f"PHI Potential: {', '.join(found_phi)}")

        # Profanity Detection (Basic)
        profanity_list = {
            "abuse",
            "offensive",
            "violent",
            "vulgar",
        }  # Expanded in real life
        found_profanity = [w for w in profanity_list if w in text_lower]
        if found_profanity:
            flags.append("Warning: Profane or inappropriate language detected")

        # Injection Detection (Security)
        injection_patterns = [
            r"<script",
            r"javascript:",
            r"or 1=1",
            r"drop table",
            r"select \*",
        ]
        found_injection = any(re.search(p, text_lower) for p in injection_patterns)
        if found_injection:
            flags.append("CRITICAL: Potential Code/SQL Injection attempt")

        # Update ai_results
        moderation_results = {
            "is_safe": not (found_profanity or found_injection),
            "flags": flags,
            "pii_summary": found_pii,
            "phi_detected": found_phi,
            "evaluated_at": datetime.now(timezone.utc).isoformat(),
        }

        current_results = getattr(response, "ai_results", {})
        current_results["moderation"] = moderation_results
        response.update(set__ai_results=current_results)

        return (
            jsonify(
                {
                    "message": "Content moderation complete",
                    "moderation": moderation_results,
                }
            ),
            200,
        )

    except Exception as e:
        return jsonify({"error": str(e)}), 400


@ai_bp.route("/generate", methods=["POST"])
@jwt_required()
def generate_form_ai() -> Tuple[Any, int]:
    logger = current_app.logger
    logger.info("--- Generate Form AI branch started ---")
    """
    AI Form Generation using local LLM.
    """
    try:
        data = request.get_json()
        prompt = data.get("prompt")
        current_form = data.get("current_form")  # Optional context

        if not prompt:
            return jsonify({"error": "Prompt is required"}), 400

        form_structure = AIService.generate_form(prompt, current_form)

        return (
            jsonify(
                {"message": "Form generated successfully", "suggestion": form_structure}
            ),
            200,
        )

    except Exception as e:
        current_app.logger.error(f"Generate AI Form Error: {str(e)}")
        return jsonify({"error": str(e)}), 500


@ai_bp.route("/suggestions", methods=["POST"])
@jwt_required()
def get_field_suggestions() -> Tuple[Any, int]:
    """
    AI Field Suggestions based on current form context.
    """
    try:
        data = request.get_json()
        current_form = data.get("current_form")

        if current_form:
            result = AIService.get_suggestions(current_form)
            return jsonify(result), 200

        # Fallback to simulated suggestions if form context is missing
        theme = data.get("theme", "").lower()
        suggestions = []
        if "feedback" in theme or "survey" in theme:
            suggestions = [
                {
                    "label": "How did you hear about us?",
                    "field_type": "select",
                    "options": ["Social Media", "Friend", "Ad"],
                },
                {
                    "label": "On a scale of 1-10, how likely are you to recommend us?",
                    "field_type": "rating",
                },
            ]
        elif "contact" in theme:
            suggestions = [
                {
                    "label": "Preferred method of contact",
                    "field_type": "radio",
                    "options": ["Email", "Phone", "SMS"],
                },
                {"label": "Best time to call", "field_type": "input"},
            ]
        else:
            suggestions = [
                {"label": "Additional Comments", "field_type": "textarea"},
                {
                    "label": "Tags",
                    "field_type": "select",
                    "is_repeatable_question": True,
                },
            ]

        return jsonify({"suggestions": suggestions}), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 400


@ai_bp.route("/<form_id>/validate-design", methods=["POST"])
@jwt_required()
def validate_form_design(form_id: str) -> Tuple[Any, int]:
    """
    Analyzes the form design for UX/logical issues.
    """
    try:
        data = request.get_json()
        form_data = data.get("form")

        if not form_data:
            return jsonify({"error": "Form data is required"}), 400

        result = AIService.analyze_form(form_data)
        return jsonify(result), 200

    except Exception as e:
        current_app.logger.error(f"Validate Form Design Error: {str(e)}")
        return jsonify({"error": str(e)}), 500


@ai_bp.route("/templates", methods=["GET"])
@jwt_required()
def list_ai_templates() -> Tuple[Any, int]:
    """
    List available AI form templates.
    """
    templates = [
        {"id": "patient_reg", "name": "Patient Registration", "category": "Medical"},
        {"id": "emp_boarding", "name": "Employee Onboarding", "category": "HR"},
        {"id": "survey_feedback", "name": "Survey/Feedback", "category": "General"},
        {"id": "event_reg", "name": "Event Registration", "category": "Events"},
        {"id": "app_form", "name": "Application Form", "category": "General"},
        {"id": "incident_report", "name": "Incident Report", "category": "Safety"},
    ]
    return jsonify({"templates": templates}), 200


@ai_bp.route("/templates/<template_id>", methods=["GET"])
@jwt_required()
def get_ai_template(template_id: str) -> Tuple[Any, int]:
    """
    Get a specific AI template structure.
    """
    # Base structure
    template = {"title": template_id.replace("_", " ").title(), "sections": []}

    if template_id == "patient_reg":
        template["sections"] = [
            {
                "title": "Patient Info",
                "questions": [
                    {"label": "Name", "field_type": "input"},
                    {"label": "DOB", "field_type": "date"},
                    {"label": "Insurance ID", "field_type": "input"},
                ],
            }
        ]
    elif template_id == "emp_boarding":
        template["sections"] = [
            {
                "title": "Job Details",
                "questions": [
                    {
                        "label": "Department",
                        "field_type": "select",
                        "options": [
                            {"option_label": "IT", "option_value": "it"},
                            {"option_label": "HR", "option_value": "hr"},
                        ],
                    },
                    {"label": "Start Date", "field_type": "date"},
                ],
            }
        ]
    elif template_id == "incident_report":
        template["sections"] = [
            {
                "title": "Incident Details",
                "questions": [
                    {"label": "Date of Incident", "field_type": "date"},
                    {"label": "Location", "field_type": "input"},
                    {"label": "Describe what happened", "field_type": "textarea"},
                ],
            }
        ]
    else:
        # Generic Template
        template["sections"] = [
            {
                "title": "Section 1",
                "questions": [{"label": "Sample Question", "field_type": "input"}],
            }
        ]

    # Assign UUIDs
    for sec in template["sections"]:
        sec["id"] = str(uuid.uuid4())
        for q in sec["questions"]:
            q["id"] = str(uuid.uuid4())
            if "options" in q:
                for opt in q["options"]:
                    opt["id"] = str(uuid.uuid4())

    return jsonify({"template": template}), 200


@ai_bp.route("/<form_id>/sentiment", methods=["GET"])
@jwt_required()
def get_form_sentiment_trends(form_id: str) -> Tuple[Any, int]:
    logger = current_app.logger
    logger.info(
        f"--- Get Form Sentiment Trends branch started for form_id: {form_id} ---"
    )
    """
    Get sentiment distribution and trends for all responses in a form.
    """
    try:
        current_user = get_current_user()
        form = Form.objects.get(id=form_id)
        if not has_form_permission(current_user, form, "view"):
            return jsonify({"error": "Unauthorized"}), 403

        responses = FormResponse.objects(form=form.id, deleted=False)

        counts = {"positive": 0, "negative": 0, "neutral": 0, "unprocessed": 0}
        total_score = 0
        analyzed_count = 0

        for resp in responses:
            results = getattr(resp, "ai_results", {})
            sentiment_data = results.get("sentiment")
            if sentiment_data:
                label = sentiment_data.get("label", "neutral")
                counts[label] += 1
                total_score += sentiment_data.get("score", 0)
                analyzed_count += 1
            else:
                counts["unprocessed"] += 1

        return (
            jsonify(
                {
                    "form_id": form_id,
                    "total_responses": len(responses),
                    "analyzed_responses": analyzed_count,
                    "distribution": counts,
                    "average_score": (
                        (total_score / analyzed_count) if analyzed_count > 0 else 0
                    ),
                }
            ),
            200,
        )

    except Exception as e:
        return jsonify({"error": str(e)}), 400


@ai_bp.route("/<form_id>/search", methods=["POST"])
@jwt_required()
def ai_powered_search(form_id: str) -> Tuple[Any, int]:
    logger = current_app.logger
    logger.info(f"--- AI Powered Search branch started for form_id: {form_id} ---")
    """
    AI-Powered Smart Search for form responses.
    Translates Natural Language queries into filters.
    
    Features:
    - Natural Language Query Parsing
    - Keyword Extraction
    - Sentiment Filtering (e.g., "unhappy", "satisfied", "positive", "negative")
    - Text Search across all response content
    - Combined Filters
    - Cache bypass support (nocache parameter)
    
    Payload: {
        "query": "search query text",
        "nocache": false (optional, default: false)
    }
    """
    try:
        data = request.get_json()
        query = data.get("query", "").lower()
        nocache = data.get("nocache", False)

        if not query:
            return jsonify({"error": "Search query is required"}), 400

        # Invalidate cache if nocache is true
        if nocache:
            from services.nlp_service import NLPSearchService

            NLPSearchService.invalidate_cache(
                form_id=form_id, pattern="by_query", query=query
            )

        current_user = get_current_user()
        form = Form.objects.get(id=form_id)
        if not has_form_permission(current_user, form, "view"):
            return jsonify({"error": "Unauthorized"}), 403

        # Base filter
        filters = {"form": form.id, "deleted": False}

        # Simulated NL Parsing

        # 1. Sentiment keyword detection
        # Positive sentiment keywords
        positive_sentiment_keywords = {
            "positive",
            "happy",
            "satisfied",
            "good",
            "great",
            "excellent",
            "amazing",
            "wonderful",
            "best",
            "love",
            "perfect",
            "pleased",
            "delighted",
            "thrilled",
            "content",
            "impressed",
            "recommend",
        }
        # Negative sentiment keywords
        negative_sentiment_keywords = {
            "negative",
            "unhappy",
            "dissatisfied",
            "bad",
            "poor",
            "terrible",
            "worst",
            "hate",
            "disappointed",
            "frustrated",
            "angry",
            "upset",
            "annoyed",
            "complaint",
            "issue",
            "problem",
            "concern",
        }
        # Neutral sentiment keywords
        neutral_sentiment_keywords = {
            "neutral",
            "okay",
            "average",
            "normal",
            "typical",
            "standard",
        }

        detected_sentiment = None
        for word in re.findall(r"\w+", query):
            if word in positive_sentiment_keywords:
                detected_sentiment = "positive"
                break
            elif word in negative_sentiment_keywords:
                detected_sentiment = "negative"
                break
            elif word in neutral_sentiment_keywords:
                detected_sentiment = "neutral"
                break

        # 2. Age patterns: "over 60", "under 30", "older than 25"
        age_gt_match = re.search(r"(?:over|older than|above)\s+(\d+)", query)
        age_lt_match = re.search(r"(?:under|younger than|below)\s+(\d+)", query)

        # 3. Keyword extraction (naive)
        # We'll look for words that aren't common stop words/operators or sentiment keywords
        stop_words = {
            "find",
            "all",
            "patients",
            "with",
            "who",
            "are",
            "over",
            "under",
            "is",
            "a",
            "the",
            "and",
            "show",
            "me",
            "users",
            "were",
            "that",
            "for",
            "to",
            "in",
            "at",
            "on",
            "by",
            "about",
            "from",
            "as",
            "of",
            "it",
            "this",
            "these",
            "those",
            "be",
            "been",
            "being",
            "have",
            "has",
            "had",
            "do",
            "does",
            "did",
            "but",
            "or",
            "not",
            "no",
            "yes",
            "if",
            "then",
        }
        # Combine stop words with sentiment keywords for exclusion
        excluded_words = (
            stop_words
            | positive_sentiment_keywords
            | negative_sentiment_keywords
            | neutral_sentiment_keywords
        )
        words = re.findall(r"\w+", query)
        keywords = [w for w in words if w not in excluded_words and not w.isdigit()]

        results = FormResponse.objects(**filters)

        # In-memory filtering for demo/simulation (since data is dict/dynamic)
        final_results = []
        for resp in results:
            match = True
            resp_data_str = str(resp.data).lower()

            # Check sentiment filter
            if detected_sentiment:
                ai_results = getattr(resp, "ai_results", {})
                sentiment_data = ai_results.get("sentiment")
                if sentiment_data:
                    response_sentiment = sentiment_data.get("label")
                    if response_sentiment != detected_sentiment:
                        match = False
                else:
                    # If no sentiment analysis exists, skip this response
                    match = False

            if not match:
                continue

            # Check keywords
            for kw in keywords:
                if kw not in resp_data_str:
                    match = False
                    break

            if not match:
                continue

            # Check Age (if found in query and exists in data)
            # Naive: looks for any number in the data that could be age
            if age_gt_match or age_lt_match:
                # Try to find a number in resp.data that looks like an age
                # For this simulation, we'll just check if any value in the dict is a number
                def find_numbers(d: Any) -> List[float]:
                    nums = []
                    if isinstance(d, dict):
                        for v in d.values():
                            nums.extend(find_numbers(v))
                    elif isinstance(d, list):
                        for v in d:
                            nums.extend(find_numbers(v))
                    elif isinstance(d, (int, float)):
                        nums.append(d)
                    elif isinstance(d, str) and d.isdigit():
                        nums.append(int(d))
                    return nums

                resp_nums = find_numbers(resp.data)

                if age_gt_match:
                    threshold = int(age_gt_match.group(1))
                    if not any(n > threshold for n in resp_nums):
                        match = False

                if age_lt_match:
                    threshold = int(age_lt_match.group(1))
                    if not any(n < threshold for n in resp_nums):
                        match = False

            if match:
                final_results.append(resp)

        # Prepare response with AI analysis results
        results_data = []
        for resp in final_results:
            result_item = {
                "response_id": str(resp.id),
                "data": resp.data,
                "created_at": (
                    resp.created_at.isoformat() if hasattr(resp, "created_at") else None
                ),
                "ai_results": getattr(resp, "ai_results", {}),
            }
            results_data.append(result_item)

        return (
            jsonify(
                {
                    "query": query,
                    "detected_sentiment": detected_sentiment,
                    "detected_keywords": keywords,
                    "count": len(final_results),
                    "results": results_data,
                }
            ),
            200,
        )

    except Exception as e:
        return jsonify({"error": str(e)}), 400


@ai_bp.route("/<form_id>/anomalies", methods=["POST"])
@jwt_required()
def detect_form_anomalies(form_id: str) -> Tuple[Any, int]:
    logger = current_app.logger
    logger.info(f"--- Detect Form Anomalies branch started for form_id: {form_id} ---")
    """
    Scans form responses for anomalies:
    1. Duplicate content (Spam detection)
    2. Statistical Outliers in numerical fields
    3. Gibberish/Short text detection
    """
    try:
        current_user = get_current_user()
        form = Form.objects.get(id=form_id)
        if not has_form_permission(current_user, form, "view"):
            return jsonify({"error": "Unauthorized"}), 403

        responses = FormResponse.objects(form=form.id, deleted=False)
        if len(responses) < 3:
            return (
                jsonify(
                    {
                        "message": "Not enough data for anomaly detection (min 3 responses required)",
                        "anomalies": [],
                    }
                ),
                200,
            )

        flagged = []

        # 1. Duplicate Detection
        content_hashes = {}

        # 2. Outlier detection prep
        num_values_per_question = {}  # {qid: [list of values]}

        def process_data(data: Any, resp_id: str) -> List[str]:
            flat_items = []
            if isinstance(data, dict):
                for k, v in data.items():
                    if isinstance(v, (int, float)):
                        num_values_per_question.setdefault(k, []).append((v, resp_id))
                    elif isinstance(v, str):
                        flat_items.append(v)
                    elif isinstance(v, (dict, list)):
                        flat_items.extend(process_data(v, resp_id))
            return flat_items

        all_resp_text = {}  # {resp_id: combined_text}

        for resp in responses:
            rid = str(resp.id)
            text_parts = process_data(resp.data, rid)
            combined = " ".join(text_parts).strip()
            all_resp_text[rid] = combined

            # Duplicate check
            if combined and combined in content_hashes:
                flagged.append(
                    {
                        "response_id": rid,
                        "type": "duplicate",
                        "confidence": 0.9,
                        "reason": f"Content matches response {content_hashes[combined]}",
                    }
                )
            content_hashes[combined] = rid

            # 3. Gibberish Check (Simple heuristic: very short or low vowel count)
            if combined and len(combined) > 0:
                vowels = len(re.findall(r"[aeiou]", combined.lower()))
                if len(combined) > 10 and vowels / len(combined) < 0.1:
                    flagged.append(
                        {
                            "response_id": rid,
                            "type": "low_quality",
                            "confidence": 0.7,
                            "reason": "Text pattern looks like gibberish (low vowel ratio)",
                        }
                    )

        # Statistical Outliers (Z-Score method baseline)
        for qid, items in num_values_per_question.items():
            if len(items) < 3:
                continue

            vals = [x[0] for x in items]
            mean = sum(vals) / len(vals)
            variance = sum((x - mean) ** 2 for x in vals) / len(vals)
            std_dev = math.sqrt(variance)

            if std_dev == 0:
                continue

            for val, rid in items:
                z_score = abs(val - mean) / std_dev
                if z_score > 2:  # 2 Sigma threshold
                    flagged.append(
                        {
                            "response_id": rid,
                            "type": "outlier",
                            "confidence": min(0.9, z_score / 5),
                            "reason": f"Value {val} is a statistical outlier for field {qid}",
                        }
                    )

        return (
            jsonify(
                {
                    "form_id": form_id,
                    "total_scanned": len(responses),
                    "anomaly_count": len(flagged),
                    "anomalies": flagged,
                }
            ),
            200,
        )

    except Exception as e:
        return jsonify({"error": str(e)}), 400


@ai_bp.route("/<form_id>/anomaly-detect", methods=["POST"])
@jwt_required()
def detect_predictive_anomalies(form_id: str) -> Tuple[Any, int]:
    logger = current_app.logger
    logger.info(
        f"--- Detect Predictive Anomalies branch started for form_id: {form_id} ---"
    )
    """
    Predictive Anomaly Detection for form responses.
    
    Features:
    1. Spam Detection: Identify bot-like patterns, repeated content, suspicious timing
    2. Statistical Anomaly Detection: Flag responses that deviate significantly from historical patterns
    3. Content Duplication: Detect repeated or copy-pasted responses
    4. Timing Analysis: Identify responses submitted at unusual times or with suspicious speed
    5. Historical Baseline: Calculate baseline metrics from historical responses
    
    Detection Rules:
    - Spam Score (0-100):
      - Repeated content: +30
      - Very short responses (<10 chars): +20
      - Extremely fast submission (<2 seconds): +25
      - All caps content: +15
      - Contains typical spam words: +20
    
    - Statistical Anomalies:
      - Response length more than 3 std devs from mean: flag
      - Sentiment score more than 3 std devs from mean: flag
    """
    try:
        current_user = get_current_user()
        form = Form.objects.get(id=form_id)
        if not has_form_permission(current_user, form, "view"):
            return jsonify({"error": "Unauthorized"}), 403

        responses = FormResponse.objects(form=form.id, deleted=False)
        responses_list = list(responses)

        if len(responses_list) < 3:
            return (
                jsonify(
                    {
                        "message": "Not enough data for anomaly detection (min 3 responses required)",
                        "baseline": None,
                        "flagged_responses": [],
                    }
                ),
                200,
            )

        # Spam detection keywords
        spam_keywords = {
            "free",
            "winner",
            "click here",
            "subscribe",
            "limited time",
            "act now",
            "congratulations",
            "you have won",
            "prize",
            "bonus",
            "cash",
            "money",
            "earn",
            "make money",
            "work from home",
            "easy money",
            "guaranteed",
            "no risk",
            "trial",
            "exclusive",
            "urgent",
            "immediately",
            "hurry",
        }

        # Step 1: Build Historical Baseline
        baseline = {
            "response_count": len(responses_list),
            "avg_response_length": 0,
            "std_response_length": 0,
            "avg_sentiment_score": 0,
            "std_sentiment_score": 0,
            "avg_submission_time": 0,
            "submission_time_std": 0,
            "content_hashes": {},
            "response_lengths": [],
            "sentiment_scores": [],
            "submission_times": [],
        }

        # Helper function to extract all text from response data
        def extract_text_from_data(data: Any) -> List[str]:
            text_parts = []
            if isinstance(data, dict):
                for v in data.values():
                    text_parts.extend(extract_text_from_data(v))
            elif isinstance(data, list):
                for item in data:
                    text_parts.extend(extract_text_from_data(item))
            elif isinstance(data, str):
                text_parts.append(data)
            return text_parts

        # Process responses for baseline
        for resp in responses_list:
            rid = str(resp.id)
            text_parts = extract_text_from_data(resp.data)
            combined_text = " ".join(text_parts).strip()

            # Response length
            text_length = len(combined_text)
            baseline["response_lengths"].append(text_length)

            # Content hash for duplication detection
            content_hash = hashlib.md5(combined_text.encode()).hexdigest()
            baseline["content_hashes"][rid] = content_hash

            # Sentiment score
            sentiment_score = 0
            ai_results = getattr(resp, "ai_results", {})
            sentiment_data = ai_results.get("sentiment")
            if sentiment_data:
                sentiment_score = sentiment_data.get("score", 0)
            baseline["sentiment_scores"].append(sentiment_score)

            # Submission time (calculate duration if available)
            submission_time = 0
            if hasattr(resp, "created_at") and hasattr(resp, "submitted_at"):
                if resp.created_at and resp.submitted_at:
                    delta = resp.submitted_at - resp.created_at
                    submission_time = delta.total_seconds()
            baseline["submission_times"].append(submission_time)
        # Calculate baseline statistics

        # Response length statistics
        baseline["avg_response_length"] = sum(baseline["response_lengths"]) / len(
            baseline["response_lengths"]
        )
        variance_length = sum(
            (x - baseline["avg_response_length"]) ** 2
            for x in baseline["response_lengths"]
        ) / len(baseline["response_lengths"])
        baseline["std_response_length"] = math.sqrt(variance_length)

        # Sentiment score statistics
        baseline["avg_sentiment_score"] = sum(baseline["sentiment_scores"]) / len(
            baseline["sentiment_scores"]
        )
        variance_sentiment = sum(
            (x - baseline["avg_sentiment_score"]) ** 2
            for x in baseline["sentiment_scores"]
        ) / len(baseline["sentiment_scores"])
        baseline["std_sentiment_score"] = math.sqrt(variance_sentiment)

        # Submission time statistics (exclude zeros)
        valid_times = [t for t in baseline["submission_times"] if t > 0]
        if valid_times:
            baseline["avg_submission_time"] = sum(valid_times) / len(valid_times)
            variance_time = sum(
                (x - baseline["avg_submission_time"]) ** 2 for x in valid_times
            ) / len(valid_times)
            baseline["submission_time_std"] = math.sqrt(variance_time)

        # Step 2: Score each response for anomalies
        flagged_responses = []

        # Track content hash frequencies for duplication detection
        hash_counts = {}
        for rid, content_hash in baseline["content_hashes"].items():
            hash_counts[content_hash] = hash_counts.get(content_hash, 0) + 1

        for resp in responses_list:
            rid = str(resp.id)
            text_parts = extract_text_from_data(resp.data)
            combined_text = " ".join(text_parts).strip()
            text_lower = combined_text.lower()

            spam_score = 0
            spam_reasons = []
            statistical_flags = []

            # 1. Content Duplication Detection
            content_hash = baseline["content_hashes"][rid]
            if hash_counts[content_hash] > 1:
                spam_score += 30
                spam_reasons.append(
                    f"Duplicate content (appears {hash_counts[content_hash]} times)"
                )

            # 2. Very Short Response Detection
            if len(combined_text) < 10:
                spam_score += 20
                spam_reasons.append("Very short response (<10 characters)")

            # 3. Extremely Fast Submission Detection
            submission_time = 0
            if hasattr(resp, "created_at") and hasattr(resp, "submitted_at"):
                if resp.created_at and resp.submitted_at:
                    delta = resp.submitted_at - resp.created_at
                    submission_time = delta.total_seconds()

            if submission_time > 0 and submission_time < 2:
                spam_score += 25
                spam_reasons.append(
                    f"Suspiciously fast submission ({submission_time:.2f} seconds)"
                )

            # 4. All Caps Content Detection
            if len(combined_text) > 5:
                uppercase_ratio = sum(1 for c in combined_text if c.isupper()) / len(
                    combined_text
                )
                if uppercase_ratio > 0.8:
                    spam_score += 15
                    spam_reasons.append("Content is mostly uppercase")

            # 5. Spam Words Detection
            found_spam_words = [word for word in spam_keywords if word in text_lower]
            if found_spam_words:
                spam_score += 20
                spam_reasons.append(
                    f"Contains spam words: {', '.join(found_spam_words[:3])}"
                )

            # 6. Statistical Anomaly - Response Length
            text_length = len(combined_text)
            if baseline["std_response_length"] > 0:
                z_score_length = (
                    abs(text_length - baseline["avg_response_length"])
                    / baseline["std_response_length"]
                )
                if z_score_length > 3:
                    statistical_flags.append(
                        f"Response length outlier (z-score: {z_score_length:.2f})"
                    )

            # 7. Statistical Anomaly - Sentiment Score
            sentiment_score = 0
            ai_results = getattr(resp, "ai_results", {})
            sentiment_data = ai_results.get("sentiment")
            if sentiment_data:
                sentiment_score = sentiment_data.get("score", 0)

            if baseline["std_sentiment_score"] > 0:
                z_score_sentiment = (
                    abs(sentiment_score - baseline["avg_sentiment_score"])
                    / baseline["std_sentiment_score"]
                )
                if z_score_sentiment > 3:
                    statistical_flags.append(
                        f"Sentiment score outlier (z-score: {z_score_sentiment:.2f})"
                    )

            # Flag response if any anomalies detected
            if spam_score > 0 or statistical_flags:
                flagged_response = {
                    "response_id": rid,
                    "spam_score": min(spam_score, 100),
                    "spam_indicators": spam_reasons,
                    "statistical_anomalies": statistical_flags,
                    "is_flagged": True,
                    "severity": (
                        "high"
                        if spam_score >= 50 or len(statistical_flags) >= 2
                        else (
                            "medium"
                            if spam_score >= 25 or len(statistical_flags) >= 1
                            else "low"
                        )
                    ),
                    "analysis": {
                        "response_length": text_length,
                        "sentiment_score": sentiment_score,
                        "submission_time_seconds": (
                            submission_time if submission_time > 0 else None
                        ),
                    },
                }
                flagged_responses.append(flagged_response)

        # Sort flagged responses by spam score (highest first)
        flagged_responses.sort(key=lambda x: x["spam_score"], reverse=True)

        return (
            jsonify(
                {
                    "form_id": form_id,
                    "baseline": {
                        "total_responses": baseline["response_count"],
                        "avg_response_length": round(
                            baseline["avg_response_length"], 2
                        ),
                        "std_response_length": round(
                            baseline["std_response_length"], 2
                        ),
                        "avg_sentiment_score": round(
                            baseline["avg_sentiment_score"], 2
                        ),
                        "std_sentiment_score": round(
                            baseline["std_sentiment_score"], 2
                        ),
                        "avg_submission_time": (
                            round(baseline["avg_submission_time"], 2)
                            if baseline["avg_submission_time"] > 0
                            else None
                        ),
                        "submission_time_std": (
                            round(baseline["submission_time_std"], 2)
                            if baseline["submission_time_std"] > 0
                            else None
                        ),
                    },
                    "total_scanned": len(responses_list),
                    "flagged_count": len(flagged_responses),
                    "flagged_responses": flagged_responses,
                    "analyzed_at": datetime.now(timezone.utc).isoformat(),
                }
            ),
            200,
        )

    except Form.DoesNotExist:
        return jsonify({"error": "Form not found"}), 404
    except Exception as e:
        current_app.logger.error(f"Predictive Anomaly Detection Error: {str(e)}")
        return jsonify({"error": str(e)}), 400


@ai_bp.route("/<form_id>/security-scan", methods=["POST"])
@jwt_required()
def scan_form_security_ai(form_id: str) -> Tuple[Any, int]:
    """
    Automated Security Scanning for Form Definitions.
    Analyzes questions, settings, and permissions for vulnerabilities.
    """
    try:
        current_user = get_current_user()
        form = Form.objects.get(id=form_id)
        if not has_form_permission(current_user, form, "edit"):
            return jsonify({"error": "Unauthorized"}), 403

        findings = []
        recommendations = []
        score = 100

        # 1. Public Access Check
        is_public = getattr(form, "is_public", False)

        # 2. Section/Question Scan
        sensitive_keywords = {
            "ssn",
            "password",
            "credit card",
            "pin",
            "otp",
            "medical",
            "health",
            "bank",
        }
        text_fields_without_validation = 0
        sensitive_fields_found = []

        for section in form.versions[-1].sections:
            for question in section.questions:
                label_lower = question.label.lower()

                # Identify sensitive fields
                if any(kw in label_lower for kw in sensitive_keywords):
                    sensitive_fields_found.append(question.label)
                    if is_public:
                        findings.append(
                            {
                                "severity": "HIGH",
                                "issue": f"Sensitive field '{question.label}' exposed on Public Form",
                                "detail": "Asking for sensitive information on a form without authentication is a significant privacy risk.",
                            }
                        )
                        score -= 20

                # Spam risk check
                if question.field_type in ["input", "textarea"]:
                    # Check if any validation exists (required or regex rules)
                    has_validation = question.is_required or getattr(
                        question, "validation_rules", None
                    )
                    if not has_validation:
                        text_fields_without_validation += 1

        if text_fields_without_validation > 3:
            findings.append(
                {
                    "severity": "MEDIUM",
                    "issue": "High Spam Risk",
                    "detail": f"{text_fields_without_validation} open text fields found without validation rules.",
                }
            )
            score -= 10
            recommendations.append(
                "Add regex or length constraints to open text fields to prevent automated spam."
            )

        # 3. Custom Script Scan
        custom_script = getattr(form, "custom_script", None)
        if custom_script:
            findings.append(
                {
                    "severity": "LOW",
                    "issue": "Active Custom Script",
                    "detail": "Custom scripts can execute server-side logic. Ensure this script is audited for security.",
                }
            )
            recommendations.append(
                "Regularly review custom scripts for potential injection or data leakage vulnerabilities."
            )

        # Final Score Logic
        score = max(0, score)
        status = "PASSED" if score >= 80 else "WARNING" if score >= 50 else "FAILED"

        report = {
            "form_id": form_id,
            "security_score": score,
            "status": status,
            "findings": findings,
            "recommendations": recommendations,
            "scanned_at": datetime.now(timezone.utc).isoformat(),
        }

        # Store report in form if necessary (optional)
        # form.update(set__security_report=report)

        return jsonify(report), 200

    except Exception as e:
        return jsonify({"error": str(e)}), 400


@ai_bp.route("/cross-analysis", methods=["POST"])
@jwt_required()
def compare_forms_ai() -> Tuple[Any, int]:
    """
    Compare multiple forms' performance and sentiment.
    Payload: { "form_ids": ["id1", "id2"] }
    """
    try:
        data = request.get_json()
        form_ids = data.get("form_ids", [])

        if not form_ids or not isinstance(form_ids, list):
            return jsonify({"error": "form_ids list is required"}), 400

        current_user = get_current_user()

        results = []
        global_stats = {
            "total_forms": len(form_ids),
            "total_responses": 0,
            "average_sentiment_score": 0,
        }

        total_sentiment_sum = 0
        forms_with_sentiment = 0

        for fid in form_ids:
            try:
                form = Form.objects.get(id=fid)
                # Check permission for each form
                if not has_form_permission(current_user, form, "view"):
                    # For security, we can either fail hard or skip.
                    # Failing hard is safer to prevent enumeration.
                    return jsonify({"error": f"Unauthorized access to form {fid}"}), 403

                responses = FormResponse.objects(form=fid, deleted=False)
                resp_count = len(responses)

                # Aggregation
                sentiment_counts = {
                    "positive": 0,
                    "negative": 0,
                    "neutral": 0,
                    "unprocessed": 0,
                }
                form_total_score = 0
                analyzed_count = 0

                for r in responses:
                    res = getattr(r, "ai_results", {})
                    sent = res.get("sentiment")
                    if sent:
                        label = sent.get("label", "neutral")
                        sentiment_counts[label] = sentiment_counts.get(label, 0) + 1
                        form_total_score += sent.get("score", 0)
                        analyzed_count += 1
                    else:
                        sentiment_counts["unprocessed"] += 1

                avg_score = (
                    (form_total_score / analyzed_count) if analyzed_count > 0 else 0
                )

                results.append(
                    {
                        "form_id": str(form.id),
                        "title": form.title,
                        "response_count": resp_count,
                        "sentiment_distribution": sentiment_counts,
                        "average_sentiment": avg_score,
                    }
                )

                global_stats["total_responses"] += resp_count
                if analyzed_count > 0:
                    total_sentiment_sum += avg_score
                    forms_with_sentiment += 1

            except Form.DoesNotExist:
                return jsonify({"error": f"Form {fid} not found"}), 404

        global_stats["average_sentiment_score"] = (
            (total_sentiment_sum / forms_with_sentiment)
            if forms_with_sentiment > 0
            else 0
        )

        return jsonify({"summary": global_stats, "details": results}), 200

    except Exception as e:
        return jsonify({"error": str(e)}), 400


@ai_bp.route("/<form_id>/summarize", methods=["POST"])
@jwt_required()
def summarize_form_responses(form_id: str) -> Tuple[Any, int]:
    """
    NLP Summarization: Summarize hundreds of feedback responses into 3 bullet points.

    Uses extractive summarization with keyword extraction and sentiment grouping.

    Payload: {
        "response_ids": ["id1", "id2", ...] (optional, defaults to all responses),
        "max_bullet_points": 3,
        "include_sentiment": true,
        "nocache": false (optional, default: false)
    }
    """
    try:
        data = request.get_json() or {}
        response_ids = data.get("response_ids")
        max_bullets = data.get("max_bullet_points", 3)
        include_sentiment = data.get("include_sentiment", True)
        nocache = data.get("nocache", False)

        # Invalidate cache if nocache is true
        if nocache:
            from services.summarization_service import SummarizationService

            SummarizationService.invalidate_cache(form_id=form_id, pattern="by_form")

        current_user = get_current_user()
        form = Form.objects.get(id=form_id)
        if not has_form_permission(current_user, form, "view"):
            return jsonify({"error": "Unauthorized"}), 403

        # Get responses
        if response_ids:
            responses = FormResponse.objects(
                id__in=response_ids, form=form.id, deleted=False
            )
        else:
            responses = FormResponse.objects(form=form.id, deleted=False)

        responses = list(responses)
        if len(responses) < 2:
            return (
                jsonify({"error": "At least 2 responses required for summarization"}),
                400,
            )

        # Extract all text content from responses
        response_texts = []  # List of {id, text, sentiment}

        def extract_text(obj: Any, texts: List[str]) -> None:
            if isinstance(obj, dict):
                for v in obj.values():
                    extract_text(v, texts)
            elif isinstance(obj, list):
                for item in obj:
                    extract_text(item, texts)
            elif isinstance(obj, str) and obj.strip():
                texts.append(obj.strip())

        for resp in responses:
            texts = []
            extract_text(resp.data, texts)
            combined = " ".join(texts)
            if combined:
                # Get sentiment if available
                sentiment = "neutral"
                score = 0
                ai_results = getattr(resp, "ai_results", {})
                if include_sentiment and "sentiment" in ai_results:
                    sentiment = ai_results["sentiment"].get("label", "neutral")
                    score = ai_results["sentiment"].get("score", 0)

                response_texts.append(
                    {
                        "id": str(resp.id),
                        "text": combined,
                        "sentiment": sentiment,
                        "score": score,
                    }
                )

        if not response_texts:
            return jsonify({"error": "No text content found in responses"}), 400

        # Extractive Summarization Algorithm
        summary_points = []

        # 1. Keyword Extraction using TF-IDF-like scoring
        stop_words = {
            "the",
            "a",
            "an",
            "and",
            "or",
            "but",
            "in",
            "on",
            "at",
            "to",
            "for",
            "of",
            "with",
            "by",
            "from",
            "as",
            "is",
            "was",
            "are",
            "were",
            "been",
            "be",
            "have",
            "has",
            "had",
            "do",
            "does",
            "did",
            "will",
            "would",
            "could",
            "should",
            "may",
            "might",
            "must",
            "shall",
            "can",
            "need",
            "this",
            "that",
            "these",
            "those",
            "i",
            "you",
            "he",
            "she",
            "it",
            "we",
            "they",
            "what",
            "which",
            "who",
            "whom",
            "whose",
            "where",
            "when",
            "why",
            "how",
            "all",
            "each",
            "every",
            "both",
            "few",
            "more",
            "most",
            "other",
            "some",
            "such",
            "no",
            "nor",
            "not",
            "only",
            "own",
            "same",
            "so",
            "than",
            "too",
            "very",
            "just",
            "also",
        }

        # Word frequency
        word_freq = {}
        for rt in response_texts:
            words = re.findall(r"\w+", rt["text"].lower())
            for word in words:
                if len(word) > 2 and word not in stop_words:
                    word_freq[word] = word_freq.get(word, 0) + 1

        # Score sentences by keyword density
        scored_sentences = []
        for rt in response_texts:
            words = re.findall(r"\w+", rt["text"].lower())
            score = sum(word_freq.get(w, 0) for w in words if w in word_freq)
            # Normalize by length
            if words:
                score = score / len(words)
            scored_sentences.append(
                {"text": rt["text"], "score": score, "sentiment": rt["sentiment"]}
            )

        # Sort by score and select top sentences
        scored_sentences.sort(key=lambda x: x["score"], reverse=True)

        # Group by sentiment and pick diverse representatives
        sentiment_groups = {"positive": [], "negative": [], "neutral": []}
        for item in scored_sentences:
            sentiment_groups[item["sentiment"]].append(item)

        # Distribute bullet points across sentiments
        bullet_per_sentiment = max_bullets // 3
        remainder = max_bullets % 3

        sentiment_order = ["negative", "positive", "neutral"]
        for i, sentiment in enumerate(sentiment_order):
            count = bullet_per_sentiment + (1 if i < remainder else 0)
            for item in sentiment_groups[sentiment][:count]:
                if len(summary_points) < max_bullets:
                    # Truncate long sentences
                    text = item["text"]
                    if len(text) > 200:
                        text = text[:197] + "..."
                    summary_points.append(
                        {
                            "point": text,
                            "sentiment": sentiment,
                            "confidence": round(min(item["score"] / 10, 1.0), 2),
                        }
                    )

        # Sort by sentiment priority (negative first for actionable insights)
        sentiment_priority = {"negative": 0, "positive": 1, "neutral": 2}
        summary_points.sort(key=lambda x: sentiment_priority.get(x["sentiment"], 2))

        # Generate overall sentiment summary
        sentiment_counts = {"positive": 0, "negative": 0, "neutral": 0}
        for rt in response_texts:
            sentiment_counts[rt["sentiment"]] = (
                sentiment_counts.get(rt["sentiment"], 0) + 1
            )

        dominant_sentiment = max(sentiment_counts, key=sentiment_counts.get)

        return (
            jsonify(
                {
                    "form_id": form_id,
                    "responses_analyzed": len(response_texts),
                    "summary": {
                        "bullet_points": [p["point"] for p in summary_points],
                        "sentiment_distribution": sentiment_counts,
                        "dominant_sentiment": dominant_sentiment,
                        "key_insights": summary_points,
                    },
                    "generated_at": datetime.now(timezone.utc).isoformat(),
                }
            ),
            200,
        )

    except Form.DoesNotExist:
        return jsonify({"error": "Form not found"}), 404
    except Exception as e:
        current_app.logger.error(f"Summarization Error: {str(e)}")
        return jsonify({"error": str(e)}), 400


@ai_bp.route("/<form_id>/export", methods=["POST"])
@jwt_required()
def export_form_ai_report(form_id: str) -> Tuple[Any, int]:
    """
    Generate AI-powered export reports for form analytics.

    Supports multiple export formats (PDF, Excel, CSV) with AI-generated insights.
    Includes sentiment distribution, key insights, and charts data for visualization.

    Payload: {
        "format": "pdf" | "excel" | "csv" | "json",
        "include_raw_data": true,
        "include_charts": true
    }

    Returns JSON data that can be converted to the requested format by the frontend.
    """
    try:
        data = request.get_json() or {}
        export_format = data.get("format", "json").lower()
        include_raw_data = data.get("include_raw_data", True)
        include_charts = data.get("include_charts", True)

        # Validate export format
        valid_formats = ["pdf", "excel", "csv", "json"]
        if export_format not in valid_formats:
            return (
                jsonify(
                    {
                        "error": f"Invalid format. Supported formats: {', '.join(valid_formats)}"
                    }
                ),
                400,
            )

        # Authentication and authorization
        current_user = get_current_user()
        form = Form.objects.get(id=form_id)
        if not has_form_permission(current_user, form, "view"):
            return jsonify({"error": "Unauthorized"}), 403

        # Get all form responses
        responses = FormResponse.objects(form=form.id, deleted=False)
        responses_list = list(responses)
        total_responses = len(responses_list)

        # 1. Generate AI Summary - Sentiment Distribution
        sentiment_counts = {
            "positive": 0,
            "negative": 0,
            "neutral": 0,
            "unprocessed": 0,
        }
        sentiment_scores = []
        analyzed_count = 0

        for resp in responses_list:
            ai_results = getattr(resp, "ai_results", {})
            sentiment_data = ai_results.get("sentiment")
            if sentiment_data:
                label = sentiment_data.get("label", "neutral")
                sentiment_counts[label] = sentiment_counts.get(label, 0) + 1
                sentiment_scores.append(sentiment_data.get("score", 0))
                analyzed_count += 1
            else:
                sentiment_counts["unprocessed"] += 1

        average_sentiment = (
            sum(sentiment_scores) / len(sentiment_scores) if sentiment_scores else 0
        )
        dominant_sentiment = max(
            {k: v for k, v in sentiment_counts.items() if k != "unprocessed"},
            key=sentiment_counts.get,
            default="neutral",
        )

        # 2. Generate Key Insights
        insights = []

        # Insight: Response volume
        if total_responses > 0:
            insights.append(
                {
                    "type": "volume",
                    "message": f"Form has received {total_responses} total responses.",
                    "priority": "info",
                }
            )

        # Insight: Sentiment analysis
        if analyzed_count > 0:
            sentiment_percentage = (analyzed_count / total_responses) * 100
            insights.append(
                {
                    "type": "sentiment",
                    "message": f"{sentiment_percentage:.1f}% of responses have been analyzed for sentiment. "
                    f"Dominant sentiment is {dominant_sentiment.upper()} with an average score of {average_sentiment:.2f}.",
                    "priority": "info",
                }
            )

            # Alert if negative sentiment is high
            if sentiment_counts.get("negative", 0) > sentiment_counts.get(
                "positive", 0
            ):
                insights.append(
                    {
                        "type": "alert",
                        "message": f"Negative responses ({sentiment_counts['negative']}) exceed positive ones ({sentiment_counts['positive']}). "
                        f"Consider reviewing feedback for improvement areas.",
                        "priority": "warning",
                    }
                )

        # Insight: Unprocessed responses
        if sentiment_counts["unprocessed"] > 0:
            insights.append(
                {
                    "type": "action",
                    "message": f"{sentiment_counts['unprocessed']} responses have not been analyzed yet. "
                    f"Run AI analysis to get complete insights.",
                    "priority": "info",
                }
            )

        # Insight: PII detection summary
        pii_detected_count = 0
        for resp in responses_list:
            ai_results = getattr(resp, "ai_results", {})
            pii_scan = ai_results.get("pii_scan")
            if pii_scan and pii_scan.get("found_count", 0) > 0:
                pii_detected_count += 1

        if pii_detected_count > 0:
            insights.append(
                {
                    "type": "security",
                    "message": f"PII (Personally Identifiable Information) detected in {pii_detected_count} response(s). "
                    f"Review and handle according to data privacy policies.",
                    "priority": "warning",
                }
            )

        # Insight: Moderation flags
        moderation_flags_count = 0
        for resp in responses_list:
            ai_results = getattr(resp, "ai_results", {})
            moderation = ai_results.get("moderation")
            if moderation and not moderation.get("is_safe", True):
                moderation_flags_count += 1

        if moderation_flags_count > 0:
            insights.append(
                {
                    "type": "security",
                    "message": f"{moderation_flags_count} response(s) have been flagged by content moderation. "
                    f"Review for inappropriate content or security issues.",
                    "priority": "critical",
                }
            )

        # 3. Generate Charts Data for Visualization
        charts_data = {}

        if include_charts:
            # Sentiment Distribution Pie Chart
            charts_data["sentiment_distribution"] = {
                "type": "pie",
                "title": "Sentiment Distribution",
                "data": [
                    {
                        "label": "Positive",
                        "value": sentiment_counts["positive"],
                        "color": "#10B981",
                    },
                    {
                        "label": "Negative",
                        "value": sentiment_counts["negative"],
                        "color": "#EF4444",
                    },
                    {
                        "label": "Neutral",
                        "value": sentiment_counts["neutral"],
                        "color": "#6B7280",
                    },
                    {
                        "label": "Unprocessed",
                        "value": sentiment_counts["unprocessed"],
                        "color": "#9CA3AF",
                    },
                ],
            }

            # Sentiment Trend Over Time (Line Chart)
            timeline_data = {}
            for resp in responses_list:
                date_key = (
                    resp.submitted_at.strftime("%Y-%m-%d")
                    if resp.submitted_at
                    else "unknown"
                )
                if date_key not in timeline_data:
                    timeline_data[date_key] = {
                        "positive": 0,
                        "negative": 0,
                        "neutral": 0,
                    }

                ai_results = getattr(resp, "ai_results", {})
                sentiment_data = ai_results.get("sentiment")
                if sentiment_data:
                    label = sentiment_data.get("label", "neutral")
                    if label in timeline_data[date_key]:
                        timeline_data[date_key][label] += 1

            sorted_dates = sorted(timeline_data.keys())
            charts_data["sentiment_trend"] = {
                "type": "line",
                "title": "Sentiment Trend Over Time",
                "labels": sorted_dates,
                "datasets": [
                    {
                        "label": "Positive",
                        "data": [timeline_data[d]["positive"] for d in sorted_dates],
                        "color": "#10B981",
                    },
                    {
                        "label": "Negative",
                        "data": [timeline_data[d]["negative"] for d in sorted_dates],
                        "color": "#EF4444",
                    },
                    {
                        "label": "Neutral",
                        "data": [timeline_data[d]["neutral"] for d in sorted_dates],
                        "color": "#6B7280",
                    },
                ],
            }

            # Response Volume Bar Chart
            charts_data["response_volume"] = {
                "type": "bar",
                "title": "Response Volume by Date",
                "labels": sorted_dates,
                "data": [sum(timeline_data[d].values()) for d in sorted_dates],
                "color": "#3B82F6",
            }

        # 4. Raw Data Export (if requested)
        raw_data = []
        if include_raw_data:
            for resp in responses_list:
                response_entry = {
                    "response_id": str(resp.id),
                    "submitted_at": (
                        resp.submitted_at.isoformat() if resp.submitted_at else None
                    ),
                    "submitted_by": resp.submitted_by,
                    "status": resp.status,
                    "is_draft": resp.is_draft,
                    "data": resp.data,
                    "ai_results": getattr(resp, "ai_results", {}),
                }
                raw_data.append(response_entry)

        # 5. Form Metadata
        form_metadata = {
            "form_id": str(form.id),
            "title": form.title,
            "description": form.description,
            "status": form.status,
            "created_at": form.created_at.isoformat() if form.created_at else None,
            "created_by": form.created_by,
            "is_public": form.is_public,
            "total_responses": total_responses,
        }

        # 6. Build the Export Report
        export_report = {
            "report_type": "AI Export Report",
            "format": export_format,
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "generated_by": str(current_user.id) if current_user else "system",
            # Form Information
            "form": form_metadata,
            # AI Summary
            "ai_summary": {
                "total_responses": total_responses,
                "analyzed_responses": analyzed_count,
                "sentiment_distribution": sentiment_counts,
                "average_sentiment_score": round(average_sentiment, 2),
                "dominant_sentiment": dominant_sentiment,
                "pii_detections": pii_detected_count,
                "moderation_flags": moderation_flags_count,
            },
            # Key Insights
            "key_insights": insights,
            # Charts Data
            "charts": charts_data if include_charts else {},
            # Raw Data
            "raw_data": raw_data if include_raw_data else [],
        }

        # Return format-specific response
        if export_format == "json":
            return jsonify(export_report), 200
        else:
            # For PDF, Excel, CSV - return JSON with data for frontend to convert
            # The frontend will handle the actual file generation
            return (
                jsonify(
                    {
                        "message": f"Export data ready for {export_format.upper()} conversion",
                        "format": export_format,
                        "data": export_report,
                    }
                ),
                200,
            )

    except Form.DoesNotExist:
        return jsonify({"error": "Form not found"}), 404
    except Exception as e:
        current_app.logger.error(f"Export Report Error: {str(e)}")
        return jsonify({"error": str(e)}), 400


# --- Cache Invalidation Endpoints ---
# Task: M2-INT-01b - Add cache invalidation rules


@ai_bp.route("/<form_id>/cache/invalidate", methods=["POST"])
@jwt_required()
def invalidate_form_cache(form_id: str) -> Tuple[Any, int]:
    """
    Manual cache invalidation for a specific form.

    Allows selective cache invalidation based on pattern:
    - all: Invalidate all cache for the form
    - nlp_search: Invalidate NLP search cache only
    - summarization: Invalidate summarization cache only
    - by_query: Invalidate cache for a specific query (requires 'query' parameter)

    Payload: {
        "pattern": "all" | "nlp_search" | "summarization" | "by_query",
        "query": "search query text" (required for by_query pattern)
    }

    Response: {
        "form_id": "form-id",
        "pattern": "all",
        "keys_invalidated": 5,
        "invalidated_at": "2026-02-04T10:00:00Z"
    }
    """
    try:
        data = request.get_json() or {}
        pattern = data.get("pattern", "all")
        query = data.get("query")

        current_user = get_current_user()
        form = Form.objects.get(id=form_id)
        if not has_form_permission(current_user, form, "edit"):
            return jsonify({"error": "Unauthorized"}), 403

        total_invalidated = 0

        # Invalidate NLP search cache
        if pattern in ["all", "nlp_search", "by_query"]:
            from services.nlp_service import NLPSearchService

            if pattern == "by_query":
                if not query:
                    return (
                        jsonify(
                            {"error": "Query parameter required for by_query pattern"}
                        ),
                        400,
                    )
                invalidated = NLPSearchService.invalidate_cache(
                    form_id=form_id, pattern="by_query", query=query
                )
            else:
                invalidated = NLPSearchService.invalidate_cache(
                    form_id=form_id, pattern="by_form"
                )
            total_invalidated += invalidated

        # Invalidate summarization cache
        if pattern in ["all", "summarization"]:
            from services.summarization_service import SummarizationService

            invalidated = SummarizationService.invalidate_cache(
                form_id=form_id, pattern="by_form"
            )
            total_invalidated += invalidated

        return (
            jsonify(
                {
                    "form_id": form_id,
                    "pattern": pattern,
                    "keys_invalidated": total_invalidated,
                    "invalidated_at": datetime.now(timezone.utc).isoformat(),
                }
            ),
            200,
        )

    except Form.DoesNotExist:
        return jsonify({"error": "Form not found"}), 404
    except Exception as e:
        current_app.logger.error(f"Cache Invalidation Error: {str(e)}")
        return jsonify({"error": str(e)}), 400


@ai_bp.route("/<form_id>/cache", methods=["DELETE"])
@jwt_required()
def clear_form_cache(form_id: str) -> Tuple[Any, int]:
    """
    Clear all cache for a specific form.

    This endpoint clears all cached data for a form including:
    - NLP search results
    - Semantic search results
    - Summarization results
    - Popular queries
    - Executive summaries

    Response: {
        "form_id": "form-id",
        "keys_invalidated": 10,
        "cleared_at": "2026-02-04T10:00:00Z"
    }
    """
    try:
        current_user = get_current_user()
        form = Form.objects.get(id=form_id)
        if not has_form_permission(current_user, form, "edit"):
            return jsonify({"error": "Unauthorized"}), 403

        from services.nlp_service import NLPSearchService
        from services.summarization_service import SummarizationService

        total_invalidated = 0

        # Clear all NLP search cache for this form
        nlp_invalidated = NLPSearchService.invalidate_cache(
            form_id=form_id, pattern="by_form"
        )
        total_invalidated += nlp_invalidated

        # Clear all summarization cache for this form
        summary_invalidated = SummarizationService.invalidate_cache(
            form_id=form_id, pattern="by_form"
        )
        total_invalidated += summary_invalidated

        return (
            jsonify(
                {
                    "form_id": form_id,
                    "keys_invalidated": total_invalidated,
                    "cleared_at": datetime.now(timezone.utc).isoformat(),
                }
            ),
            200,
        )

    except Form.DoesNotExist:
        return jsonify({"error": "Form not found"}), 404
    except Exception as e:
        current_app.logger.error(f"Clear Cache Error: {str(e)}")
        return jsonify({"error": str(e)}), 400
