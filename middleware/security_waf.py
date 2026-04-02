import re
import logging
from flask import request, abort, g
from logger.unified_logger import error_logger, audit_logger

# --- Security Patterns (OWASP Top 10 Protections) ---

# SQL Injection patterns
SQLI_PATTERNS = [
    # More specific SQLi patterns instead of just blocking any single quote
    re.compile(r"(\%27)|(\-\-)|(\%23)|(#)", re.IGNORECASE),
    re.compile(r"((\%3D)|(=))[^\n]*((%27)|(\')|(\-\-)|(%3B)|(;))", re.IGNORECASE),
    re.compile(r"\w*((\%27)|(\'))((\%6F)|o|(\%4F))((\%72)|r|(\%52))", re.IGNORECASE), # ' or ' pattern
    re.compile(r"((\%27)|(\'))\s*union", re.IGNORECASE),
    re.compile(r"exec(\s|\+)+(s|x)p\w+", re.IGNORECASE),
    re.compile(r"SELECT\s+.*\s+FROM", re.IGNORECASE),
    re.compile(r"INSERT\s+INTO", re.IGNORECASE),
    re.compile(r"DROP\s+TABLE", re.IGNORECASE),
]

# Cross-Site Scripting (XSS) patterns
XSS_PATTERNS = [
    re.compile(r"((\%3C)|<)((\%2F)|\/)*[a-z0-9\%]+((\%3E)|>)", re.IGNORECASE),
    re.compile(r"((\%3C)|<)((\%69)|i|(\%49))((\%6D)|m|(\%4D))((\%67)|g|(\%47))[^\n]+((\%3E)|>)", re.IGNORECASE),
    re.compile(r"((\%3C)|<)[^\n]+((\%3E)|>)", re.IGNORECASE),
    re.compile(r"javascript:", re.IGNORECASE),
    re.compile(r"onerror=", re.IGNORECASE),
    re.compile(r"onload=", re.IGNORECASE),
    re.compile(r"alert\(", re.IGNORECASE),
]

# Path Traversal patterns
PATH_TRAVERSAL_PATTERNS = [
    re.compile(r"\.\.\/", re.IGNORECASE),
    re.compile(r"\/etc\/passwd", re.IGNORECASE),
    re.compile(r"\/etc\/shadow", re.IGNORECASE),
    re.compile(r"C:\\", re.IGNORECASE),
]

# Command Injection patterns
CMD_INJECTION_PATTERNS = [
    re.compile(r"[;\|&><]", re.IGNORECASE),
    re.compile(r"\$\(.*\)", re.IGNORECASE),
    re.compile(r"`.*`", re.IGNORECASE),
]

class SecurityWAF:
    """
    Web Application Firewall (WAF) Middleware for Flask.
    Protects against common OWASP Top 10 attacks.
    """

    def __init__(self, app=None):
        if app is not None:
            self.init_app(app)

    def init_app(self, app):
        @app.before_request
        def waf_check():
            # Skip for OPTIONS requests (CORS preflight)
            if request.method == "OPTIONS":
                return

            # Skip for static assets or specific routes if needed
            if any(request.path.startswith(p) for p in ["/static", "/flasgger_static", "/form/static", "/form/flasgger_static", "/form/docs"]):
                return

            request_id = getattr(g, "request_id", "unknown")
            client_ip = request.remote_addr
            
            # Check all parts of the request
            self._check_value(request.path, "Path", client_ip, request_id)
            
            for key, value in request.args.items():
                self._check_value(f"{key}={value}", "Query Params", client_ip, request_id)
            
            for key, value in request.headers.items():
                # Skip some headers that might contain legitimate special characters or quality values
                if key.lower() in [
                    "user-agent", "referer", "cookie", "accept", 
                    "accept-language", "accept-encoding", "content-type", 
                    "authorization", "if-none-match", "cache-control",
                    "x-csrf-token-access", "x-csrf-token-refresh", "x-organization-id"
                ]:
                    continue
                # Check key and value separately to avoid false positives on `=...;` regex
                self._check_value(key, "Header Key", client_ip, request_id)
                self._check_value(value, "Header Value", client_ip, request_id)

            # Check JSON body if applicable
            if request.is_json:
                try:
                    body_str = request.get_data(as_text=True)
                    if body_str:
                        self._check_value(body_str, "JSON Body", client_ip, request_id)
                except Exception:
                    pass

    def _check_value(self, value, source, client_ip, request_id):
        if not value or not isinstance(value, str):
            return

        # 1. SQL Injection Check
        for pattern in SQLI_PATTERNS:
            if pattern.search(value):
                self._block_request("SQL Injection", source, value, client_ip, request_id)

        # 2. XSS Check
        for pattern in XSS_PATTERNS:
            if pattern.search(value):
                self._block_request("Cross-Site Scripting (XSS)", source, value, client_ip, request_id)

        # 3. Path Traversal Check
        for pattern in PATH_TRAVERSAL_PATTERNS:
            if pattern.search(value):
                self._block_request("Path Traversal", source, value, client_ip, request_id)

        # 4. Command Injection Check
        for pattern in CMD_INJECTION_PATTERNS:
            if pattern.search(value):
                # Specific check for semicolon as it's common in some legitimate fields
                # but dangerous in shell commands
                if ";" in value and source.startswith("Header"):
                    continue
                self._block_request("Command Injection", source, value, client_ip, request_id)

    def _block_request(self, attack_type, source, value, client_ip, request_id):
        error_msg = f"SECURITY ALERT: Blocked {attack_type} attempt from IP {client_ip} in {source}. Value: '{value}'"
        error_logger.error(f"[ReqID: {request_id}] {error_msg}")
        audit_logger.warning(f"[ReqID: {request_id}] {error_msg}")
        
        # Abort the request with 403 Forbidden
        abort(403, description="Access blocked by security policy.")

waf = SecurityWAF()
