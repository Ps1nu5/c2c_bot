import logging
import re
import threading
import time
import urllib.parse
from datetime import datetime, timedelta, timezone
from typing import Callable, Optional

from selenium import webdriver
from selenium.common.exceptions import (
    NoAlertPresentException,
    NoSuchElementException,
    StaleElementReferenceException,
    TimeoutException,
    WebDriverException,
)
from selenium.webdriver.common.by import By
from selenium.webdriver.firefox.options import Options
from selenium.webdriver.firefox.service import Service
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import Select, WebDriverWait

from config import (
    ALERT_WAIT_TIMEOUT,
    ELEMENT_WAIT_TIMEOUT,
    LOGIN_URL,
    ORDERS_BASE_URL,
    PAGE_LOAD_TIMEOUT,
    POLL_INTERVAL,
    TRADER_URL,
)

logger = logging.getLogger(__name__)

# Login form
SEL_EMAIL_INPUT    = (By.CSS_SELECTOR, "input[type='email'], input[name='email'], input[autocomplete='email']")
SEL_PASSWORD_INPUT = (By.CSS_SELECTOR, "input[type='password']")
SEL_SUBMIT_BUTTON  = (By.CSS_SELECTOR, "button[type='submit']")

# Toolbar: filter open button — identified by the filter/funnel SVG icon path.
# Avoids class-based matching since biDnNR is shared across many unrelated buttons.
SEL_FILTER_BUTTON  = (By.XPATH,
    "//button[.//*[local-name()='path' and ("
    "contains(@d,'M13.994') or "      # from live HTML
    "contains(@d,'M14 2H2') or "      # common filter icon variant
    "contains(@d,'M3 4a1')  or "      # another variant
    "contains(@d,'M1 3h14')           "
    ")]]"
)

# Refresh button — there are two eihCyf buttons: search (magnifier) and refresh (circular arrow).
# The refresh icon path starts with M12.794 (circular arrow).
SEL_REFRESH_BUTTON = (By.XPATH,
    "//button[contains(@class,'eihCyf') and "
    ".//*[local-name()='path' and contains(@d,'M12.794')]]"
)

# Amount checkbox: the ljCEoY class is shared across ALL filter rows (Date, Status, Amount, etc.)
# Must find specifically the one whose label contains "Amount" or "Сумма"
SEL_AMOUNT_CHECKBOX= (By.XPATH,
    "//div[contains(@class,'ljCEoY') and "
    "(.//span[normalize-space(.)='Amount'] or .//span[normalize-space(.)='Сумма'] or .//span[normalize-space(.)='Sum'])"
    "]//input[@type='checkbox']"
)
SEL_AMOUNT_SELECT  = (By.CSS_SELECTOR, "select.sc-19onufu-0")
SEL_AMOUNT_INPUTS  = (By.CSS_SELECTOR, "input.sc-1y8nk6y-0.dOPfuZ")

# Filter submit: "Готово" / "Done" / "Apply" — NOT type=submit, just type=button
SEL_FILTER_SUBMIT  = (By.XPATH,
    "//button[normalize-space(.)='Готово' or normalize-space(.)='Done' "
    "or normalize-space(.)='Apply' or normalize-space(.)='OK']"
)

SEL_TABLE_BODY     = (By.CSS_SELECTOR, "div[role='rowgroup']")
SEL_ORDER_ROWS     = (By.CSS_SELECTOR, "div[role='row'].tr")

# Take/Взять button — search by text since class changes between sessions
SEL_TAKE_BUTTON    = (By.XPATH, ".//button[normalize-space(.)='Take' or normalize-space(.)='Взять']")


def _build_orders_url() -> str:
    tz = timezone(timedelta(hours=3))
    from_date = datetime.now(tz).replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    from_str = urllib.parse.quote(from_date.strftime("%Y-%m-%dT%H:%M:%S+03:00"), safe="")
    t = "22314268-b9f0-48fd-8901-30419acd2419"
    return f"{ORDERS_BASE_URL}?from={from_str}&status=new&t={t}"


