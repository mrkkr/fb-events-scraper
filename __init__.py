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
    
    # --- UPDATED SELECTORS based on the actual HTML structure ---
    SELECTORS = {
        'cookie_consent': 'button[data-cookiebanner="accept_button"]',
        'login_prompt': '[aria-label="Close"]',
        'event': {
            # FIXED: Updated container selector to match the actual HTML structure
            'container': 'div.x9f619.x1n2onr6.x1ja2u2z.x78zum5.xdt5ytf.x193iq5w.xeuugli.x1r8uery.x1iyjqo2.xs83m0k.x1icxu4v.x25sj25.x10b6aqq.x1yrsyyn',
            # Alternative: More flexible container selector (finds any div containing an event link)
            'container_fallback': 'div:has(a[href*="/events/"])',
            'event_link': 'a[href*="/events/"]',
            # Selectors relative to the container (these look correct based on your HTML)
            'title_span': 'span.html-span',
            'date_text': 'div.xu06os2 span.x1lliihq',
            'location_container': 'div.x1gslohp'
        }
    }

    # Month name to number mapping
    MONTHS = {
        'Jan': 1, 'Feb': 2, 'Mar': 3, 'Apr': 4, 'May': 5, 'Jun': 6,
        'Jul': 7, 'Aug': 8, 'Sep': 9, 'Oct': 10, 'Nov': 11, 'Dec': 12
    }

    def __init__(self, csv_file: str, categories_csv: str = "page_categories.csv") -> None:
        """
        Initialize the scraper.

        Args:
            csv_file (str): Path to CSV file containing Facebook page URLs
            categories_csv (str): Path to CSV file containing Facebook page links and categories
        """
        self.csv_file = Path(csv_file)
        self.categories_csv = Path(categories_csv)
        self.logger = self._setup_logger()
        self.popups_dismissed = False
        self.processed_urls = set()
        self.page_to_categories = self._load_page_categories()

    def _load_page_categories(self) -> dict:
        """Load mapping from fb_page_link to list of categories from page_categories.csv."""
        mapping = {}
        try:
            with open(self.categories_csv, encoding="utf-8") as f:
                reader = csv.DictReader(f)
                for row in reader:
                    if 'fb_page_link' in row and 'category' in row:
                        page_url = row['fb_page_link'].replace('www.', '').replace('web.', '').rstrip('/')
                        categories = [cat.strip() for cat in row['category'].strip('"').split(',')]
                        mapping[page_url] = categories
            self.logger.info(f"Loaded {len(mapping)} page-category mappings")
        except Exception as e:
            self.logger.error(f"Could not load page_categories.csv: {e}")
        return mapping

    def _get_categories_for_url(self, url: str) -> list:
        """Get categories for a given URL, normalizing the URL first."""
        normalized_url = url.replace('www.', '').replace('web.', '').rstrip('/')
        categories = self.page_to_categories.get(normalized_url, [])
        if not categories:
            self.logger.warning(f"No categories found for normalized URL: {normalized_url}")
        return categories

    async def scrape_events(self) -> None:
        """
        Main method to orchestrate the scraping process.
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

            context.set_default_timeout(60000)
            
            try:
                batch_size = 3
                results = []
                
                for i in range(0, len(urls), batch_size):
                    batch = urls[i:i + batch_size]
                    self.logger.info(f"Processing batch {i//batch_size + 1}/{len(urls)//batch_size + 1}")
                    
                    tasks = [self._scrape_page_with_retry(context, url) for url in batch]
                    batch_results = await asyncio.gather(*tasks, return_exceptions=True)
                    
                    for result in batch_results:
                        if isinstance(result, Exception):
                            self.logger.error(f"A task in the batch failed: {result}")
                        else:
                            results.append(result)
                    
                    await asyncio.sleep(5)
                    
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
        """
        for attempt in range(max_retries):
            try:
                return await self._scrape_page(context, url)
            except Exception as e:
                self.logger.warning(f"Attempt {attempt + 1}/{max_retries} failed for {url}: {str(e)}")
                if attempt < max_retries - 1:
                    await asyncio.sleep(10 * (attempt + 1))
                else:
                    self.logger.error(f"Failed to scrape {url} after {max_retries} attempts")
                    raise e

    async def _scrape_page(self, context, url: str) -> Dict:
        """Scrape events from a single page."""
        page = await context.new_page()
        try:
            self.logger.info(f"Processing: {url}")
            await page.goto(url, wait_until='domcontentloaded', timeout=45000)
            await self._handle_popups(page)
            await page.wait_for_timeout(3000)
            
            await self._scroll_page(page)

            content = await page.content()
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
            cookie_button = page.locator(self.SELECTORS['cookie_consent'])
            if await cookie_button.count() > 0:
                await cookie_button.first.click(timeout=5000)
                self.logger.info("Clicked cookie consent button.")
                await page.wait_for_timeout(1000)
        except Exception:
            self.logger.debug("Cookie consent button not found or could not be clicked.")

        try:
            close_button = page.locator(self.SELECTORS['login_prompt'])
            if await close_button.count() > 0:
                await close_button.first.click(timeout=5000)
                self.logger.info("Closed login prompt.")
        except Exception:
            self.logger.debug("Login prompt not found or could not be closed.")

    async def _scroll_page(self, page: Page) -> None:
        """Scroll down the page to load all content."""
        for _ in range(10):  # Scroll 10 times to load more events
            await page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
            await page.wait_for_timeout(2000) # Wait for content to load

    def _merge_results(self, results: List[Dict]) -> Dict:
        """
        Merge events from multiple pages into a single dictionary, removing duplicates.
        """
        merged = {}
        seen_events = set()
        
        for result in results:
            for date, events in result.items():
                if date not in merged:
                    merged[date] = []
                
                for event in events:
                    event_id = f"{event['event_title']}|{date}|{event['event_link']}"
                    
                    if event_id not in seen_events:
                        merged[date].append(event)
                        seen_events.add(event_id)
                    else:
                        self.logger.debug(f"Skipped duplicate event: {event['event_title']} on {date}")
        
        merged = {date: events for date, events in merged.items() if events}
        self.logger.info(f"Merged results: {len(seen_events)} unique events across {len(merged)} dates")
        return merged

    # --- UPDATED PARSING LOGIC with more robust container detection ---
    def _parse_content(self, content: str, url: str) -> Dict:
        """Parse HTML content by finding event containers and extracting data from them."""
        events = {}
        soup = BeautifulSoup(content, 'html.parser')
        
        # Try the primary container selector first
        event_containers = soup.select(self.SELECTORS['event']['container'])
        
        # If primary selector fails, try fallback approach
        if not event_containers:
            self.logger.warning(f"Primary container selector found 0 containers, trying fallback approach for {url}")
            # Find all divs that contain event links as a fallback
            all_event_links = soup.select(self.SELECTORS['event']['event_link'])
            event_containers = []
            for link in all_event_links:
                # Find the parent container (traverse up to find a suitable parent)
                container = link
                for _ in range(10):  # Limit traversal depth
                    container = container.parent
                    if not container:
                        break
                    # Look for a div that has the structural elements we need
                    if (container.name == 'div' and 
                        container.select_one('div.xu06os2') and  # Has date structure
                        container.select_one('span.html-span')):  # Has title structure
                        event_containers.append(container)
                        break
        
        self.logger.info(f"Found {len(event_containers)} event containers on {url}")
        
        # Get categories for the current page URL
        page_categories = self._get_categories_for_url(url)
        
        for container in event_containers:
            try:
                event_data = self._extract_event_data(container)
                if event_data and event_data.get('date') != "Date TBD":
                    date = event_data['date']
                    if date not in events:
                        events[date] = []
                    
                    # Add categories to the event data
                    event_data['event_categories'] = page_categories
                    events[date].append(event_data)
                    self.logger.debug(f"Extracted: '{event_data['event_title']}' on {date} with categories {page_categories}")

            except Exception as e:
                self.logger.debug(f"Could not extract data from a container: {str(e)}")
                continue
        
        self.logger.info(f"Successfully extracted {sum(len(e) for e in events.values())} valid events from {url}")
        return events

    def _extract_event_data(self, container) -> Dict:
        """
        Extracts single event data from its container block.
        This is a more robust method than the previous implementation.
        """
        if not container:
            return {}

        # Find the link
        link_tag = container.select_one(self.SELECTORS['event']['event_link'])
        event_url = self._clean_url(link_tag.get('href', '')) if link_tag else None
        if not event_url:
            return {}

        # Find the title
        title_tag = container.select_one(self.SELECTORS['event']['title_span'])
        title = title_tag.get_text(strip=True) if title_tag else "No Title"

        # Find the date
        date_tag = container.select_one(self.SELECTORS['event']['date_text'])
        date_str = date_tag.get_text(strip=True) if date_tag else None
        date = self._convert_date(date_str)

        # Find the location/place - Updated extraction logic
        place = "No location"
        place_tag = container.select_one(self.SELECTORS['event']['location_container'])
        if place_tag:
            # Get the first div inside x1gslohp which contains the venue info
            venue_div = place_tag.select_one('div')
            if venue_div:
                # Extract just the venue name (before any spans or "Event by" text)
                venue_text = venue_div.get_text(strip=True)
                # Clean up - remove "Event by" part and everything after
                if 'Event by' in venue_text:
                    place = venue_text.split('Event by')[0].strip()
                else:
                    # Take only the part before the first span (which usually contains separators)
                    place = venue_text.split('·')[0].strip() if '·' in venue_text else venue_text

        return {
            'event_title': title,
            'event_link': event_url,
            'date': date,
            'event_place': place,
        }

    def _clean_url(self, url: str) -> str:
        """Clean Facebook event URL."""
        if not url:
            return ""
        if '?' in url:
            url = url.split('?')[0]
        if not url.startswith('http'):
            url = f"https://www.facebook.com{url}"
        return url

    def _convert_date(self, date_string: str) -> str:
        """
        Convert Facebook date string to standardized format.
        Updated to handle the actual date format from your HTML: "Mon, Oct 13 at 6:00 PM CEST"
        """
        if not date_string:
            return "Date TBD"

        self.logger.debug(f"[DATE] Converting: '{date_string}'")
        original_date_string = date_string
        date_string = date_string.lower()

        warsaw_tz = timezone(timedelta(hours=1))  # CET (update for CEST when needed)
        now = datetime.now(warsaw_tz)
        today = now.date()

        if "happening now" in date_string or "today" in date_string:
            return today.strftime("%d/%m/%Y")
        if "tomorrow" in date_string:
            return (today + timedelta(days=1)).strftime("%d/%m/%Y")

        try:
            # Handle the format: "Mon, Oct 13 at 6:00 PM CEST"
            date_part = date_string.split(" at ")[0].strip()
            if ',' in date_part:
                date_part = date_part.split(',')[1].strip()

            parts = date_part.split()
            if len(parts) >= 2:
                month_str = parts[0][:3].title()
                try:
                    day = int(parts[1])
                except ValueError:
                    self.logger.debug(f"[DATE] Could not parse day from '{parts[1]}'")
                    return "Date TBD"
                
                month = self.MONTHS.get(month_str)

                if month:
                    # Determine the year
                    event_date_this_year = datetime(now.year, month, day).date()
                    if event_date_this_year < today:
                        # If the date has passed this year, assume it's next year
                        result = datetime(now.year + 1, month, day).strftime("%d/%m/%Y")
                    else:
                        result = event_date_this_year.strftime("%d/%m/%Y")
                    
                    self.logger.debug(f"[DATE] Successfully converted '{original_date_string}' to {result}")
                    return result

        except Exception as e:
            self.logger.debug(f"[DATE] Could not parse date '{original_date_string}': {e}")

        return "Date TBD"

    def _setup_logger(self) -> logging.Logger:
        """Setup logger for the scraper."""
        logger = logging.getLogger(__name__)
        if not logger.handlers:
            handler = logging.StreamHandler()
            formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')
            handler.setFormatter(formatter)
            logger.addHandler(handler)
            logger.setLevel(logging.INFO) # Change to DEBUG for more verbosity
        return logger

    def _read_urls(self) -> List[str]:
        """Read only URLs from the first column of the CSV file."""
        urls = []
        with open(self.csv_file, "r", encoding="utf-8") as csvfile:
            reader = csv.reader(csvfile)
            next(reader) # Skip header
            for row in reader:
                if row and row[0].startswith("http"):
                    urls.append(row[0])
        return list(set(urls)) # Return unique URLs

    def _save_events(self, events: Dict) -> None:
        """Save events to JSON file with proper date sorting."""
        events_with_dates = {
            (datetime.strptime(date, "%d/%m/%Y") if date != "Date TBD" else datetime.max): event_list
            for date, event_list in events.items()
        }
        
        sorted_events = dict(sorted(events_with_dates.items()))
        
        sorted_events_str = {
            key.strftime("%d/%m/%Y") if key != datetime.max else "Date TBD": value
            for key, value in sorted_events.items()
        }
        
        with open("events_data.json", "w", encoding="utf-8") as output:
            json.dump(sorted_events_str, output, ensure_ascii=False, indent=4)
            self.logger.info("Successfully saved sorted events to events_data.json")

    async def run(self):
        """Entry point for the scraper."""
        await self.scrape_events()

if __name__ == "__main__":
    scraper = FacebookEventScraper("page_categories.csv", "page_categories.csv")
    asyncio.run(scraper.run())
