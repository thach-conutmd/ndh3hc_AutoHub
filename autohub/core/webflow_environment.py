"""WebFlow environments and the one place that turns the saved settings into the WebFlow Base URL (no I/O, no Qt)."""
from __future__ import annotations

from collections.abc import Mapping

ENVIRONMENT_KEY = "webflow_environment"
BASE_URL_KEY = "webflow_base_url"
PRODUCTION = "Production"
ACCEPTANCE = "Acceptance"
DEFAULT_ENVIRONMENT = PRODUCTION
ENVIRONMENT_URLS = {
    PRODUCTION: "https://rb-webflow.bosch.com/app/dashboard",
    ACCEPTANCE: "https://rb-pde-int.bosch.com:8881/app/dashboard",
}


def environment_for_url(url: object) -> str:
    """The environment a (possibly legacy) Base URL belongs to; anything unknown falls back to the default."""
    text = str(url or "").strip().rstrip("/").casefold()
    return next((name for name, value in ENVIRONMENT_URLS.items() if value.casefold() == text), DEFAULT_ENVIRONMENT)


def selected_environment(saved: Mapping) -> str:
    environment = saved.get(ENVIRONMENT_KEY)
    return environment if environment in ENVIRONMENT_URLS else environment_for_url(saved.get(BASE_URL_KEY))


def webflow_base_url(saved: Mapping) -> str:
    """The Base URL of the selected environment; full WebFlow job links are never rebuilt from it."""
    return ENVIRONMENT_URLS[selected_environment(saved)]
