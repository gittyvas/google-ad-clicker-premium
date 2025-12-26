import sys
import json
import random
from datetime import datetime
from time import sleep
from threading import Thread
from typing import Any, Optional, Union

import selenium
from selenium.webdriver import ActionChains
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import (
    JavascriptException,
    TimeoutException,
    NoSuchElementException,
    ElementNotInteractableException,
    ElementClickInterceptedException,
    StaleElementReferenceException,
)

import hooks
from adb import adb_controller
from clicklogs_db import ClickLogsDB
from config_reader import config
from logger import logger
from stats import SearchStats
from utils import (
    Direction,
    add_cookies,
    get_random_sleep,
    resolve_redirect,
    boost_requests,
)
from webdriver import execute_stealth_js_code


LinkElement = selenium.webdriver.remote.webelement.WebElement
AdList = list[tuple[LinkElement, str, str]]
NonAdList = list[LinkElement]
AllLinks = list[Union[AdList, NonAdList]]


class SearchController:
    """Search controller for JuicyAds clicker

    :type driver: selenium.webdriver
    :param driver: Selenium Chrome webdriver instance
    :type query: str
    :param query: Search query (not used for direct site mode)
    :type country_code: str
    :param country_code: Country code for the proxy IP
    """

    # Your target URL with JuicyAds
    URL = "https://stellaplus.netlify.app/"

    # JuicyAds specific ad zone ID from your HTML snippet
    JUICYADS_ZONE_ID = "1107020"

    def __init__(
        self, driver: selenium.webdriver, query: str, country_code: Optional[str] = None
    ) -> None:
        self._driver = driver
        self._search_query, self._filter_words = self._process_query(query)
        self._exclude_list = None
        self._random_mouse_enabled = config.behavior.random_mouse
        self._use_custom_cookies = config.behavior.custom_cookies
        self._max_scroll_limit = config.behavior.max_scroll_limit
        self._hooks_enabled = config.behavior.hooks_enabled

        self._ad_page_min_wait = config.behavior.ad_page_min_wait
        self._ad_page_max_wait = config.behavior.ad_page_max_wait
        self._nonad_page_min_wait = config.behavior.nonad_page_min_wait
        self._nonad_page_max_wait = config.behavior.nonad_page_max_wait

        self._android_device_id = None

        self._stats = SearchStats()

        if config.behavior.excludes:
            self._exclude_list = [item.strip() for item in config.behavior.excludes.split(",")]
            logger.debug(f"Words to be excluded: {self._exclude_list}")

        self._clicklogs_db_client = ClickLogsDB()

        self._load()

    def search_for_ads(
        self, non_ad_domains: Optional[list[str]] = None
    ) -> tuple[AdList, NonAdList, AdList]:
        """Load the target site and return JuicyAds found on it

        :type non_ad_domains: list
        :param non_ad_domains: List of domains to select for non-ad links (not used)
        :rtype: tuple
        :returns: Tuple of [ad_links, non_ad_links, shopping_ads]
        """

        if self._use_custom_cookies:
            self._driver.delete_all_cookies()
            add_cookies(self._driver)

            for cookie in self._driver.get_cookies():
                logger.debug(cookie)

        logger.info(f"Loading target site: {self.URL}")
        sleep(get_random_sleep(2, 4) * config.behavior.wait_factor)

        if self._hooks_enabled:
            hooks.after_search_hook(self._driver)

        self._make_random_scrolls()
        self._make_random_mouse_movements()

        # Get all clickable JuicyAds links from the page
        ad_links = self._get_juicyads()

        # Return empty lists for non-ads and shopping ads since we're targeting JuicyAds only
        return (ad_links, [], [])

    def _get_juicyads(self) -> AdList:
        """Extract JuicyAds ad links from the target site

        Looks for JuicyAds specific elements:
        - ins tags with numeric IDs (JuicyAds ad containers like id="1107020")
        - iframes loaded by JuicyAds
        - links within JuicyAds containers

        :rtype: AdList
        :returns: List of (ad_element, ad_link, ad_title) tuples
        """

        logger.info("Getting JuicyAds links from target site...")

        ads = []

        # Wait for JuicyAds script to load and render ads
        logger.debug("Waiting for JuicyAds to load...")
        sleep(get_random_sleep(3, 5) * config.behavior.wait_factor)

        # Check if JuicyAds script is present
        try:
            juicyads_loaded = self._driver.execute_script(
                "return typeof window.adsbyjuicy !== 'undefined';"
            )
            logger.debug(f"JuicyAds script loaded: {juicyads_loaded}")
        except JavascriptException:
            logger.debug("Could not check JuicyAds script status")

        # Wait for the specific ad zone container
        try:
            WebDriverWait(self._driver, 15).until(
                EC.presence_of_element_located((By.ID, self.JUICYADS_ZONE_ID))
            )
            logger.debug(f"JuicyAds zone {self.JUICYADS_ZONE_ID} found")
        except TimeoutException:
            logger.warning(f"Timeout waiting for JuicyAds zone {self.JUICYADS_ZONE_ID}")

        # Give extra time for ad content to load inside the container
        sleep(get_random_sleep(3, 5) * config.behavior.wait_factor)

        # Try to find the main JuicyAds container first
        try:
            main_container = self._driver.find_element(By.ID, self.JUICYADS_ZONE_ID)
            if main_container:
                data_width = main_container.get_attribute("data-width") or "908"
                data_height = main_container.get_attribute("data-height") or "258"
                title = f"JuicyAds Zone {self.JUICYADS_ZONE_ID} ({data_width}x{data_height})"

                # Check if there's content inside the container
                inner_html = main_container.get_attribute("innerHTML").strip()
                if inner_html:
                    logger.info(f"Found JuicyAds container with content: {title}")

                    # Look for clickable elements inside the container
                    clickable_found = False

                    # Check for iframes inside the container
                    try:
                        iframes = main_container.find_elements(By.TAG_NAME, "iframe")
                        for iframe in iframes:
                            ads.append((iframe, f"juicyads://zone/{self.JUICYADS_ZONE_ID}", f"{title} (iframe)"))
                            clickable_found = True
                            logger.debug("Found iframe inside JuicyAds container")
                    except NoSuchElementException:
                        pass

                    # Check for links inside the container
                    try:
                        links = main_container.find_elements(By.TAG_NAME, "a")
                        for link in links:
                            href = link.get_attribute("href")
                            if href:
                                ads.append((link, href, f"{title} (link)"))
                                clickable_found = True
                                logger.debug(f"Found link inside JuicyAds container: {href}")
                    except NoSuchElementException:
                        pass

                    # Check for images inside the container
                    try:
                        images = main_container.find_elements(By.TAG_NAME, "img")
                        for img in images:
                            src = img.get_attribute("src")
                            if src:
                                ads.append((img, src, f"{title} (banner)"))
                                clickable_found = True
                                logger.debug(f"Found image inside JuicyAds container: {src}")
                    except NoSuchElementException:
                        pass

                    # If no specific clickable element found, use the container itself
                    if not clickable_found:
                        ads.append((main_container, f"juicyads://zone/{self.JUICYADS_ZONE_ID}", title))
                        logger.debug("Using JuicyAds container as clickable element")
                else:
                    # Container exists but empty - JuicyAds may not have loaded
                    logger.warning(f"JuicyAds container {self.JUICYADS_ZONE_ID} is empty")
                    # Still add it as clickable - sometimes ads load on interaction
                    ads.append((main_container, f"juicyads://zone/{self.JUICYADS_ZONE_ID}", title))

        except NoSuchElementException:
            logger.warning(f"JuicyAds container with ID {self.JUICYADS_ZONE_ID} not found")

        # Also look for any iframes that JuicyAds might have injected anywhere on page
        try:
            all_iframes = self._driver.find_elements(By.TAG_NAME, "iframe")
            for iframe in all_iframes:
                src = iframe.get_attribute("src") or ""
                name = iframe.get_attribute("name") or ""
                iframe_id = iframe.get_attribute("id") or ""

                # Check if this is a JuicyAds iframe
                if any(x in src.lower() for x in ['jads', 'juicy', 'poweredby']) or \
                   any(x in name.lower() for x in ['jads', 'juicy']) or \
                   any(x in iframe_id.lower() for x in ['jads', 'juicy']):

                    # Avoid duplicates
                    if not any(ad[0] == iframe for ad in ads):
                        ads.append((iframe, src or f"juicyads://iframe", "JuicyAds iframe"))
                        logger.debug(f"Found JuicyAds iframe: src={src}, name={name}")

                        # Try to get clickable elements inside iframe
                        try:
                            self._driver.switch_to.frame(iframe)
                            iframe_links = self._driver.find_elements(By.CSS_SELECTOR, "a")
                            for link in iframe_links:
                                href = link.get_attribute("href")
                                if href and href.startswith("http"):
                                    ads.append((link, href, "JuicyAds iframe link"))
                                    logger.debug(f"Found link in JuicyAds iframe: {href}")
                            self._driver.switch_to.default_content()
                        except Exception as e:
                            logger.debug(f"Could not inspect iframe contents: {e}")
                            self._driver.switch_to.default_content()

        except NoSuchElementException:
            pass

        self._stats.ads_found = len(ads)
        logger.info(f"Found {len(ads)} JuicyAds elements on the page")

        # Debug: log page source snippet if no ads found
        if len(ads) == 0:
            logger.debug("No JuicyAds found. Checking page content...")
            page_source = self._driver.page_source

            if "adsbyjuicy" in page_source.lower():
                logger.debug("JuicyAds push code detected in page")
            if "jads.js" in page_source.lower():
                logger.debug("JuicyAds script reference detected in page")
            if self.JUICYADS_ZONE_ID in page_source:
                logger.debug(f"Zone ID {self.JUICYADS_ZONE_ID} found in page source")

            # Log the ins element if present
            if f'id="{self.JUICYADS_ZONE_ID}"' in page_source or f"id='{self.JUICYADS_ZONE_ID}'" in page_source:
                logger.debug("ins element with zone ID is in page source")

        # Apply filters if configured
        if self._filter_words:
            filtered_ads = []
            for ad in ads:
                ad_link = ad[1].lower()
                ad_title = ad[2].lower()
                for word in self._filter_words:
                    if word in ad_link or word in ad_title:
                        filtered_ads.append(ad)
                        self._stats.num_filtered_ads += 1
                        break
            ads = filtered_ads

        # Apply excludes if configured
        if self._exclude_list:
            final_ads = []
            for ad in ads:
                ad_link = ad[1].lower()
                ad_title = ad[2].lower()
                excluded = False
                for exclude in self._exclude_list:
                    if exclude.lower() in ad_link or exclude.lower() in ad_title:
                        logger.debug(f"Excluding: [{ad[2]}] -> {ad[1]}")
                        self._stats.num_excluded_ads += 1
                        excluded = True
                        break
                if not excluded:
                    final_ads.append(ad)
            ads = final_ads

        return ads

    def click_shopping_ads(self, shopping_ads: AdList) -> None:
        """Click shopping ads if there are any (not used for JuicyAds)

        :type shopping_ads: AdList
        :param shopping_ads: List of (ad, ad_link, ad_title) tuples
        """
        # Not applicable for JuicyAds - kept for interface compatibility
        pass

    def click_links(self, links: AllLinks) -> None:
        """Click links

        :type links: AllLinks
        :param links: List of [(ad, ad_link, ad_title), non_ad_links]
        """

        execute_stealth_js_code(self._driver)

        # store the ID of the original window
        original_window_handle = self._driver.current_window_handle

        for link in links:
            is_ad_element = isinstance(link, tuple)

            try:
                link_element, link_url, ad_title = self._extract_link_info(link, is_ad_element)

                if self._hooks_enabled and is_ad_element:
                    hooks.before_ad_click_hook(self._driver)

                logger.info(
                    f"Clicking to {'[' + ad_title + '](' + link_url + ')' if is_ad_element else '[' + link_url + ']'}..."
                )

                category = "Ad" if is_ad_element else "Non-ad"

                if config.behavior.send_to_android and self._android_device_id:
                    self._handle_android_click(link_element, link_url, is_ad_element, category)
                else:
                    self._handle_browser_click(
                        link_element, link_url, is_ad_element, original_window_handle, category
                    )

                # scroll the page to avoid elements remain outside of the view
                self._driver.execute_script("arguments[0].scrollIntoView(true);", link_element)

            except StaleElementReferenceException:
                logger.debug(
                    f"Ad element [{ad_title if is_ad_element else link_url}] has changed. "
                    "Skipping scroll into view..."
                )

            except Exception:
                logger.error(f"Failed to click on [{ad_title if is_ad_element else link_url}]!")

    def _extract_link_info(self, link: Any, is_ad_element: bool) -> tuple:
        """Extract link information

        :type link: tuple(ad, ad_link, ad_title) or LinkElement
        :param link: (ad, ad_link, ad_title) for ads LinkElement for non-ads
        :type is_ad_element: bool
        :param is_ad_element: Whether it is an ad or non-ad link
        :rtype: tuple
        :returns: (link_element, link_url, ad_title) tuple
        """

        if is_ad_element:
            link_element = link[0]
            link_url = link[1]
            ad_title = link[2]
        else:
            link_element = link
            link_url = link_element.get_attribute("href")
            ad_title = None

        return (link_element, link_url, ad_title)

    def _handle_android_click(
        self,
        link_element: selenium.webdriver.remote.webelement.WebElement,
        link_url: str,
        is_ad_element: bool,
        category: str = "Ad",
    ) -> None:
        """Handle opening link on Android device

        :type link_element: selenium.webdriver.remote.webelement.WebElement
        :param link_element: Link element
        :type link_url: str
        :param link_url: Canonical url for the clicked link
        :type is_ad_element: bool
        :param is_ad_element: Whether it is an ad or non-ad link
        :type category: str
        :param category: Specifies link category as Ad or Non-ad
        """

        url = link_element.get_attribute("href") or link_url
        url = resolve_redirect(url)

        adb_controller.open_url(url, self._android_device_id)

        click_time = datetime.now().strftime("%H:%M:%S")

        # wait a little before starting random actions
        sleep(get_random_sleep(2, 3) * config.behavior.wait_factor)

        logger.debug(f"Current url on device: {url}")

        if self._hooks_enabled and category == "Ad":
            hooks.after_ad_click_hook(self._driver)

        self._start_random_scroll_thread()

        site_url = link_url if category == "Ad" else "/".join(url.split("/", maxsplit=3)[:3])

        self._update_click_stats(site_url, click_time, category)

        if config.behavior.request_boost:
            boost_requests(url)

        wait_time = self._get_wait_time(is_ad_element) * config.behavior.wait_factor
        logger.debug(f"Waiting {wait_time} seconds on {category.lower()} page...")
        sleep(wait_time)

        adb_controller.close_browser()
        sleep(get_random_sleep(0.5, 1) * config.behavior.wait_factor)

    def _handle_browser_click(
        self,
        link_element: selenium.webdriver.remote.webelement.WebElement,
        link_url: str,
        is_ad_element: bool,
        original_window_handle: str,
        category: str = "Ad",
    ) -> None:
        """Handle clicking in the browser

        :type link_element: selenium.webdriver.remote.webelement.WebElement
        :param link_element: Link element
        :type link_url: str
        :param link_url: Canonical url for the clicked link
        :type is_ad_element: bool
        :param is_ad_element: Whether it is an ad or non-ad link
        :type original_window_handle: str
        :param original_window_handle: Window handle for the search results tab
        :type category: str
        :param category: Specifies link category as Ad or Non-ad
        """

        # For JuicyAds ins/iframe/img elements, try direct click first
        tag_name = link_element.tag_name.lower()
        if tag_name in ("ins", "iframe", "img", "div"):
            try:
                # Scroll element into view
                self._driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", link_element)
                sleep(get_random_sleep(0.5, 1) * config.behavior.wait_factor)

                # Try JavaScript click for better reliability with JuicyAds
                try:
                    self._driver.execute_script("arguments[0].click();", link_element)
                except JavascriptException:
                    link_element.click()

                click_time = datetime.now().strftime("%H:%M:%S")

                sleep(get_random_sleep(2, 3) * config.behavior.wait_factor)

                # Check if new window/tab opened
                if len(self._driver.window_handles) > 1:
                    for window_handle in self._driver.window_handles:
                        if window_handle != original_window_handle:
                            self._driver.switch_to.window(window_handle)

                            sleep(get_random_sleep(2, 3) * config.behavior.wait_factor)
                            logger.debug(f"Current url on new tab: {self._driver.current_url}")

                            if self._hooks_enabled and category == "Ad":
                                hooks.after_ad_click_hook(self._driver)

                            self._start_random_action_threads()

                            self._update_click_stats(self._driver.current_url, click_time, category)

                            if config.behavior.request_boost:
                                boost_requests(self._driver.current_url)

                            wait_time = self._get_wait_time(is_ad_element) * config.behavior.wait_factor
                            logger.debug(f"Waiting {wait_time} seconds on {category.lower()} page...")
                            sleep(wait_time)

                            self._driver.close()
                            break

                    self._driver.switch_to.window(original_window_handle)
                    sleep(get_random_sleep(1, 1.5) * config.behavior.wait_factor)
                    return
                else:
                    # Click happened but no new tab - log it anyway
                    self._update_click_stats(link_url, click_time, category)
                    logger.debug("Click registered but no new tab opened")
                    return

            except (ElementClickInterceptedException, ElementNotInteractableException) as e:
                logger.debug(f"Direct click failed on {tag_name}: {e}")
                # Fall through to standard click handling

        self._open_link_in_new_tab(link_element)

        if len(self._driver.window_handles) != 2:
            logger.debug("Couldn't click! Scrolling element into view...")
            self._driver.execute_script("arguments[0].scrollIntoView(true);", link_element)
            self._open_link_in_new_tab(link_element)

        if len(self._driver.window_handles) != 2:
            logger.debug(f"Failed to open '{link_url}' in a new tab!")
            return
        else:
            logger.debug("Opened link in a new tab. Switching to tab...")

        for window_handle in self._driver.window_handles:
            if window_handle != original_window_handle:
                self._driver.switch_to.window(window_handle)
                click_time = datetime.now().strftime("%H:%M:%S")

                sleep(get_random_sleep(3, 5) * config.behavior.wait_factor)
                logger.debug(f"Current url on new tab: {self._driver.current_url}")

                if self._hooks_enabled and category == "Ad":
                    hooks.after_ad_click_hook(self._driver)

                self._start_random_action_threads()

                url = link_url if is_ad_element else self._driver.current_url

                self._update_click_stats(url, click_time, category)

                if config.behavior.request_boost:
                    boost_requests(self._driver.current_url)

                wait_time = self._get_wait_time(is_ad_element) * config.behavior.wait_factor
                logger.debug(f"Waiting {wait_time} seconds on {category.lower()} page...")
                sleep(wait_time)

                self._driver.close()
                break

        # go back to the original window
        self._driver.switch_to.window(original_window_handle)
        sleep(get_random_sleep(1, 1.5) * config.behavior.wait_factor)

    def _open_link_in_new_tab(
        self, link_element: selenium.webdriver.remote.webelement.WebElement
    ) -> None:
        """Open the link in a new browser tab

        :type link_element: selenium.webdriver.remote.webelement.WebElement
        :param link_element: Link element
        """

        platform = sys.platform
        control_command_key = Keys.COMMAND if platform.endswith("darwin") else Keys.CONTROL

        try:
            actions = ActionChains(self._driver)
            actions.move_to_element(link_element)
            actions.key_down(control_command_key)
            actions.click()
            actions.key_up(control_command_key)
            actions.perform()

            sleep(get_random_sleep(0.5, 1) * config.behavior.wait_factor)

        except JavascriptException as exp:
            error_message = str(exp).split("\n")[0]

            if "has no size and location" in error_message:
                logger.error(
                    f"Failed to click element[{link_element.get_attribute('outerHTML')}]! "
                    "Skipping..."
                )

    def _get_wait_time(self, is_ad_element: bool) -> int:
        """Get wait time based on whether the link is an ad or non-ad

        :type is_ad_element: bool
        :param is_ad_element: Whether it is an ad or non-ad link
        :rtype: int
        :returns: Randomly selected number from the given range
        """

        if is_ad_element:
            return random.choice(range(self._ad_page_min_wait, self._ad_page_max_wait))
        else:
            return random.choice(range(self._nonad_page_min_wait, self._nonad_page_max_wait))

    def _update_click_stats(self, url: str, click_time: str, category: str) -> None:
        """Update click statistics

        :type url: str
        :param url: Clicked link url to save db
        :type click_time: str
        :param click_time: Click time in hh:mm:ss format
        :type category: str
        :param category: Specifies link category as Ad or Non-ad
        """

        if category == "Ad":
            self._stats.ads_clicked += 1
        elif category == "Non-ad":
            self._stats.non_ads_clicked += 1

        self._clicklogs_db_client.save_click(
            site_url=url, category=category, query=self._search_query, click_time=click_time
        )

    def _start_random_scroll_thread(self) -> None:
        """Start a thread for random swipes on Android device"""

        random_scroll_thread = Thread(target=self._make_random_swipes)
        random_scroll_thread.start()
        random_scroll_thread.join(
            timeout=float(max(self._ad_page_max_wait, self._nonad_page_max_wait))
        )

    def _start_random_action_threads(self) -> None:
        """Start threads for random actions on browser"""

        random_scroll_thread = Thread(target=self._make_random_scrolls)
        random_scroll_thread.start()
        random_mouse_thread = Thread(target=self._make_random_mouse_movements)
        random_mouse_thread.start()
        random_scroll_thread.join(
            timeout=float(max(self._ad_page_max_wait, self._nonad_page_max_wait))
        )
        random_mouse_thread.join(
            timeout=float(max(self._ad_page_max_wait, self._nonad_page_max_wait))
        )

    def end_search(self) -> None:
        """Close the browser.

        Delete cookies and cache before closing.
        """

        if self._driver:
            try:
                self._delete_cache_and_cookies()
                self._driver.quit()

            except Exception as exp:
                logger.debug(exp)

            self._driver = None

    def _load(self) -> None:
        """Load target site directly"""

        logger.info(f"Opening {self.URL}...")

        if config.webdriver.use_seleniumbase:
            self._driver.uc_open_with_reconnect(self.URL, reconnect_time=3)
        else:
            self._driver.get(self.URL)

    def _is_scroll_at_the_end(self) -> bool:
        """Check if scroll is at the end

        :rtype: bool
        :returns: Whether the scrollbar was reached to end or not
        """

        page_height = self._driver.execute_script("return document.body.scrollHeight;")
        total_scrolled_height = self._driver.execute_script(
            "return window.pageYOffset + window.innerHeight;"
        )

        return page_height - 1 <= total_scrolled_height

    def _delete_cache_and_cookies(self) -> None:
        """Delete browser cache, storage, and cookies"""

        logger.debug("Deleting browser cache and cookies...")

        try:
            self._driver.delete_all_cookies()

            self._driver.execute_cdp_cmd("Network.clearBrowserCache", {})
            self._driver.execute_cdp_cmd("Network.clearBrowserCookies", {})
            self._driver.execute_script("window.localStorage.clear();")
            self._driver.execute_script("window.sessionStorage.clear();")

        except Exception as exp:
            if "not connected to DevTools" in str(exp):
                logger.debug("Incognito mode is active. No need to delete cache. Skipping...")

    def _make_random_scrolls(self) -> None:
        """Make random scrolls on page"""

        logger.debug("Making random scrolls...")

        directions = [Direction.DOWN]
        directions += random.choices(
            [Direction.UP] * 5 + [Direction.DOWN] * 5, k=random.choice(range(1, 5))
        )

        logger.debug(f"Direction choices: {[d.value for d in directions]}")

        for direction in directions:
            if direction == Direction.DOWN and not self._is_scroll_at_the_end():
                self._driver.find_element(By.TAG_NAME, "body").send_keys(Keys.PAGE_DOWN)
            elif direction == Direction.UP:
                self._driver.find_element(By.TAG_NAME, "body").send_keys(Keys.PAGE_UP)

            sleep(get_random_sleep(1, 3) * config.behavior.wait_factor)

        self._driver.find_element(By.TAG_NAME, "body").send_keys(Keys.HOME)

    def _make_random_swipes(self) -> None:
        """Make random swipes on page"""

        logger.debug("Making random swipes...")

        directions = [Direction.DOWN, Direction.DOWN]
        directions += random.choices(
            [Direction.UP] * 5 + [Direction.DOWN] * 5, k=random.choice(range(1, 5))
        )

        logger.debug(f"Direction choices: {[d.value for d in directions]}")

        for direction in directions:
            if direction == Direction.DOWN:
                self._send_swipe(direction=Direction.DOWN)

            elif direction == Direction.UP:
                self._send_swipe(direction=Direction.UP)

            sleep(get_random_sleep(1, 2) * config.behavior.wait_factor)

        HOME_KEYCODE = 122
        adb_controller.send_keyevent(HOME_KEYCODE)  # go to top by sending Home key

    def _send_swipe(self, direction: Direction) -> None:
        """Send swipe action to mobile device

        :type direction: Direction
        :param direction: Direction to swipe
        """

        x_position = random.choice(range(100, 200))
        duration = random.choice(range(100, 500))

        if direction == Direction.DOWN:
            y_start_position = random.choice(range(1000, 1500))
            y_end_position = random.choice(range(500, 1000))

        elif direction == Direction.UP:
            y_start_position = random.choice(range(500, 1000))
            y_end_position = random.choice(range(1000, 1500))

        adb_controller.send_swipe(
            x1=x_position,
            y1=y_start_position,
            x2=x_position,
            y2=y_end_position,
            duration=duration,
        )

    def _make_random_mouse_movements(self) -> None:
        """Make random mouse movements"""

        if self._random_mouse_enabled:
            try:
                import pyautogui

                logger.debug("Making random mouse movements...")

                screen_width, screen_height = pyautogui.size()
                pyautogui.moveTo(screen_width / 2 - 300, screen_height / 2 - 200)

                logger.debug(pyautogui.position())

                ease_methods = [
                    pyautogui.easeInQuad,
                    pyautogui.easeOutQuad,
                    pyautogui.easeInOutQuad,
                ]

                logger.debug("Going LEFT and DOWN...")

                pyautogui.move(
                    -random.choice(range(200, 300)),
                    random.choice(range(250, 450)),
                    1,
                    random.choice(ease_methods),
                )

                logger.debug(pyautogui.position())

                for _ in range(1, random.choice(range(3, 7))):
                    direction = random.choice(list(Direction))
                    ease_method = random.choice(ease_methods)

                    logger.debug(f"Going {direction.value}...")

                    if direction == Direction.LEFT:
                        pyautogui.move(-(random.choice(range(100, 200))), 0, 0.5, ease_method)

                    elif direction == Direction.RIGHT:
                        pyautogui.move(random.choice(range(200, 400)), 0, 0.3, ease_method)

                    elif direction == Direction.UP:
                        pyautogui.move(0, -(random.choice(range(100, 200))), 1, ease_method)
                        pyautogui.scroll(random.choice(range(1, 7)))

                    elif direction == Direction.DOWN:
                        pyautogui.move(0, random.choice(range(150, 300)), 0.7, ease_method)
                        pyautogui.scroll(-random.choice(range(1, 7)))

                    else:
                        pyautogui.move(
                            random.choice(range(100, 200)),
                            random.choice(range(150, 250)),
                            1,
                            ease_method,
                        )

                    logger.debug(pyautogui.position())

            except pyautogui.FailSafeException:
                logger.debug("The mouse cursor was moved to one of the screen corners!")

                pyautogui.FAILSAFE = False

                logger.debug("Moving cursor to center...")
                pyautogui.moveTo(screen_width / 2, screen_height / 2)

    def set_browser_id(self, browser_id: Optional[int] = None) -> None:
        """Set browser id in stats if multiple browsers are used

        :type browser_id: int
        :param browser_id: Browser id to separate instances in log for multiprocess runs
        """

        self._stats.browser_id = browser_id

    def assign_android_device(self, device_id: str) -> None:
        """Assign Android device to browser

        :type device_id: str
        :param device_id: Android device ID to assign
        """

        logger.info(f"Assigning device[{device_id}] to browser {self._stats.browser_id}")

        self._android_device_id = device_id

    @staticmethod
    def _process_query(query: str) -> tuple[str, list[str]]:
        """Extract search query and filter words from the query input

        Query and filter words are splitted with "@" character. Multiple
        filter words can be used by separating with "#" character.

        e.g. wireless keyboard@amazon#ebay
             bluetooth headphones @ sony # amazon  #bose

        :type query: str
        :param query: Query string with optional filter words
        :rtype tuple
        :returns: Search query and list of filter words if any
        """

        search_query = query.split("@")[0].strip()

        filter_words = []

        if "@" in query:
            filter_words = [word.strip().lower() for word in query.split("@")[1].split("#")]

        if filter_words:
            logger.debug(f"Filter words: {filter_words}")

        return (search_query, filter_words)

    @property
    def stats(self) -> SearchStats:
        """Return search statistics data

        :rtype: SearchStats
        :returns: Search statistics data
        """

        return self._stats
