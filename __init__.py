"""
Facebook Events Scraper Module.

This module provides functionality to scrape events from Facebook pages
using Playwright for browser automation and BeautifulSoup for HTML parsing.
"""

import csv
import json
import logging
import asyncio
from pathlib import Path
from typing import Dict, List
from datetime import datetime, timedelta, timezone
from bs4 import BeautifulSoup
from playwright.async_api import async_playwright, Page

class FacebookEventScraper:
    """
    Facebook events scraper using Playwright.
    
    This class handles the entire scraping process including:
    - Browser automation with Playwright
    - HTML parsing with BeautifulSoup
    - Date conversion and standardization
    - Event data extraction and storage
    """
    
    # CSS Selectors for various Facebook elements
    SELECTORS = {
        'cookie_consent': '.x1i10hfl.xjbqb8w.x1ejq31n.xd10rxx.x1sy0etr.x17r0tee.x972fbf.xcfux6l.x1qhh985.xm0m39n.x1ypdohk.xe8uvvx.xdj266r.x11i5rnm.xat24cr.x1mh8g0r.xexx8yu.x4uap5.x18d9i69.xkhd6sd.x16tdsg8.x1hl2dhg.xggy1nq',
        'login_prompt': '.x1i10hfl.xjqpnuy.xa49m3k.xqeqjp1.x2hbi6w.x13fuv20.xu3j5b3.x1q0q8m5.x26u7qi.x1ypdohk.xdl72j9',
        'event': {
            'wrapper': '.x6s0dn4.x1lq5wgf.xgqcy7u.x30kzoy.x9jhf4c.x1olyfxc.x9f619.x78zum5.x1e56ztr.xyamay9.x1pi30zi.x1l90r2v.x1swvt13.x1gefphp',
            'link': 'a[href*="/events/"]',
            'date': '.x1lliihq.x6ikm8r.x10wlt62.x1n2onr6.xlyipyv.xuxw1ft',
            'title': '.html-span.xdj266r.x11i5rnm.xat24cr.x1mh8g0r.xexx8yu.x4uap5.x18d9i69.xkhd6sd.x1hl2dhg.x16tdsg8.x1vvkbs',
            'place_element': '.x1gslohp > div:first-child',
            'place_container': '.x1lliihq.x6ikm8r.x10wlt62.x1n2onr6',
            'date_element': '.x193iq5w.xeuugli.x13faqbe.x1vvkbs.x10flsy6.x1lliihq.x1s928wv.xhkezso.x1gmr53x.x1cpjm7i.x1fgarty.x1943h6x.x1tu3fi.x3x7a5m.x1nxh6w3.x1sibtaa.xo1l8bm.xzsf02u.x1yc453h',
        }
    }

    # Month name to number mapping
    MONTHS = {
        'Jan': 1, 'Feb': 2, 'Mar': 3, 'Apr': 4, 'May': 5, 'Jun': 6,
        'Jul': 7, 'Aug': 8, 'Sep': 9, 'Oct': 10, 'Nov': 11, 'Dec': 12
    }

    def __init__(self, csv_file: str) -> None:
        """
        Initialize the scraper.

        Args:
            csv_file (str): Path to CSV file containing Facebook page URLs
        """
        self.csv_file = Path(csv_file)
        self.logger = self._setup_logger()
        self.popups_dismissed = False
        self.processed_urls = set()

    async def scrape_events(self) -> None:
        """
        Main method to orchestrate the scraping process.
        
        This method:
        1. Reads URLs from CSV
        2. Initializes Playwright browser
        3. Processes URLs in batches
        4. Merges and saves results
        """
        urls = self._read_urls()
        self.logger.info(f"Starting to scrape {len(urls)} URLs")
        
        async with async_playwright() as p:
            browser = await p.chromium.launch(
                headless=True,
                args=[
                    '--disable-blink-features=AutomationControlled',
                    '--no-sandbox',
                    '--disable-setuid-sandbox',
                    '--disable-dev-shm-usage',
                    '--disable-gpu',
                    '--window-size=1920,1080',
                ]
            )
            
            context = await browser.new_context(
                user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36',
                viewport={'width': 1920, 'height': 1080},
                locale='en-US',
                timezone_id='Europe/Warsaw',
                permissions=['geolocation'],
                java_script_enabled=True,
            )

            # Add debug logging
            context.set_default_timeout(60000)
            page = await context.new_page()
            await page.route("**/*", lambda route: route.continue_())
            
            try:
                # Reduce batch size and increase timeouts
                batch_size = 3  # Reduced from 5
                results = []
                
                for i in range(0, len(urls), batch_size):
                    batch = urls[i:i + batch_size]
                    self.logger.info(f"Processing batch {i//batch_size + 1}/{len(urls)//batch_size + 1}")
                    
                    # Process each URL with individual error handling
                    batch_results = []
                    for url in batch:
                        try:
                            result = await self._scrape_page_with_retry(context, url)
                            batch_results.append(result)
                        except Exception as e:
                            self.logger.error(f"Failed to process {url}: {str(e)}")
                            batch_results.append({})
                    
                    results.extend(batch_results)
                    # Increased delay between batches
                    await asyncio.sleep(5)  # Increased from 2
                    
                events = self._merge_results(results)
                if not events:
                    self.logger.warning("No events were found!")
                else:
                    self.logger.info(f"Found {sum(len(e) for e in events.values())} events")
                self._save_events(events)
            finally:
                await context.close()
                await browser.close()

    async def _scrape_page_with_retry(self, context, url: str, max_retries: int = 3) -> Dict:
        """
        Attempt to scrape a page with exponential backoff retries.

        Args:
            context: Playwright browser context
            url (str): Target Facebook page URL
            max_retries (int): Maximum number of retry attempts

        Returns:
            Dict: Extracted events data or empty dict if failed
        """
        for attempt in range(max_retries):
            try:
                return await self._scrape_page(context, url)
            except Exception as e:
                self.logger.warning(f"Attempt {attempt + 1}/{max_retries} failed for {url}: {str(e)}")
                if attempt < max_retries - 1:
                    await asyncio.sleep(10 * (attempt + 1))  # Increased backoff time
                else:
                    self.logger.error(f"Failed to scrape {url} after {max_retries} attempts")
                    return {}

    async def _scrape_page(self, context, url: str) -> Dict:
        """Scrape events from a single page."""
        page = await context.new_page()
        try:
            self.logger.info(f"Processing: {url}")
            
            await page.goto(url, wait_until='networkidle', timeout=30000)
            await self._handle_popups(page)
            await page.wait_for_timeout(2000)
            
            try:
                # Look for event links directly
                event_titles = await page.query_selector_all(self.SELECTORS['event']['title'])
                if len(event_titles) > 0:
                    self.logger.info(f"Found {len(event_titles)} potential event titles on {url}")
                    
                    # Debug: Print first few titles
                    for i, title in enumerate(event_titles[:3]):
                        title_text = await title.text_content()
                        self.logger.debug(f"Sample title {i+1}: {title_text}")
                    
                    await self._scroll_page(page)
                else:
                    self.logger.warning(f"No event titles found on {url}")
                    return {}

            except Exception as e:
                self.logger.error(f"Error finding events: {str(e)}")
                return {}

            content = await page.content()
            self.logger.debug(f"Page content length: {len(content)} characters")
            events = self._parse_content(content, url)
            
            return events

        except Exception as e:
            self.logger.error(f"Error processing {url}: {str(e)}")
            return {}
        finally:
            await page.close()

    async def _handle_popups(self, page: Page) -> None:
        """Handle various popups that might appear."""
        try:
            # Increased timeout for popup handling
            timeout = 15000  # Increased from 10000
            
            # Handle cookie consent with force option
            try:
                cookie_button = await page.wait_for_selector(
                    self.SELECTORS['cookie_consent'],
                    state="attached",
                    timeout=timeout
                )
                if cookie_button:
                    await page.evaluate("""
                        (selector) => {
                            const elements = document.querySelectorAll(selector);
                            for (const el of elements) {
                                if (el.innerText.includes('Allow all cookies')) {
                                    el.click();
                                    return true;
                                }
                            }
                            return false;
                        }
                    """, self.SELECTORS['cookie_consent'])
                    self.logger.info("✓ Cookie consent clicked using JavaScript")
                    await page.wait_for_timeout(2000)
            except Exception as e:
                self.logger.warning(f"Cookie consent error: {str(e)}")

            # Handle login prompt with force option
            try:
                close_button = await page.wait_for_selector(
                    self.SELECTORS['login_prompt'],
                    state="attached",
                    timeout=timeout
                )
                if close_button:
                    await page.evaluate("""
                        (selector) => {
                            const elements = document.querySelectorAll(selector);
                            for (const el of elements) {
                                if (el.getAttribute('aria-label') === 'Close') {
                                    el.click();
                                    return true;
                                }
                            }
                            return false;
                        }
                    """, self.SELECTORS['login_prompt'])
                    self.logger.info("✓ Login prompt clicked using JavaScript")
                    await page.wait_for_timeout(2000)
            except Exception as e:
                self.logger.warning(f"Login prompt error: {str(e)}")
            
        except Exception as e:
            self.logger.error(f"Popup handling error: {str(e)}")

    async def _wait_for_content(self, page: Page) -> None:
        """Wait for the main content to load."""
        try:
            # Wait for event title elements to appear
            await page.wait_for_selector(self.SELECTORS['event']['title'], timeout=30000)
            event_titles = await page.query_selector_all(self.SELECTORS['event']['title'])
            if len(event_titles) > 0:
                self.logger.info(f"✓ Found {len(event_titles)} potential events")
            else:
                self.logger.info("No events found on page")
            
            await page.wait_for_timeout(2000)
            
        except Exception as e:
            self.logger.error(f"Content loading error: {str(e)}")
            raise

    async def _scroll_page(self, page: Page) -> None:
        """Scroll down the page to load all content."""
        try:
            last_event_count = 0
            no_new_events_count = 0
            max_no_new_events = 3  # Stop if no new events found after 3 scrolls
            
            for scroll in range(10):  # Maximum 10 scrolls
                await page.evaluate("window.scrollBy(0, 800)")
                await page.wait_for_timeout(1000)
                
                events = await page.query_selector_all(self.SELECTORS['event']['title'])
                current_count = len(events)
                
                if current_count == last_event_count:
                    no_new_events_count += 1
                    if no_new_events_count >= max_no_new_events:
                        self.logger.info(f"No new events found after {no_new_events_count} scrolls")
                        break
                else:
                    no_new_events_count = 0
                    
                last_event_count = current_count
                self.logger.debug(f"Found {current_count} events after scroll {scroll + 1}")
                
        except Exception as e:
            self.logger.debug(f"Scrolling error (non-critical): {str(e)}")

    def _merge_results(self, results: List[Dict]) -> Dict:
        """
        Merge events from multiple pages into a single dictionary, removing duplicates.
        
        Args:
            results: List of dictionaries containing events by date
        
        Returns:
            Dict: Merged events grouped by date with duplicates removed
        """
        merged = {}
        seen_events = set()  # Track unique events using title+date+link combination
        
        for result in results:
            for date, events in result.items():
                if date not in merged:
                    merged[date] = []
                
                for event in events:
                    # Create unique identifier for event
                    event_id = f"{event['event_title']}|{date}|{event['event_link']}"
                    
                    if event_id not in seen_events:
                        merged[date].append(event)
                        seen_events.add(event_id)
                        self.logger.debug(f"Added unique event: {event['event_title']} on {date}")
                    else:
                        self.logger.debug(f"Skipped duplicate event: {event['event_title']} on {date}")
        
        # Remove dates with empty event lists
        merged = {date: events for date, events in merged.items() if events}
        
        self.logger.info(f"Merged results: {len(seen_events)} unique events across {len(merged)} dates")
        return merged

    def _parse_content(self, content: str, url: str) -> Dict:
        """Parse HTML content using BeautifulSoup."""
        events = {}
        soup = BeautifulSoup(content, 'html.parser')
        
        # Find all event titles
        event_titles = soup.select(self.SELECTORS['event']['title'])
        self.logger.debug(f"BeautifulSoup found {len(event_titles)} event titles")
        
        events_found = 0
        events_skipped = 0
        
        for idx, title_element in enumerate(event_titles, 1):
            self.logger.debug(f"Processing event {idx}/{len(event_titles)} on {url}")
            
            parent = title_element.parent
            self.logger.debug(f"Parent HTML: {parent.prettify()[:200]}...")
            
            event_data = self._extract_event_data(parent)
            if event_data:
                # Create unique key using title + date instead of just URL
                event_key = f"{event_data['title']}_{event_data['date']}"
                
                if event_data['date'] not in events:
                    events[event_data['date']] = []
                
                # Add event even if title exists but date is different
                events[event_data['date']].append({
                    'event_title': event_data['title'],
                    'event_link': event_data['link'],
                    'event_place': event_data['place']
                })
                events_found += 1
                self.logger.info(f"✓ Found event #{events_found}: {event_data['title']} at {event_data['place']} on {event_data['date']}")
            else:
                self.logger.debug(f"Failed to extract data for event {idx}")

        self.logger.info(f"Page summary for {url}:")
        self.logger.info(f"- Total titles found: {len(event_titles)}")
        self.logger.info(f"- Successfully extracted: {events_found}")
        self.logger.info(f"- Skipped duplicates: {events_skipped}")
        self.logger.info(f"- Failed to extract: {len(event_titles) - events_found - events_skipped}")
        
        return events

    def _extract_event_data(self, container) -> Dict:
        """
        Extract event data from HTML container.

        Extracts the following information:
        - Event title
        - Event link/URL
        - Event date
        - Event location/place

        Args:
            container: BeautifulSoup element containing event information

        Returns:
            Dict: Event data or empty dict if extraction fails
        """
        try:
            # Get the root wrapper - going up to find the main event container
            root = container
            while root and (root.name != 'div' or 'x6s0dn4' not in root.get('class', [])):
                root = root.parent

            if not root:
                self.logger.debug("[ROOT] Could not find root container with class x6s0dn4")
                return {}

            # Find title - it's in a span with html-span and xdj266r classes
            title = None
            title_span = root.find('span', class_=lambda x: x and 'html-span' in x and 'xdj266r' in x)
            if title_span:
                title = title_span.text.strip()
                self.logger.debug(f"[TITLE] Found: '{title}'")
            else:
                self.logger.debug("[TITLE] No title element found")
                return {}

            # Find event link
            link = None
            link_element = root.find('a', href=lambda x: x and '/events/' in x)
            if link_element:
                link = self._clean_url(link_element['href'])
                self.logger.debug(f"[LINK] Found: {link}")
            else:
                self.logger.debug("[LINK] No event link found")
                return {}

            # Extract date - looking for specific span structure
            date = None
            date_span = root.find('span', class_=lambda x: x and 'x1lliihq' in x and 'xuxw1ft' in x)
            if date_span:
                raw_date = date_span.get_text(strip=True)
                self.logger.debug(f"[DATE] Raw text: '{raw_date}'")
                date = self._convert_date(raw_date)
                self.logger.debug(f"[DATE] Converted to: '{date}'")

            # Extract place - try both possible structures
            place = None
            # First try the primary structure with x1gslohp class
            place_div = root.find('div', class_='x1gslohp')
            if place_div:
                first_div = place_div.find('div')
                if first_div:
                    place_text = ''
                    for content in first_div.contents:
                        if isinstance(content, str):
                            place_text += content
                        elif content.name == 'span':
                            break
                    place = place_text.strip()
                    self.logger.debug(f"[PLACE] Found from primary structure: '{place}'")

            # If no place found, try alternative structure with link element
            if not place:
                place_link = root.find('a', class_=lambda x: x and all(cls in x for cls in [
                    'x1i10hfl', 'xjbqb8w', 'x1ejq31n', 'xd10rxx', 'x1sy0etr', 
                    'x17r0tee', 'x972fbf', 'xcfux6l', 'x1qhh985', 'xm0m39n', 
                    'x9f619', 'x1ypdohk', 'xt0psk2', 'xe8uvvx', 'xdj266r', 
                    'x11i5rnm', 'xat24cr', 'x1mh8g0r', 'xexx8yu', 'x4uap5', 
                    'x18d9i69', 'xkhd6sd', 'x16tdsg8', 'x1hl2dhg', 'xggy1nq',
                    'x1a2a7pz', 'xkrqix3', 'x1sur9pj', 'xi81zsa', 'x1s688f'
                ]))
                if place_link:
                    place = place_link.get_text(strip=True)
                    self.logger.debug(f"[PLACE] Found from alternative structure: '{place}'")

            if not place:
                place = "No location"
                self.logger.debug("[PLACE] Using default location - no structure matched")

            # Only return if we have essential data
            if title and link:
                event_data = {
                    'date': date or "Date TBD",
                    'link': link,
                    'title': title,
                    'place': place
                }
                self.logger.info(f"[EVENT] Extracted: {title} @ {place} on {date}")
                return event_data

            return {}

        except Exception as e:
            self.logger.debug(f"[ERROR] Extracting event data: {str(e)}")
            return {}

    def _clean_url(self, url: str) -> str:
        """Clean Facebook event URL."""
        if '?' in url:
            url = url.split('?')[0]
        if 'facebook.com' not in url:
            url = f"https://facebook.com{url}"
        return url

    def _convert_date(self, date_string: str) -> str:
        """
        Convert Facebook date string to standardized format.
        """
        try:
            if not date_string:
                return "Date TBD"

            self.logger.debug(f"[DATE] Converting: '{date_string}'")
            date_string = date_string.strip().lower()

            # Get current time in Warsaw timezone (UTC+1)
            warsaw_tz = datetime.now(timezone(timedelta(hours=1)))
            current_year = warsaw_tz.year
            today = warsaw_tz.date()

            # Handle special cases (happening now, today, tomorrow)
            if "happening now" in date_string:
                result = today.strftime("%d/%m/%Y")
                self.logger.debug(f"[DATE] Happening now -> {result}")
                return result
            if "today" in date_string:
                result = today.strftime("%d/%m/%Y")
                self.logger.debug(f"[DATE] Today -> {result}")
                return result
            if "tomorrow" in date_string:
                result = (today + timedelta(days=1)).strftime("%d/%m/%Y")
                self.logger.debug(f"[DATE] Tomorrow -> {result}")
                return result

            # Parse standard date format: "Fri, Mar 15 at 8:00 PM CET"
            try:
                # Remove time portion and clean up
                date_part = date_string.split(" at ")[0]
                if ',' in date_part:
                    date_part = date_part.split(',')[1].strip()

                # Parse "Mar 15" format
                parts = date_part.split()
                if len(parts) >= 2:
                    month = parts[0][:3].title()  # Capitalize first three letters
                    day = int(parts[1])
                    
                    if month in self.MONTHS:
                        month_num = self.MONTHS[month]
                        
                        # Determine year based on date
                        event_date = datetime(current_year, month_num, day)
                        if event_date.date() < today:
                            # If event date is in the past, it's probably next year
                            event_date = datetime(current_year + 1, month_num, day)
                        
                        result = event_date.strftime("%d/%m/%Y")
                        self.logger.debug(f"[DATE] Successfully converted to: {result}")
                        return result

                self.logger.debug(f"[DATE] Failed to parse parts: {parts}")
            except Exception as e:
                self.logger.debug(f"[DATE] Error parsing standard format: {str(e)}")

            return "Date TBD"

        except Exception as e:
            self.logger.debug(f"[DATE] Conversion error: {str(e)}")
            return "Date TBD"

    def _setup_logger(self) -> logging.Logger:
        """Setup logger for the scraper."""
        logger = logging.getLogger(__name__)
        handler = logging.StreamHandler()
        formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')
        handler.setFormatter(formatter)
        logger.addHandler(handler)
        logger.setLevel(logging.DEBUG)  # Changed to DEBUG to see more details
        return logger

    def _read_urls(self) -> List[str]:
        """Read URLs from CSV file."""
        urls = []
        with open(self.csv_file, "r") as csvfile:
            reader = csv.reader(csvfile)
            next(reader)
            for row in reader:
                urls.extend(row)
        return urls

    async def _dismiss_popups(self, page: Page) -> None:
        """Dismiss popups on the page."""
        if not self.popups_dismissed:
            try:
                await page.click(self.SELECTORS['cookie_consent'])
            except:
                self.logger.warning("Cookie consent popup not found")
            self.popups_dismissed = True
        try:
            await page.click(self.SELECTORS['login_prompt'])
        except:
            self.logger.warning("Login prompt popup not found")

    def _save_events(self, events: Dict) -> None:
        """
        Save events to JSON file with proper date sorting.
        """
        # Convert string dates to datetime objects for proper sorting
        events_with_dates = {
            (datetime.strptime(date, "%d/%m/%Y") if date != "Date TBD" else datetime.max): events
            for date, events in events.items()
        }
        
        # Sort by date
        sorted_events = dict(sorted(events_with_dates.items()))
        
        # Convert back to string format
        sorted_events_str = {
            key.strftime("%d/%m/%Y") if key != datetime.max else "Date TBD": value
            for key, value in sorted_events.items()
        }
        
        # Save to file
        with open("events_data.json", "w", encoding="utf-8") as output:
            json.dump(sorted_events_str, output, ensure_ascii=False, indent=4)

    def _convert_to_date(self, date_str: str) -> datetime:
        """Convert date string to datetime object."""
        try:
            return datetime.strptime(date_str, '%d/%m/%y')
        except ValueError:
            return None

    async def run(self):
        """Entry point for the scraper."""
        await self.scrape_events()

if __name__ == "__main__":
    scraper = FacebookEventScraper("my_liked_pages.csv")
    asyncio.run(scraper.run())