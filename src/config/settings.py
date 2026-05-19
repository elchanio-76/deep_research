import os

# Export config
EXPORT_DIR = os.getenv("EXPORT_DIR", "./exports")
EXPORT_BASE_URL = os.getenv("EXPORT_BASE_URL", "/exports")

QUALITY_AGENT_MAX_SEARCHES = 3
DEFAULT_NUM_SEARCHES = 5
FACT_CHECK_CONFIDENCE_THRESHOLD = 70
GROUP_VERIFY_MAX_CLAIMS = 3
GROUP_VERIFY_CONTEXT_LIMIT = 500
GROUP_VERIFY_CLAIM_SNIPPET_LEN = 200

PLANNER_MODEL = "gpt-5"
QUALITY_MODEL = "gpt-5"
FACT_CHECK_PLANNER_MODEL = "gpt-5"
ADAPTIVE_SEARCH_MODEL = "gpt-5-mini"
SEARCH_MODEL = "gpt-4o-mini"
WRITER_MODEL = "gpt-5-mini"
QA_MODEL = "gpt-5-mini"
CLAIM_EXTRACTOR_MODEL = "gpt-5-mini"

EDITOR_MODEL = "gpt-5-mini"
EMAIL_MODEL = "gpt-4o-mini"
SESSION_TITLE_MODEL = "gpt-5-mini"
VERIFICATION_TOOL_MODEL = "gpt-4o-mini"

# E-mail config
RECIPIENT = os.getenv("EMAIL_RECIPIENT", "")
SENDER = os.getenv("EMAIL_SENDER", "")
EMAIL_ENABLED = os.getenv("EMAIL_ENABLED", "false").lower() == "true"
DEFAULT_AWS_REGION = "eu-north-1"

# Database config
DEFAULT_DB_POOL_MIN = 1
DEFAULT_DB_POOL_MAX = 5

# Search mode config
SEARCH_MODE_DEFAULT = "no_adaptive"
SEARCH_MODE_OPTIONS = [
    "no_adaptive",
    "deep_dive",
    "deep_dive_gap_fill",
]

AGENT_MODEL_MAP = {
    "planner_agent": PLANNER_MODEL,
    "search_agent": SEARCH_MODEL,
    "brave_search_agent": SEARCH_MODEL,
    "writer_agent": WRITER_MODEL,
    "qa_agent": QA_MODEL,
    "quality_agent": QUALITY_MODEL,
    "claim_extractor": CLAIM_EXTRACTOR_MODEL,
    "fact_check_planner": FACT_CHECK_PLANNER_MODEL,
    "editor_agent": EDITOR_MODEL,
    "email_agent": EMAIL_MODEL,
    "session_title_agent": SESSION_TITLE_MODEL,
    "adaptive_search_planner": ADAPTIVE_SEARCH_MODEL,
    "quick_verifier_agent": VERIFICATION_TOOL_MODEL,
    "thorough_verifier_agent": VERIFICATION_TOOL_MODEL,
    "red_team_challenger_agent": VERIFICATION_TOOL_MODEL,
    "group_verifier_agent": VERIFICATION_TOOL_MODEL,
}

MODEL_COSTS = {
    # Costs per 1M tokens, no caching
    "gpt-5": {"input": 1.25, "output": 10.0},
    "gpt-5-mini": {"input": 0.25, "output": 2.0},
    "gpt-4o-mini": {"input": 0.15, "output": 0.6},
}

# Brave Search config
BRAVE_RATE_LIMIT_SECONDS = 1.0
BRAVE_SEARCH_COST = 0.0

TOOL_COSTS = {
    # Per tool call
    "web_search": 0.0112,  # For use with gpt-4o-mini
    "brave_search": BRAVE_SEARCH_COST,
}
