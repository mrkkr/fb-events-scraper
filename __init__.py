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
        'cookie_consent': '.x1i10hfl.xjqpnuy.xa49m3k.xqeqjp1.x2hbi6w.x13fuv20.xu3j5b3.x1q0q8m5.x26u7qi.x972fbf.xcfux6l.x1qhh985.xm0m39n.x9f619.x78zum5.xl56j7k',
        'login_prompt': '.x1i10hfl.xjqpnuy.xa49m3k.xqeqjp1.x2hbi6w.x13fuv20.xu3j5b3.x1q0q8m5.x26u7qi.x972fbf.xcfux6l.x1qhh985.xm0m39n.x9f619.x78zum5.xl56j7k',
        'event': {
            'wrapper': '.x6s0dn4.x1lq5wgf.xgqcy7u.x30kzoy.x9jhf4c.x1olyfxc.x9f619.x78zum5.x1e56ztr.xyamay9.x1pi30zi.x1l90r2v.x1swvt13.x1gefphp',
            'date': '.x1lliihq.x6ikm8r.x10wlt62.x1n2onr6.xlyipyv.xuxw1ft',
            'title': '.html-span.xdj266r.x11i5rnm.xat24cr.x1mh8g0r.xexx8yu.x4uap5.x18d9i69.xkhd6sd.x1hl2dhg.x16tdsg8.x1vvkbs',
            'date_element': '.x193iq5w.xeuugli.x13faqbe.x1vvkbs.x10flsy6.x1lliihq.x1s928wv.xhkezso.x1gmr53x.x1cpjm7i.x1fgarty.x1943h6x.x1tu3fi.x3x7a5m.x1nxh6w3.x1sibtaa.xo1l8bm.xzsf02u.x1yc453h',
            'place_container': '.x1lliihq.x6ikm8r.x10wlt62.x1n2onr6',
            'link': 'a[href*="/events/"]',
            'place_element': '.x1gslohp > div:first-child'
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
            # Handle cookie consent
            await page.evaluate("""
                () => {
                    const buttons = Array.from(document.querySelectorAll('button'));
                    const clickButton = (text) => {
                        for (const btn of buttons) {
                            if (btn.textContent.toLowerCase().includes(text)) {
                                btn.click();
                                return true;
                            }
                        }
                        return false;
                    };
                    
                    return clickButton('accept') || clickButton('allow') || clickButton('continue');
                }
            """)
            
            await page.wait_for_timeout(2000)
            
            # Handle login prompt
            await page.evaluate("""
                () => {
                    const buttons = Array.from(document.querySelectorAll('button, [role="button"]'));
                    const closeButton = buttons.find(btn => 
                        btn.getAttribute('aria-label') === 'Close' || 
                        btn.textContent.includes('Not Now')
                    );
                    if (closeButton) {
                        closeButton.click();
                        return true;
                    }
                    return false;
                }
            """)
            
            self.logger.info("✓ Popup handling complete")
            
        except Exception as e:
            self.logger.warning(f"Popup handling error: {str(e)}")
            # Continue execution even if popup handling fails

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
        
        # Find all containers that might have events
        event_containers = []
        for link in soup.select(self.SELECTORS['event']['link']):
            container = link
            depth = 0
            # Look up the DOM tree for event container
            while container and depth < 5:
                if container.name == 'div' and container.get('class'):
                    classes = ' '.join(container.get('class', []))
                    if 'x6s0dn4' in classes and 'x1lq5wgf' in classes:
                        # Verify it has a title and place elements
                        if (container.select_one(self.SELECTORS['event']['title']) and 
                            container.select_one('.x1gslohp')):
                            event_containers.append(container)
                            break
                container = container.parent
                depth += 1
        
        self.logger.info(f"Found {len(event_containers)} potential event containers")
        
        for container in event_containers:
            event_data = self._extract_event_data(container)
            if event_data and event_data.get('date') != "Date TBD":
                if event_data['date'] not in events:
                    events[event_data['date']] = []
                events[event_data['date']].append({
                    'event_title': event_data['title'],
                    'event_link': event_data['link'],
                    'event_place': event_data['place']
                })
                self.logger.debug(f"Extracted event: {event_data['title']} at {event_data['place']}")
        
        self.logger.info(f"Successfully extracted {sum(len(e) for e in events.values())} events")
        return events

    def _extract_event_data(self, container) -> Dict:
        """Extract event data from HTML container."""
        try:
            # Get link first
            link_element = container.select_one(self.SELECTORS['event']['link'])
            if not link_element:
                return {}
            link = self._clean_url(link_element['href'])

            # Find title - must match ALL classes
            title = None
            title_elements = container.select('.html-span')  # Looking specifically for html-span elements
            for element in title_elements:
                if element.get('class') and all(cls in element.get('class', []) for cls in [
                    'xdj266r', 'x11i5rnm', 'xat24cr', 'x1mh8g0r', 'xexx8yu', 'x4uap5', 
                    'x18d9i69', 'xkhd6sd', 'x1hl2dhg', 'x16tdsg8', 'x1vvkbs'
                ]):
                    title = element.get_text(strip=True)
                    break

            # Find date - using x1yc453h class as unique identifier
            date = None
            date_elements = container.select('.x1yc453h')  # Using unique class as anchor
            for element in date_elements:
                if element.get('class') and 'xzsf02u' in element.get('class', []):
                    date_text = element.get_text(strip=True)
                    date = self._convert_date(date_text)
                    if date != "Date TBD":
                        break

            # Find place - using exact structure
            place = None
            place_container = container.find('div', class_='x1gslohp')
            if place_container:
                # Get first div child that isn't a date element
                place_element = place_container.find('div', recursive=False)
                if place_element and not any(cls in place_element.get('class', []) for cls in ['xzsf02u', 'x1yc453h']):
                    place = place_element.get_text(strip=True)
                    if place and place not in ['See more', 'Show map']:
                        self.logger.debug(f"Found place: {place}")

            # Create event data if we have the minimum required information
            if title and link and date and date != "Date TBD":
                result = {
                    'date': date,
                    'link': link,
                    'title': title,
                    'place': place or "No location"
                }
                self.logger.debug(f"Successfully extracted event: {title} on {date}")
                return result
            else:
                self.logger.debug(f"Skipping event due to missing data: title={bool(title)}, link={bool(link)}, valid_date={bool(date and date != 'Date TBD')}")

            return {}

        except Exception as e:
            self.logger.error(f"Error extracting event data: {str(e)}")
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