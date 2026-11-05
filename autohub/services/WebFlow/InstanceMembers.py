import logging

from selenium.common.exceptions import ElementClickInterceptedException, StaleElementReferenceException, TimeoutException
from selenium.webdriver.common.action_chains import ActionChains
from selenium.webdriver.common.by import By
from selenium.webdriver.remote.webdriver import WebDriver
from selenium.webdriver.support.ui import WebDriverWait

from . import Constants as Constants
from .Information import Information
from .components import button_is_enabled, scroll_into_view_if_hidden, wait_until_idle

_logger = logging.getLogger(__name__)


def _matches_user(title: str, name: str) -> bool:
    """Titles read "Name (Dept)"; the configured name may or may not include the department."""
    title = title.strip()
    name = name.strip()
    return title == name or title.startswith(f"{name} (")


class InstanceMembers:
    """Adds one user to every Job Instance Members role except the skipped ones."""

    def __init__(self, driver: WebDriver):
        self.driver = driver
        self._information = Information(driver)

    def add_user(self, name: str) -> bool:
        if not wait_until_idle(self.driver, Constants.WEBFLOW_TIMEOUT):
            raise RuntimeError("WebFlow is still busy before Instance Members")
        self._information.expand_job_information()
        self._open_dialog()
        try:
            self._wait_for_data()
            self._filter(name)
            for role in self._target_roles():
                self._add_to_role(name, role)
        except Exception:
            self._dismiss_dialog()
            raise
        self._confirm_dialog()
        return True

    def _open_dialog(self) -> None:
        button = WebDriverWait(self.driver, Constants.BODY_TIMEOUT).until(
            lambda driver: next(
                (b for b in driver.find_elements(By.XPATH, Constants.INSTANCE_MEMBERS_BUTTON_XPATH) if b.is_displayed()),
                None,
            )
        )
        scroll_into_view_if_hidden(self.driver, button)
        if not button_is_enabled(button):
            raise RuntimeError("Instance Members button is disabled")
        button.click()
        WebDriverWait(self.driver, Constants.INSTANCE_MEMBERS_TIMEOUT).until(
            lambda driver: any(d.is_displayed() for d in driver.find_elements(By.CSS_SELECTOR, Constants.INSTANCE_MEMBERS_DIALOG_CSS))
        )

    def _wait_for_data(self) -> None:
        """Wait until the roles and the user list are rendered and the page is idle again."""
        WebDriverWait(self.driver, Constants.INSTANCE_MEMBERS_TIMEOUT).until(
            lambda driver: len(driver.find_elements(By.CSS_SELECTOR, Constants.INSTANCE_MEMBERS_ROLE_CSS)) > 0
            and len(driver.find_elements(By.CSS_SELECTOR, Constants.INSTANCE_MEMBERS_ROW_CSS)) > 0
        )
        if not wait_until_idle(self.driver, Constants.INSTANCE_MEMBERS_TIMEOUT):
            raise RuntimeError("Instance Members did not finish loading")

    def _filter(self, name: str) -> None:
        box = self.driver.find_element(By.CSS_SELECTOR, Constants.INSTANCE_MEMBERS_FILTER_CSS)
        box.clear()
        box.send_keys(name)
        WebDriverWait(self.driver, Constants.INSTANCE_MEMBERS_TIMEOUT).until(
            lambda driver: any(
                _matches_user(row.get_attribute("title") or "", name)
                for row in driver.find_elements(By.CSS_SELECTOR, Constants.INSTANCE_MEMBERS_ROW_CSS)
            )
        )

    def _find_user_row(self, name: str):
        for row in self.driver.find_elements(By.CSS_SELECTOR, Constants.INSTANCE_MEMBERS_ROW_CSS):
            if _matches_user(row.get_attribute("title") or "", name):
                return row
        raise RuntimeError(f"Change Engineer {name!r} was not found in Instance Members")

    def _roles(self) -> list[str]:
        return [
            role.get_attribute("title") or ""
            for role in self.driver.find_elements(By.CSS_SELECTOR, Constants.INSTANCE_MEMBERS_ROLE_CSS)
        ]

    def _target_roles(self) -> list[str]:
        roles = [role for role in self._roles() if role and role not in Constants.INSTANCE_MEMBERS_SKIPPED_ROLES]
        if not roles:
            raise RuntimeError("No Instance Members roles to add the user to")
        return roles

    def _role_element(self, role: str):
        for element in self.driver.find_elements(By.CSS_SELECTOR, Constants.INSTANCE_MEMBERS_ROLE_CSS):
            if element.get_attribute("title") == role:
                return element
        raise RuntimeError(f"Instance Members role {role!r} was not found")

    def _role_members(self, role: str) -> list[str]:
        """Expand the role if its members are not in the DOM yet, then return their titles."""
        element = self._role_element(role)
        item = element.find_element(By.XPATH, "./parent::li")
        if not item.find_elements(By.CSS_SELECTOR, "div.tree-children"):
            element.find_element(By.CSS_SELECTOR, "span.ui-tree-toggler").click()
            wait_until_idle(self.driver, Constants.INSTANCE_MEMBERS_TIMEOUT)
        return [
            member.get_attribute("title") or ""
            for member in item.find_elements(By.CSS_SELECTOR, Constants.INSTANCE_MEMBERS_ROLE_CHILDREN_CSS)
        ]

    def _add_to_role(self, name: str, role: str) -> None:
        if any(_matches_user(member, name) for member in self._role_members(role)):
            _logger.info("Change Engineer already in Instance Members role %s", role)
            return
        row = self._find_user_row(name)
        target = self._role_element(role)
        scroll_into_view_if_hidden(self.driver, target)
        try:
            ActionChains(self.driver).drag_and_drop(row, target).perform()
        except (ElementClickInterceptedException, StaleElementReferenceException) as error:
            raise RuntimeError(f"Could not drag {name!r} onto Instance Members role {role!r}") from error
        wait_until_idle(self.driver, Constants.INSTANCE_MEMBERS_TIMEOUT)
        if not any(_matches_user(member, name) for member in self._role_members(role)):
            raise RuntimeError(f"Change Engineer {name!r} was not added to Instance Members role {role!r}")
        _logger.info("Added Change Engineer to Instance Members role %s", role)

    def _confirm_dialog(self) -> None:
        buttons = self.driver.find_elements(By.XPATH, Constants.INSTANCE_MEMBERS_OK_XPATH)
        if not buttons:
            raise RuntimeError("Instance Members OK button was not found")
        buttons[0].click()
        self._wait_until_dialog_closed()

    def _dismiss_dialog(self) -> None:
        """Best effort after a failure: close the dialog without masking the original error."""
        try:
            buttons = self.driver.find_elements(By.XPATH, Constants.INSTANCE_MEMBERS_OK_XPATH)
            if buttons:
                buttons[0].click()
                self._wait_until_dialog_closed()
        except Exception:
            _logger.warning("Could not close the Instance Members dialog after a failure", exc_info=True)

    def _wait_until_dialog_closed(self) -> None:
        try:
            WebDriverWait(self.driver, Constants.INSTANCE_MEMBERS_TIMEOUT).until(
                lambda driver: not any(
                    d.is_displayed() for d in driver.find_elements(By.CSS_SELECTOR, Constants.INSTANCE_MEMBERS_DIALOG_CSS)
                )
            )
        except TimeoutException as error:
            raise RuntimeError("Instance Members dialog did not close after OK") from error
