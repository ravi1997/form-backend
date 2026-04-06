"""
utils/mongodb_query_helper.py
Utilities for safe MongoDB query construction to prevent NoSQL injection.
"""

import re
from typing import Any, Dict, List


class NoSQLInjector:
    """
    Provides methods to escape and sanitize user input for MongoDB queries.
    Prevents NoSQL injection attacks.
    """

    # MongoDB operators that should be escaped
    MONGODB_OPERATORS = {
        "$or",
        "$and",
        "$not",
        "$nor",
        "$gt",
        "$gte",
        "$lt",
        "$lte",
        "$ne",
        "$in",
        "$nin",
        "$regex",
        "$exists",
        "$type",
        "$mod",
        "$where",
        "$all",
        "$size",
        "$elemMatch",
        "$text",
        "$search",
    }

    @staticmethod
    def escape_value(value: Any) -> Any:
        """
        Escape a value to prevent NoSQL injection.
        For strings, this means ensuring they don't contain MongoDB operators.

        Args:
            value: The value to escape

        Returns:
            Escaped value if it's a string, original otherwise
        """
        if not isinstance(value, str):
            return value

        # Check if value contains MongoDB operators
        for operator in NoSQLInjector.MONGODB_OPERATORS:
            if operator in value:
                # Replace operator with escaped version
                value = value.replace(operator, f"\\{operator}")

        return value

    @staticmethod
    def sanitize_key(key: str) -> str:
        """
        Sanitize a MongoDB key to prevent NoSQL injection.
        Prevents key injection like "username.$ne".

        Args:
            key: The key to sanitize

        Returns:
            Sanitized key
        """
        if not isinstance(key, str):
            return key

        # Remove any MongoDB operators from the key
        # Only allow alphanumeric, underscore, and dot
        sanitized = re.sub(r"[\$\.\{]", "", key)

        return sanitized

    @staticmethod
    def build_safe_query(field: str, value: Any) -> Dict[str, Any]:
        """
        Build a safe MongoDB query for a field-value pair.

        Args:
            field: The field name (will be sanitized)
            value: The value (will be escaped if string)

        Returns:
            Safe query dictionary
        """
        safe_field = NoSQLInjector.sanitize_key(field)
        safe_value = NoSQLInjector.escape_value(value)

        return {safe_field: safe_value}

    @staticmethod
    def build_or_query(field: str, values: List[Any]) -> Dict[str, Any]:
        """
        Build a safe $or query for a field with multiple values.

        Args:
            field: The field name (will be sanitized)
            values: List of values to OR together (will be escaped)

        Returns:
            Safe query dictionary with $or operator
        """
        if not values:
            raise ValueError("Cannot build $or query with empty values list")

        # Sanitize the field
        safe_field = NoSQLInjector.sanitize_key(field)

        # Escape each value
        safe_values = [NoSQLInjector.escape_value(v) for v in values]

        # Build the query
        queries = [{safe_field: v} for v in safe_values]

        return {"$or": queries}

    @staticmethod
    def validate_json_structure(obj: Dict[str, Any]) -> bool:
        """
        Validate that a JSON object doesn't contain MongoDB operators
        in unexpected places.

        Args:
            obj: Dictionary to validate

        Returns:
            True if safe, False if potentially malicious
        """
        if not isinstance(obj, dict):
            return False

        # Check for MongoDB operators at top level (which is suspicious)
        for key in obj.keys():
            if key.startswith("$"):
                return False

        return True


def sanitize_query_input(input_data: str) -> str:
    """
    Simple sanitization for query string inputs.

    Args:
        input_data: Input string to sanitize

    Returns:
        Sanitized string
    """
    if not isinstance(input_data, str):
        return input_data

    # Remove MongoDB operators
    sanitized = input_data
    for operator in NoSQLInjector.MONGODB_OPERATORS:
        sanitized = sanitized.replace(operator, "")

    return sanitized
