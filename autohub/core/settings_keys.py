"""Setting keys shared by more than one module."""

RECORD_PAGES_KEY = "record_webflow_pages"  # record the page of every WebFlow step (default on)
WEBFLOW_MAX_ATTEMPTS_KEY = "webflow_max_attempts"
WEBFLOW_RETRY_ENABLED_KEY = "webflow_retry_enabled"
DEFAULT_WEBFLOW_MAX_ATTEMPTS = 5
WEBFLOW_ATTEMPTS_LIMIT = 100
LATEST_COUNT_CHOICES = (5, 10, 20, 50, 100, 0)
LATEST_COUNT_KEY = "latest_variant_count"
SHOW_WEBFLOW_LINK_KEY = "show_webflow_link"
A2L_COMP_ID_SYMBOL_KEY = "a2l_comp_id_symbol"
WEBFLOW_GENERAL_OPTIONS_KEY = "webflow_general_options"
CALIBRATION_FOLDER_PATH_KEY = "calibration_folder_path"
NEW_VARIANT_DEFAULTS_KEY = "new_variant_defaults"
SHOW_FORM_B_ADVANCED_FIELDS_KEY = "show_form_b_advanced_fields"
XML_COMPARISON_EXCLUSIONS_KEY = "xml_comparison_exclusions"
XML_COMPARISON_DISABLED_EXCLUSIONS_KEY = "xml_comparison_disabled_exclusions"
XML_COMPARISON_EXCLUSIONS_MASTER_ONLY_KEY = "xml_comparison_exclusions_master_only"
DEFAULT_XML_COMPARISON_EXCLUSIONS = ("Files/", "Notes/")


def normalize_latest_count(value) -> int:
    """A listed choice, else 0 (All)."""
    try:
        count = int(value)
    except (TypeError, ValueError):
        return 0
    return count if count in LATEST_COUNT_CHOICES else 0
