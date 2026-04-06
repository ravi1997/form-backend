"""
utils/password_validator.py
NIST SP 800-63B and OWASP compliant password policy validation.
"""

import re
import string
from typing import Tuple, Optional, List
from dataclasses import dataclass
from enum import Enum

# Common weak passwords that should be rejected
COMMON_PASSWORDS = [
    "password",
    "password123",
    "123456",
    "12345678",
    "qwerty",
    "abc123",
    "letmein",
    "admin",
    "welcome",
    "monkey",
    "sunshine",
    "iloveyou",
    "password1",
    "123456789",
    "football",
    "baseball",
    "trustno1",
    "princess",
    "adobe123",
    "admin123",
    "login123",
    "passw0rd",
    "qwerty123",
    "123qwe",
]


class PasswordStrength(Enum):
    """Password strength levels"""

    VERY_WEAK = 0
    WEAK = 1
    MODERATE = 2
    STRONG = 3
    VERY_STRONG = 4


@dataclass
class PasswordValidationResult:
    """Result of password validation"""

    is_valid: bool
    strength: PasswordStrength
    errors: List[str]
    warnings: List[str]
    score: int


class PasswordValidator:
    """
    NIST SP 800-63B and OWASP compliant password validator.

    Requirements (based on NIST SP 800-63B Digital Identity Guidelines):
    - Minimum 12 characters (NIST recommends at least 8, OWASP recommends 12+)
    - At least 3 of 4 character types: uppercase, lowercase, numbers, special
    - No sequential or repetitive characters
    - No common passwords
    - Not found in breached password databases (simulated)
    """

    # NIST/OWASP recommended minimums
    MIN_LENGTH = 12
    MAX_LENGTH = 128
    MIN_CHARACTER_TYPES = 3

    # Maximum allowed sequential characters (e.g., "abcde" = 5)
    MAX_SEQUENTIAL = 3

    # Maximum allowed repetitive characters (e.g., "aaaaa" = 5)
    MAX_REPETITIVE = 3

    # Regular expressions for patterns
    SEQUENTIAL_PATTERN = re.compile(
        r"(?:012|123|234|345|456|567|678|789|890|901|"
        r"abc|bcd|cde|def|efg|fgh|ghi|hij|ijk|jkl|klm|lmn|mno|nop|opq|pqr|qrs|rst|stu|tuv|uvw|vwx|wxy|xyz)",
        re.IGNORECASE,
    )

    REPETITIVE_PATTERN = re.compile(r"(.)\1{2,}")

    def __init__(self):
        self._common_passwords = set(p.lower() for p in COMMON_PASSWORDS)

    def validate(self, password: str) -> PasswordValidationResult:
        """
        Validate password against NIST/OWASP requirements.

        Args:
            password: The password to validate

        Returns:
            PasswordValidationResult with validation status and details
        """
        errors = []
        warnings = []

        # 1. Length validation
        if len(password) < self.MIN_LENGTH:
            errors.append(
                f"Password must be at least {self.MIN_LENGTH} characters long"
            )
        elif len(password) < 14:
            warnings.append(
                "Password is less than 14 characters; longer passwords are stronger"
            )

        if len(password) > self.MAX_LENGTH:
            errors.append(f"Password must not exceed {self.MAX_LENGTH} characters")

        # 2. Character type variety
        has_upper = any(c.isupper() for c in password)
        has_lower = any(c.islower() for c in password)
        has_digit = any(c.isdigit() for c in password)
        has_special = any(c in string.punctuation for c in password)

        char_types = sum([has_upper, has_lower, has_digit, has_special])

        if char_types < self.MIN_CHARACTER_TYPES:
            errors.append(
                f"Password must contain at least {self.MIN_CHARACTER_TYPES} "
                f"of the following character types: uppercase, lowercase, numbers, special characters"
            )

        # 3. No whitespace
        if any(c.isspace() for c in password):
            errors.append("Password must not contain whitespace characters")

        # 4. Common password check
        password_lower = password.lower()
        if password_lower in self._common_passwords:
            errors.append("Password is too common and easily guessed")

        # 5. Sequential characters check
        sequential_matches = self.SEQUENTIAL_PATTERN.findall(password)
        for match in sequential_matches:
            if len(match) >= self.MAX_SEQUENTIAL:
                errors.append(f"Password contains sequential characters: '{match}'")
                break

        # 6. Repetitive characters check
        repetitive_matches = self.REPETITIVE_PATTERN.findall(password)
        for match in repetitive_matches:
            if len(match) >= self.MAX_REPETITIVE:
                errors.append(f"Password contains repetitive characters: '{match}'")
                break

        # 7. Warnings for weak patterns
        if not has_digit:
            warnings.append("Password does not contain any numbers")

        if not has_special:
            warnings.append("Password does not contain any special characters")

        if password.isnumeric():
            errors.append("Password must not be all numbers")

        if password.isalpha():
            errors.append("Password must not be all letters")

        # Calculate strength and score
        strength, score = self._calculate_strength(
            password, has_upper, has_lower, has_digit, has_special
        )

        # Determine if valid
        is_valid = len(errors) == 0

        return PasswordValidationResult(
            is_valid=is_valid,
            strength=strength,
            errors=errors,
            warnings=warnings,
            score=score,
        )

    def _calculate_strength(
        self,
        password: str,
        has_upper: bool,
        has_lower: bool,
        has_digit: bool,
        has_special: bool,
    ) -> Tuple[PasswordStrength, int]:
        """Calculate password strength and score."""
        score = 0

        # Length score (up to 40 points)
        length_score = min(len(password) * 2, 40)
        score += length_score

        # Character variety score (up to 30 points)
        variety_score = sum([has_upper, has_lower, has_digit, has_special]) * 7.5
        score += variety_score

        # Complexity bonus (up to 20 points)
        if len(password) >= 16 and variety_score >= 30:
            score += 10  # Long and complex
        if char_types := sum([has_upper, has_lower, has_digit, has_special]) >= 4:
            score += 10  # All character types

        # Deductions for weak patterns
        sequential_matches = self.SEQUENTIAL_PATTERN.findall(password)
        repetitive_matches = self.REPETITIVE_PATTERN.findall(password)

        for match in sequential_matches:
            if len(match) >= self.MAX_SEQUENTIAL:
                score -= 10

        for match in repetitive_matches:
            if len(match) >= self.MAX_REPETITIVE:
                score -= 10

        # Common password deduction
        if password.lower() in self._common_passwords:
            score -= 30

        # Ensure score is in valid range
        score = max(0, min(100, score))

        # Determine strength level
        if score < 20:
            strength = PasswordStrength.VERY_WEAK
        elif score < 40:
            strength = PasswordStrength.WEAK
        elif score < 60:
            strength = PasswordStrength.MODERATE
        elif score < 80:
            strength = PasswordStrength.STRONG
        else:
            strength = PasswordStrength.VERY_STRONG

        return strength, score

    def is_password_breached(self, password: str) -> bool:
        """
        Check if password has been found in data breaches.
        In production, this would call HaveIBeenPwned API.
        For now, returns False (placeholder implementation).
        """
        # TODO: Implement HaveIBeenPwned API integration
        # Reference: https://haveibeenpwned.com/API/v3
        return False

    def check_password_history(
        self, password: str, password_history: List[str]
    ) -> bool:
        """
        Check if password has been used before.
        Returns True if password is new (not in history).
        """
        # In production, this should also check for similar passwords
        # (e.g., "Password123" vs "Password456")
        return password not in password_history

    def suggest_strong_password(self, length: int = 16) -> str:
        """
        Generate a strong random password suggestion.
        """
        import secrets
        import string as str_mod

        # Mix of character types
        uppercase = str_mod.ascii_uppercase
        lowercase = str_mod.ascii_lowercase
        digits = str_mod.digits
        special = "!@#$%^&*()-_=+"

        # Ensure at least 4 of each type
        chars = []
        chars.extend(secrets.choice(uppercase) for _ in range(4))
        chars.extend(secrets.choice(lowercase) for _ in range(4))
        chars.extend(secrets.choice(digits) for _ in range(4))
        chars.extend(secrets.choice(special) for _ in range(4))

        # Fill remaining length with random characters from all sets
        all_chars = uppercase + lowercase + digits + special
        for _ in range(length - len(chars)):
            chars.append(secrets.choice(all_chars))

        # Shuffle the characters
        secrets.SystemRandom().shuffle(chars)

        return "".join(chars)


# Singleton instance
password_validator = PasswordValidator()
