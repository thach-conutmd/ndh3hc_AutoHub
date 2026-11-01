"""Setting keys shared by more than one module."""

RECORD_PAGES_KEY = "record_webflow_pages"  # record the page of every WebFlow step (default on)
WEBFLOW_MAX_ATTEMPTS_KEY = "webflow_max_attempts"
WEBFLOW_RETRY_ENABLED_KEY = "webflow_retry_enabled"
DEFAULT_WEBFLOW_MAX_ATTEMPTS = 5
WEBFLOW_ATTEMPTS_LIMIT = 100
LATEST_COUNT_CHOICES = (5, 10, 20, 50, 100, 0)
LATEST_COUNT_KEY = "latest_variant_count"
SHOW_WEBFLOW_LINK_KEY = "show_webflow_link"


def normalize_latest_count(value) -> int:
    """A listed choice, else 0 (All)."""
    try:
        count = int(value)
    except (TypeError, ValueError):
        return 0
    return count if count in LATEST_COUNT_CHOICES else 0