def _extract_amount(row) -> Optional[float]:
    try:
        cells = row.find_elements(By.CSS_SELECTOR, "div[role='cell']")
        for cell in cells:
            title = cell.get_attribute("title") or ""
            if "RUB" in title:
                cleaned = title.replace(",", ".").replace(" ", "").replace(" ", "")
                import re as _re
                cleaned = _re.sub(r"[^\d.]", "", cleaned)
                parts = cleaned.split(".")
                cleaned = parts[0] if len(parts) > 2 else cleaned
                return abs(float(cleaned)) if cleaned else None
        amount_div = row.find_element(By.CSS_SELECTOR, "div[title]")
        title = amount_div.get_attribute("title") or ""
        import re as _re
        cleaned = _re.sub(r"[^\d.,]", "", title).replace(",", ".").replace(" ", "").replace(" ", "")
        return abs(float(cleaned)) if cleaned else None
    except (NoSuchElementException, ValueError):
        return None


def _extract_slug(row) -> Optional[str]:
    try:
        link = row.find_element(By.CSS_SELECTOR, "a[href*='/trader/orders/']")
        href = link.get_attribute("href") or ""
        import re as _re
        match = _re.search(r"/trader/orders/(trade-[^/?]+)", href)
        return match.group(1) if match else None
    except NoSuchElementException:
        return None


