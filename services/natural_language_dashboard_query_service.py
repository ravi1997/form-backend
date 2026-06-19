"""
services/natural_language_dashboard_query_service.py
Service for converting natural language queries to dashboard filters.
"""

from typing import Dict, List, Optional, Any
from datetime import datetime
import json
import re

from logger.unified_logger import app_logger, error_logger
from services.llm_service import LLMService
from services.llm_prompt_template_service import LLMPromptTemplateService
from services.llm_usage_tracking_service import LLMUsageTrackingService
from utils.exceptions import ValidationError, NotFoundError


class NaturalLanguageDashboardQueryService:
    """Service for converting natural language queries to dashboard filters."""

    def __init__(self):
        self.llm_service = LLMService()
        self.template_service = LLMPromptTemplateService()
        self.usage_tracker = LLMUsageTrackingService()

    async def convert_query_to_filters(
        self,
        natural_language_query: str,
        dashboard_context: Dict[str, Any],
        user_id: str,
        organization_id: str,
        provider: str = "openai"
    ) -> Dict[str, Any]:
        """Convert natural language query to structured dashboard filters."""
        try:
            app_logger.info(f"Converting natural language query: {natural_language_query[:50]}...")
            
            # Get dashboard query template
            template = await self.template_service.get_template("dashboard_query")
            
            if not template:
                # Use fallback conversion
                return await self._fallback_query_conversion(
                    natural_language_query, dashboard_context
                )
            
            # Prepare context
            context = {
                "dashboard_context": json.dumps(dashboard_context, indent=2),
                "available_fields": self._extract_available_fields(dashboard_context),
                "query": natural_language_query
            }
            
            # Generate completion
            result = await self.llm_service.generate_completion(
                prompt=natural_language_query,
                provider=self.llm_service.LLMProvider(provider),
                template_id=template["id"],
                template_vars=context,
                user_id=user_id,
                organization_id=organization_id
            )
            
            # Parse filters from response
            try:
                filters = json.loads(result["content"])
                
                # Validate and sanitize filters
                validated_filters = self._validate_filters(
                    filters, dashboard_context
                )
                
                return {
                    "query": natural_language_query,
                    "filters": validated_filters,
                    "provider": provider,
                    "model": result.get("model", ""),
                    "usage": result.get("usage", {}),
                    "cost": result.get("cost", 0.0),
                    "confidence": self._calculate_confidence(result["content"])
                }
                
            except json.JSONDecodeError:
                # Try to extract filters using regex
                extracted_filters = self._extract_filters_from_text(result["content"])
                
                return {
                    "query": natural_language_query,
                    "filters": extracted_filters,
                    "provider": provider,
                    "model": result.get("model", ""),
                    "usage": result.get("usage", {}),
                    "cost": result.get("cost", 0.0),
                    "confidence": 0.5,  # Lower confidence for regex extraction
                    "parse_error": "Failed to parse JSON, used fallback extraction"
                }
            
        except Exception as e:
            error_logger.error(f"Failed to convert query to filters: {str(e)}", exc_info=True)
            raise

    async def get_query_suggestions(
        self,
        dashboard_context: Dict[str, Any],
        user_id: str,
        organization_id: str,
        limit: int = 10
    ) -> List[Dict[str, Any]]:
        """Get suggested queries for a dashboard."""
        try:
            app_logger.info("Generating query suggestions for dashboard")
            
            # Extract key information from dashboard context
            fields = self._extract_available_fields(dashboard_context)
            widgets = dashboard_context.get("widgets", [])
            
            # Generate suggestions based on dashboard content
            suggestions = []
            
            # Time-based suggestions
            if any("date" in field.lower() or "time" in field.lower() for field in fields):
                suggestions.extend([
                    {
                        "query": "Show me data from the last 7 days",
                        "category": "time",
                        "description": "Filter to recent time period"
                    },
                    {
                        "query": "Compare this month to last month",
                        "category": "time",
                        "description": "Month-over-month comparison"
                    }
                ])
            
            # Numeric field suggestions
            numeric_fields = [f for f in fields if self._is_numeric_field(f, dashboard_context)]
            if numeric_fields:
                suggestions.extend([
                    {
                        "query": f"Show top 10 {numeric_fields[0]} values",
                        "category": "ranking",
                        "description": "Top values by numeric field"
                    },
                    {
                        "query": f"Where {numeric_fields[0]} is greater than average",
                        "category": "filter",
                        "description": "Filter by above-average values"
                    }
                ])
            
            # Category field suggestions
            category_fields = [f for f in fields if self._is_category_field(f, dashboard_context)]
            if category_fields:
                suggestions.extend([
                    {
                        "query": f"Group by {category_fields[0]}",
                        "category": "grouping",
                        "description": "Group data by category"
                    },
                    {
                        "query": f"Show {category_fields[0]} breakdown",
                        "category": "breakdown",
                        "description": "Category breakdown analysis"
                    }
                ])
            
            # Performance suggestions
            suggestions.extend([
                {
                    "query": "Show me the best performing items",
                    "category": "performance",
                    "description": "Top performers analysis"
                },
                {
                    "query": "What are the trends over time?",
                    "category": "trends",
                    "description": "Time trend analysis"
                }
            ])
            
            # Limit suggestions
            suggestions = suggestions[:limit]
            
            return suggestions
            
        except Exception as e:
            error_logger.error(f"Failed to get query suggestions: {str(e)}", exc_info=True)
            return []

    async def explain_filters(
        self,
        filters: List[Dict[str, Any]],
        dashboard_context: Dict[str, Any],
        user_id: str,
        organization_id: str
    ) -> Dict[str, Any]:
        """Generate natural language explanation of applied filters."""
        try:
            app_logger.info("Generating filter explanation")
            
            # Create explanation prompt
            filters_json = json.dumps(filters, indent=2)
            context_json = json.dumps(dashboard_context, indent=2)
            
            prompt = f"""
            Explain the following dashboard filters in plain, natural language:
            
            Filters: {filters_json}
            
            Dashboard Context: {context_json}
            
            Provide a clear, concise explanation of what these filters do and what data they show.
            Format your response as a JSON object with "explanation" and "impact" fields.
            """
            
            # Generate completion
            result = await self.llm_service.generate_completion(
                prompt=prompt,
                user_id=user_id,
                organization_id=organization_id
            )
            
            try:
                explanation_data = json.loads(result["content"])
                
                return {
                    "filters": filters,
                    "explanation": explanation_data.get("explanation", ""),
                    "impact": explanation_data.get("impact", ""),
                    "provider": result.get("provider", ""),
                    "model": result.get("model", ""),
                    "usage": result.get("usage", {}),
                    "cost": result.get("cost", 0.0)
                }
                
            except json.JSONDecodeError:
                return {
                    "filters": filters,
                    "explanation": result["content"],
                    "impact": "",
                    "provider": result.get("provider", ""),
                    "model": result.get("model", ""),
                    "usage": result.get("usage", {}),
                    "cost": result.get("cost", 0.0),
                    "parse_error": "Failed to parse structured explanation"
                }
            
        except Exception as e:
            error_logger.error(f"Failed to explain filters: {str(e)}", exc_info=True)
            raise

    async def optimize_filters(
        self,
        filters: List[Dict[str, Any]],
        dashboard_context: Dict[str, Any],
        user_id: str,
        organization_id: str
    ) -> Dict[str, Any]:
        """Optimize filters for better performance and relevance."""
        try:
            app_logger.info("Optimizing dashboard filters")
            
            # Create optimization prompt
            filters_json = json.dumps(filters, indent=2)
            context_json = json.dumps(dashboard_context, indent=2)
            
            prompt = f"""
            Analyze and optimize the following dashboard filters for better performance and relevance:
            
            Current Filters: {filters_json}
            
            Dashboard Context: {context_json}
            
            Suggest optimizations to:
            1. Improve query performance
            2. Increase data relevance
            3. Remove redundant filters
            4. Add missing important filters
            
            Return your response as a JSON object with:
            - "optimized_filters": array of optimized filters
            - "optimizations": array of optimization descriptions
            - "performance_impact": description of performance impact
            """
            
            # Generate completion
            result = await self.llm_service.generate_completion(
                prompt=prompt,
                user_id=user_id,
                organization_id=organization_id
            )
            
            try:
                optimization_data = json.loads(result["content"])
                
                return {
                    "original_filters": filters,
                    "optimized_filters": optimization_data.get("optimized_filters", filters),
                    "optimizations": optimization_data.get("optimizations", []),
                    "performance_impact": optimization_data.get("performance_impact", ""),
                    "provider": result.get("provider", ""),
                    "model": result.get("model", ""),
                    "usage": result.get("usage", {}),
                    "cost": result.get("cost", 0.0)
                }
                
            except json.JSONDecodeError:
                return {
                    "original_filters": filters,
                    "optimized_filters": filters,
                    "optimizations": [],
                    "performance_impact": "No optimizations applied",
                    "provider": result.get("provider", ""),
                    "model": result.get("model", ""),
                    "usage": result.get("usage", {}),
                    "cost": result.get("cost", 0.0),
                    "parse_error": "Failed to parse optimization results"
                }
            
        except Exception as e:
            error_logger.error(f"Failed to optimize filters: {str(e)}", exc_info=True)
            raise

    async def _fallback_query_conversion(
        self,
        query: str,
        dashboard_context: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Fallback method for converting queries without LLM."""
        try:
            # Simple rule-based conversion
            filters = []
            query_lower = query.lower()
            
            # Time-based filters
            if "last" in query_lower and "day" in query_lower:
                days_match = re.search(r'last (\d+) days?', query_lower)
                if days_match:
                    days = int(days_match.group(1))
                    filters.append({
                        "field": "date",
                        "operator": "greater_than_or_equal",
                        "value": f"-{days}d"
                    })
            
            # Numeric comparisons
            if "greater than" in query_lower or "more than" in query_lower:
                # Extract numeric value and field
                number_match = re.search(r'(\d+(?:\.\d+)?)', query_lower)
                if number_match:
                    value = float(number_match.group(1))
                    # Try to find field name
                    fields = self._extract_available_fields(dashboard_context)
                    field = self._find_field_in_query(query_lower, fields)
                    
                    if field:
                        filters.append({
                            "field": field,
                            "operator": "greater_than",
                            "value": value
                        })
            
            # Top N queries
            if "top" in query_lower:
                top_match = re.search(r'top (\d+)', query_lower)
                if top_match:
                    limit = int(top_match.group(1))
                    filters.append({
                        "type": "limit",
                        "value": limit
                    })
            
            return {
                "query": query,
                "filters": filters,
                "provider": "rule_based",
                "model": "fallback",
                "usage": {},
                "cost": 0.0,
                "confidence": 0.3
            }
            
        except Exception as e:
            error_logger.error(f"Failed fallback query conversion: {str(e)}", exc_info=True)
            return {
                "query": query,
                "filters": [],
                "provider": "rule_based",
                "model": "fallback",
                "usage": {},
                "cost": 0.0,
                "confidence": 0.1
            }

    def _extract_available_fields(self, dashboard_context: Dict[str, Any]) -> List[str]:
        """Extract available fields from dashboard context."""
        fields = set()
        
        # Extract from widgets
        widgets = dashboard_context.get("widgets", [])
        for widget in widgets:
            # Extract from data bindings
            bindings = widget.get("data_bindings", [])
            for binding in bindings:
                if "field" in binding:
                    fields.add(binding["field"])
            
            # Extract from filters
            widget_filters = widget.get("filters", [])
            for filter_config in widget_filters:
                if "field" in filter_config:
                    fields.add(filter_config["field"])
        
        # Extract from data sources
        data_sources = dashboard_context.get("data_sources", [])
        for source in data_sources:
            source_fields = source.get("fields", [])
            fields.update(source_fields)
        
        return sorted(list(fields))

    def _validate_filters(
        self,
        filters: List[Dict[str, Any]],
        dashboard_context: Dict[str, Any]
    ) -> List[Dict[str, Any]]:
        """Validate and sanitize filters against dashboard context."""
        validated_filters = []
        available_fields = self._extract_available_fields(dashboard_context)
        
        for filter_config in filters:
            # Check if field exists
            if "field" in filter_config:
                field = filter_config["field"]
                if field not in available_fields:
                    # Skip invalid field filters
                    continue
            
            # Validate operator
            valid_operators = [
                "equals", "not_equals", "contains", "not_contains",
                "greater_than", "less_than", "greater_than_or_equal",
                "less_than_or_equal", "in", "not_in", "between"
            ]
            
            if "operator" in filter_config:
                operator = filter_config["operator"]
                if operator not in valid_operators:
                    filter_config["operator"] = "equals"  # Default operator
            
            # Sanitize value
            if "value" in filter_config:
                value = filter_config["value"]
                if isinstance(value, str):
                    # Basic sanitization
                    filter_config["value"] = value.strip()
            
            validated_filters.append(filter_config)
        
        return validated_filters

    def _extract_filters_from_text(self, text: str) -> List[Dict[str, Any]]:
        """Extract filters from text using regex patterns."""
        filters = []
        
        # Extract field: operator: value patterns
        pattern = r'(\w+)\s*:\s*(equals|contains|greater_than|less_than)\s*:\s*([^,\n]+)'
        matches = re.findall(pattern, text, re.IGNORECASE)
        
        for field, operator, value in matches:
            filters.append({
                "field": field.strip(),
                "operator": operator.strip().lower(),
                "value": value.strip()
            })
        
        # Extract "field > value" patterns
        pattern = r'(\w+)\s*>\s*([^,\n\s]+)'
        matches = re.findall(pattern, text)
        
        for field, value in matches:
            filters.append({
                "field": field.strip(),
                "operator": "greater_than",
                "value": value.strip()
            })
        
        # Extract "field < value" patterns
        pattern = r'(\w+)\s*<\s*([^,\n\s]+)'
        matches = re.findall(pattern, text)
        
        for field, value in matches:
            filters.append({
                "field": field.strip(),
                "operator": "less_than",
                "value": value.strip()
            })
        
        return filters

    def _calculate_confidence(self, response_text: str) -> float:
        """Calculate confidence score for the conversion."""
        # Simple heuristic-based confidence calculation
        confidence = 0.5  # Base confidence
        
        # Check for structured output
        if response_text.strip().startswith('{') and response_text.strip().endswith('}'):
            confidence += 0.3
        
        # Check for filter keywords
        filter_keywords = ["filter", "where", "field", "operator", "value"]
        keyword_count = sum(1 for keyword in filter_keywords if keyword in response_text.lower())
        confidence += min(keyword_count * 0.05, 0.2)
        
        return min(confidence, 1.0)

    def _is_numeric_field(self, field: str, dashboard_context: Dict[str, Any]) -> bool:
        """Check if a field is numeric based on dashboard context."""
        # This is a simplified check - in production, you'd have field type information
        numeric_indicators = ["amount", "price", "cost", "value", "number", "count", "quantity"]
        
        return any(indicator in field.lower() for indicator in numeric_indicators)

    def _is_category_field(self, field: str, dashboard_context: Dict[str, Any]) -> bool:
        """Check if a field is a category field."""
        # This is a simplified check - in production, you'd have field type information
        category_indicators = ["category", "type", "status", "group", "class", "name"]
        
        return any(indicator in field.lower() for indicator in category_indicators)

    def _find_field_in_query(self, query: str, fields: List[str]) -> str:
        """Find the most relevant field mentioned in the query."""
        query_lower = query.lower()
        
        for field in fields:
            if field.lower() in query_lower:
                return field
        
        # Return first field if no match found
        return fields[0] if fields else ""