class SeleniumWorker:
    def __init__(
        self,
        on_order_taken: Callable[[str, Optional[float]], None],
        on_order_failed: Callable[[str, Optional[float]], None],
        headless: bool = True,
    ) -> None:
        self._on_order_taken = on_order_taken
        self._on_order_failed = on_order_failed
        self._headless = headless
        self._stop_event = threading.Event()
        self._thread: Optional[threading.Thread] = None
        self._driver: Optional[webdriver.Firefox] = None
        self._orders_url: str = ""
        self.login: str = ""
        self.password: str = ""
        self.min_amount: Optional[float] = None
        self.max_amount: Optional[float] = None

    def start(self, login: str, password: str, min_amount: Optional[float], max_amount: Optional[float]) -> None:
        if self._thread and self._thread.is_alive():
            logger.warning("Worker already running")
            return
        self.login = login
        self.password = password
        self.min_amount = min_amount
        self.max_amount = max_amount
        self._stop_event.clear()
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()
        logger.info("SeleniumWorker started")

    def stop(self) -> None:
        self._stop_event.set()
        if self._thread:
            self._thread.join(timeout=15)
        logger.info("SeleniumWorker stopped")

    def is_running(self) -> bool:
        return self._thread is not None and self._thread.is_alive()

    def _run(self) -> None:
        try:
            self._driver = self._create_driver()
            self._login()
            self._navigate_to_orders()
            self._apply_amount_filter()
            self._poll_loop()
        except Exception as exc:
            logger.exception("Worker crashed: %s", exc)
        finally:
            self._quit_driver()

    def _create_driver(self) -> webdriver.Firefox:
        options = Options()
        if self._headless:
            options.add_argument("--headless")
        options.add_argument("--width=1920")
        options.add_argument("--height=1080")
        options.set_preference("dom.webdriver.enabled", False)
        options.set_preference("useAutomationExtension", False)
        try:
            service = Service()
            driver = webdriver.Firefox(service=service, options=options)
        except Exception:
            driver = webdriver.Firefox(options=options)
        driver.set_page_load_timeout(PAGE_LOAD_TIMEOUT)
        driver.implicitly_wait(0)
        return driver

    def _wait(self, timeout: int = ELEMENT_WAIT_TIMEOUT) -> WebDriverWait:
        return WebDriverWait(self._driver, timeout)

    def _login(self) -> None:
        logger.info("Navigating to login page")
        self._driver.get(LOGIN_URL)
        email_input = self._wait().until(EC.presence_of_element_located(SEL_EMAIL_INPUT))
        email_input.clear()
        email_input.send_keys(self.login)
        password_input = self._driver.find_element(*SEL_PASSWORD_INPUT)
        password_input.clear()
        password_input.send_keys(self.password)
        submit = self._driver.find_element(*SEL_SUBMIT_BUTTON)
        submit.click()
        self._wait(PAGE_LOAD_TIMEOUT).until(
            lambda d: d.current_url != LOGIN_URL and "/login" not in d.current_url
        )
        logger.info("Login successful, current url: %s", self._driver.current_url)

    def _navigate_to_orders(self) -> None:
        logger.info("Navigating to trader role page")
        self._driver.get(TRADER_URL)
        self._wait_page_ready()
        self._orders_url = _build_orders_url()
        logger.info("Navigating to orders: %s", self._orders_url)
        self._driver.get(self._orders_url)
        self._wait_for_table()

    def _apply_amount_filter(self) -> None:
        logger.info(
            "FILTER ENTRY: min_amount=%s max_amount=%s url=%s",
            self.min_amount, self.max_amount, self._driver.current_url
        )
        if self.min_amount is None and self.max_amount is None:
            logger.info("No amount filter configured, skipping")
            return

        logger.info("Applying amount filter: min=%s max=%s", self.min_amount, self.max_amount)

        try:
            all_btns = self._driver.find_elements(By.XPATH, "//button")
            logger.info("FILTER DEBUG: total buttons on page = %d", len(all_btns))
            filter_btn = self._wait().until(EC.element_to_be_clickable(SEL_FILTER_BUTTON))
            logger.info("FILTER DEBUG: filter button found, text=%r", filter_btn.text)
            self._driver.execute_script("arguments[0].click();", filter_btn)
            time.sleep(1.2)
        except TimeoutException:
            logger.warning("Filter button not found (XPath=%s), skipping", SEL_FILTER_BUTTON[1])
            # dump all button texts to help diagnose
            try:
                btns = self._driver.find_elements(By.XPATH, "//button")
                for i, b in enumerate(btns[:20]):
                    svgs = b.find_elements(By.TAG_NAME, "svg")
                    logger.warning("  btn[%d] text=%r svg_count=%d", i, b.text[:40], len(svgs))
            except Exception:
                pass
            return

        # Dump filter row labels for debugging
        try:
            labels = self._driver.execute_script(
                "return Array.from(document.querySelectorAll('div.ljCEoY')).map(function(el){"
                "  var cb = el.querySelector('input[type=checkbox]');"
                "  var lbl = el.querySelector('span');"
                "  return (lbl ? lbl.textContent.trim() : '?') + ' checked=' + (cb ? cb.checked : '?');"
                "});"
            )
            logger.info("FILTER ROWS: %s", labels)
        except Exception as exc:
            logger.warning("Could not dump filter rows: %s", exc)

        # Find the Amount filter row container (div.ljCEoY that has "Amount"/"Сумма" label)
        amount_row = self._find_amount_row()
        if amount_row is None:
            logger.warning("Could not find amount filter row, skipping filter")
            return

        # Find and click the checkbox WITHIN the Amount row (not globally)
        try:
            checkbox = amount_row.find_element(By.CSS_SELECTOR, "input[type='checkbox']")
        except NoSuchElementException:
            logger.warning("No checkbox inside amount filter row, skipping filter")
            return

        is_checked = checkbox.is_selected() or checkbox.get_attribute("checked") is not None
        logger.info("Amount checkbox found, checked=%s", is_checked)
        if not is_checked:
            self._driver.execute_script("arguments[0].click();", checkbox)
            time.sleep(0.8)
            logger.info("Amount checkbox activated")

        # After clicking, the expanded section appears as a sibling or child of the row's parent.
        # We search for the select and inputs in the PARENT of the amount_row (the whole filter
        # block for "Amount"), scoped to avoid picking up Date/Status inputs.
        amount_parent = self._driver.execute_script("return arguments[0].parentNode;", amount_row)

        try:
            # Find <select> within the Amount filter block
            select_el = WebDriverWait(self._driver, ELEMENT_WAIT_TIMEOUT).until(
                lambda d: self._find_in_parent(amount_parent, "select")
            )
            current_val = select_el.get_attribute("value") or ""
            logger.info("Amount select current value: %r", current_val)
            if current_val != "is_between":
                # React requires native setter + event to trigger state update
                self._driver.execute_script("""
                    var sel = arguments[0];
                    var nativeInputValueSetter = Object.getOwnPropertyDescriptor(window.HTMLSelectElement.prototype, 'value').set;
                    nativeInputValueSetter.call(sel, 'is_between');
                    sel.dispatchEvent(new Event('change', {bubbles: true}));
                """, select_el)
                time.sleep(0.5)
                logger.info("Amount select set to is_between via JS")
            else:
                logger.info("Amount select already at is_between, no change needed")
        except (TimeoutException, Exception) as exc:
            logger.warning("Could not find/set amount select: %s", exc)

        # Wait a moment for the two text inputs to appear inside the Amount block
        time.sleep(0.3)
        try:
            # Find all visible text inputs WITHIN the Amount filter parent block only
            all_inputs = amount_parent.find_elements(By.CSS_SELECTOR, "input[type='text'], input:not([type='checkbox'])")
            visible = [i for i in all_inputs if i.is_displayed()]
            logger.info("Found %d visible amount inputs (scoped to amount block)", len(visible))
            if len(visible) >= 2:
                if self.min_amount is not None:
                    self._set_react_input(visible[0], str(int(self.min_amount)))
                    logger.info("Min amount entered: %s", self.min_amount)
                if self.max_amount is not None:
                    self._set_react_input(visible[1], str(int(self.max_amount)))
                    logger.info("Max amount entered: %s", self.max_amount)
            elif len(visible) == 1:
                # Only one input visible — might be "equals" mode, set whichever is provided
                val = self.min_amount if self.min_amount is not None else self.max_amount
                if val is not None:
                    self._set_react_input(visible[0], str(int(val)))
                    logger.info("Single amount input entered: %s", val)
            else:
                logger.warning("No visible amount inputs found inside Amount block after checkbox click")
        except Exception as exc:
            logger.warning("Could not fill amount inputs: %s", exc)
            return

        try:
            submit_btn = self._wait().until(EC.element_to_be_clickable(SEL_FILTER_SUBMIT))
            self._driver.execute_script("arguments[0].click();", submit_btn)
            time.sleep(0.5)
            self._wait_for_table()
            logger.info("Filter applied successfully")
        except TimeoutException:
            logger.warning("Filter submit button not found")

    def _find_amount_row(self):
        """Return the div.ljCEoY container element that contains the Amount/Сумма label.

        Structure (from live HTML):
          div.ljCEoY                  ← THIS element is returned
            div.kYNfQp
              input[type=checkbox]
              label > span "Amount"
          [sibling div with react-slidedown — appears after checkbox is checked]

        The select and inputs live OUTSIDE this div (as a sibling inside the parent),
        so we return the row div itself and let the caller access parentNode for scoping.
        """
        # Strategy 1: XPATH — div.ljCEoY whose descendant span text is Amount / Сумма
        for label_text in ("Amount", "Сумма", "Sum"):
            try:
                row = self._wait(10).until(EC.presence_of_element_located((
                    By.XPATH,
                    f"//div[contains(@class,'ljCEoY') and "
                    f".//span[normalize-space(.)='{label_text}']]"
                )))
                logger.info("Amount filter row found via label '%s'", label_text)
                return row
            except TimeoutException:
                continue

        # Strategy 2: any div.ljCEoY that contains a checkbox — take the 4th one
        # (typical order: Date, Status, Type, Amount, Card, Phone, …)
        try:
            rows = self._driver.find_elements(By.CSS_SELECTOR, "div.ljCEoY")
            logger.info("Strategy 2: found %d div.ljCEoY rows", len(rows))
            # Amount is usually the 4th filter row (index 3)
            if len(rows) >= 4:
                logger.info("Amount filter row found via strategy 2 (index 3)")
                return rows[3]
            elif rows:
                logger.info("Amount filter row found via strategy 2 (last row)")
                return rows[-1]
        except Exception as exc:
            logger.warning("Strategy 2 failed: %s", exc)

        logger.warning("Could not find amount filter row by any strategy")
        return None

    def _find_in_parent(self, parent, tag: str):
        """Find the first visible <tag> element inside a JS parent node.

        Used as a WebDriverWait lambda to wait for elements that appear
        only after a checkbox is clicked (animated slidedown).
        Returns the element or False (so WebDriverWait keeps polling).
        """
        try:
            elements = parent.find_elements(By.TAG_NAME, tag)
            for el in elements:
                if el.is_displayed():
                    return el
        except Exception:
            pass
        return False

    def _poll_loop(self) -> None:
        logger.info("Starting poll loop")
        while not self._stop_event.is_set():
            try:
                self._poll_once()
            except WebDriverException as exc:
                if self._stop_event.is_set():
                    break
                logger.error("WebDriverException in poll loop: %s", exc)
                time.sleep(2)
            except Exception as exc:
                if self._stop_event.is_set():
                    break
                logger.exception("Unexpected error in poll loop: %s", exc)
                time.sleep(2)
            self._stop_event.wait(POLL_INTERVAL)

    def _poll_once(self) -> None:
        try:
            refresh_btn = self._wait(5).until(EC.element_to_be_clickable(SEL_REFRESH_BUTTON))
            self._driver.execute_script("arguments[0].click();", refresh_btn)
            logger.debug("Refresh button clicked")
        except (NoSuchElementException, TimeoutException):
            logger.debug("Refresh button not found, falling back to driver.get")
            self._driver.get(self._orders_url)
        self._wait_for_table()
        rows = self._get_order_rows()
        if not rows:
            return
        for row in rows:
            if self._stop_event.is_set():
                return
            self._process_row(row)

    def _get_order_rows(self) -> list:
        try:
            rows = self._driver.find_elements(*SEL_ORDER_ROWS)
            return [
                r for r in rows
                if "position: absolute" in (r.get_attribute("style") or "")
            ]
        except WebDriverException:
            return []

    def _process_row(self, row) -> None:
        slug = None
        amount = None
        try:
            slug = _extract_slug(row)
            amount = _extract_amount(row)
            if slug is None:
                return
            take_buttons = row.find_elements(*SEL_TAKE_BUTTON)
            if not take_buttons:
                return
            take_btn = take_buttons[0]
            if not take_btn.is_displayed() or not take_btn.is_enabled():
                return
            logger.info("Taking order %s amount=%s", slug, amount)
            self._driver.execute_script("arguments[0].click();", take_btn)
            self._confirm_alert()
            logger.info("Order %s taken successfully", slug)
            self._on_order_taken(slug, amount)
        except NoAlertPresentException:
            logger.warning("No alert after Take for order %s", slug)
            self._on_order_failed(slug or "unknown", amount)
        except StaleElementReferenceException:
            logger.debug("Stale element for order %s, skipping", slug)
        except WebDriverException as exc:
            logger.error("WebDriverException taking order %s: %s", slug, exc)
            self._on_order_failed(slug or "unknown", amount)

    def _confirm_alert(self) -> None:
        end_time = time.time() + ALERT_WAIT_TIMEOUT
        while time.time() < end_time:
            try:
                alert = self._driver.switch_to.alert
                alert.accept()
                return
            except NoAlertPresentException:
                time.sleep(0.1)
        raise NoAlertPresentException("Alert did not appear within timeout")

    def _wait_for_table(self) -> None:
        try:
            WebDriverWait(self._driver, PAGE_LOAD_TIMEOUT).until(
                lambda d: d.execute_script("return document.readyState") == "complete"
            )
        except TimeoutException:
            pass
        # Wait for table container AND at least one row OR empty state indicator
        for _ in range(40):
            try:
                body = self._driver.find_element(*SEL_TABLE_BODY)
                # Check: rows rendered OR loading spinner gone
                inner = body.get_attribute("innerHTML") or ""
                if "Loading" not in inner and len(inner) > 50:
                    time.sleep(0.2)
                    return
            except NoSuchElementException:
                pass
            time.sleep(0.25)
        logger.warning("Table did not finish rendering after waiting")

    def _wait_page_ready(self) -> None:
        try:
            WebDriverWait(self._driver, PAGE_LOAD_TIMEOUT).until(
                lambda d: d.execute_script("return document.readyState") == "complete"
            )
            time.sleep(0.2)
        except TimeoutException:
            pass

    def _set_react_input(self, element, value: str) -> None:
        self._driver.execute_script("""
            var input = arguments[0];
            var val = arguments[1];
            var nativeInputValueSetter = Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype, 'value').set;
            nativeInputValueSetter.call(input, val);
            input.dispatchEvent(new Event('input', {bubbles: true}));
            input.dispatchEvent(new Event('change', {bubbles: true}));
        """, element, value)

    def _quit_driver(self) -> None:
        if self._driver:
            try:
                self._driver.quit()
            except Exception:
                pass
            self._driver = None
