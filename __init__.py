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
    
    # Updated CSS Selectors based on current Facebook structure
    SELECTORS = {
        'cookie_consent': 'button[data-cookiebanner="accept_button"]',
        'login_prompt': '[aria-label="Close"]',
        'event': {
            # More flexible event container selector
            'container': 'div[class*="x9f619"]',
            'event_link': 'a[href*="/events/"]',
            # Updated selectors based on actual HTML structure
            'date_container': '.xu06os2.x1ok221b',
            'date_text': '.x1lliihq.x6ikm8r.x10wlt62.x1n2onr6',
            'title_span': 'span.html-span',
            'location_container': '.x1gslohp > div:first-child'
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
                    
                    batch_results = []
                    for url in batch:
                        try:
                            result = await self._scrape_page_with_retry(context, url)
                            batch_results.append(result)
                        except Exception as e:
                            self.logger.error(f"Failed to process {url}: {str(e)}")
                            batch_results.append({})
                    
                    results.extend(batch_results)
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
                    return {}

    async def _scrape_page(self, context, url: str) -> Dict:
        """Scrape events from a single page."""
        page = await context.new_page()
        try:
            self.logger.info(f"Processing: {url}")
            
            await page.goto(url, wait_until='networkidle', timeout=30000)
            await self._handle_popups(page)
            await page.wait_for_timeout(3000)
            
            # Look for event links first (more reliable)
            event_links = await page.query_selector_all(self.SELECTORS['event']['event_link'])
            
            if event_links:
                self.logger.info(f"Found {len(event_links)} event links on {url}")
                await self._scroll_page(page)
            else:
                self.logger.warning(f"No event links found on {url}")
                return {}

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

    async def _scroll_page(self, page: Page) -> None:
        """Scroll down the page to load all content."""
        try:
            last_event_count = 0
            no_new_events_count = 0
            max_no_new_events = 3
            
            for scroll in range(10):
                await page.evaluate("window.scrollBy(0, 800)")
                await page.wait_for_timeout(1000)
                
                events = await page.query_selector_all(self.SELECTORS['event']['event_link'])
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
                        self.logger.debug(f"Added unique event: {event['event_title']} on {date}")
                    else:
                        self.logger.debug(f"Skipped duplicate event: {event['event_title']} on {date}")
        
        merged = {date: events for date, events in merged.items() if events}
        
        self.logger.info(f"Merged results: {len(seen_events)} unique events across {len(merged)} dates")
        return merged

    def _parse_content(self, content: str, url: str) -> Dict:
        """Parse HTML content using BeautifulSoup with updated selectors."""
        events = {}
        soup = BeautifulSoup(content, 'html.parser')
        
        # Find all event links first
        event_links = soup.select(self.SELECTORS['event']['event_link'])
        self.logger.info(f"Found {len(event_links)} event links in HTML")
        
        for link in event_links:
            try:
                event_data = self._extract_event_data_updated(link)
                if event_data and event_data.get('date') and event_data['date'] != "Date TBD":
                    if event_data['date'] not in events:
                        events[event_data['date']] = []
                    events[event_data['date']].append({
                        'event_title': event_data['title'],
                        'event_link': event_data['link'],
                        'event_place': event_data['place']
                    })
                    self.logger.debug(f"Extracted event: {event_data['title']} at {event_data['place']}")
            except Exception as e:
                self.logger.debug(f"Error extracting event data: {str(e)}")
                continue
        
        self.logger.info(f"Successfully extracted {sum(len(e) for e in events.values())} events")
        return events

    def _extract_event_data_updated(self, link_element) -> Dict:
        """
        Extract event data from the event link element and its parent container.
        """
        try:
            # Get the event URL
            event_url = self._clean_url(link_element.get('href', ''))
            if not event_url:
                return {}

            # Get the title from the link's span
            title_span = link_element.select_one(self.SELECTORS['event']['title_span'])
            title = title_span.get_text(strip=True) if title_span else None
            
            if not title:
                # Fallback: try to get any text from the link
                title = link_element.get_text(strip=True)

            # Find the parent container that holds all event information
            # Navigate up to find the main event container
            container = link_element
            for _ in range(10):  # Limit traversal depth
                container = container.parent
                if not container:
                    break
                # Look for the characteristic event container classes
                if container.get('class') and any('x9f619' in str(cls) for cls in container.get('class', [])):
                    break

            if not container:
                return {}

            # Extract date - look for date patterns in the container
            date = self._extract_date_from_container(container)
            
            # Extract location - look for location container
            place = self._extract_place_from_container(container)

            if title and event_url and date and date != "Date TBD":
                return {
                    'title': title,
                    'link': event_url,
                    'date': date,
                    'place': place or "No location"
                }

            return {}

        except Exception as e:
            self.logger.debug(f"Error in updated extraction: {str(e)}")
            return {}

    def _extract_date_from_container(self, container) -> str:
        """Extract date from event container."""
        try:
            # Look for date patterns in span elements
            date_spans = container.select('span')
            for span in date_spans:
                text = span.get_text(strip=True)
                # Look for date patterns like "Tue, Jun 17 at 7 PM"
                if any(pattern in text.lower() for pattern in ['at ', 'pm', 'am', 'mon,', 'tue,', 'wed,', 'thu,', 'fri,', 'sat,', 'sun,']):
                    date = self._convert_date(text)
                    if date != "Date TBD":
                        return date
            
            return "Date TBD"
        except Exception as e:
            self.logger.debug(f"Date extraction error: {str(e)}")
            return "Date TBD"

    def _extract_place_from_container(self, container) -> str:
        """Extract location from event container."""
        try:
            # Look for location container
            location_div = container.select_one(self.SELECTORS['event']['location_container'])
            if location_div:
                location_text = location_div.get_text(strip=True)
                # Clean up location text (remove "Event by" and other metadata)
                if 'Event by' in location_text:
                    location_text = location_text.split('Event by')[0].strip()
                if location_text and location_text not in ['See more', 'Show map']:
                    return location_text
            
            return "No location"
        except Exception as e:
            self.logger.debug(f"Location extraction error: {str(e)}")
            return "No location"

    def _clean_url(self, url: str) -> str:
        """Clean Facebook event URL."""
        if not url:
            return ""
        if '?' in url:
            url = url.split('?')[0]
        if 'facebook.com' not in url and url.startswith('/'):
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

            # Handle special cases
            if "happening now" in date_string:
                return today.strftime("%d/%m/%Y")
            if "today" in date_string:
                return today.strftime("%d/%m/%Y")
            if "tomorrow" in date_string:
                return (today + timedelta(days=1)).strftime("%d/%m/%Y")

            # Parse standard format: "Tue, Jun 17 at 7 PM" or "Jun 17 at 7 PM"
            try:
                # Remove time portion and clean up
                date_part = date_string.split(" at ")[0]
                if ',' in date_part:
                    date_part = date_part.split(',')[1].strip()

                # Parse "Jun 17" format
                parts = date_part.split()
                if len(parts) >= 2:
                    month = parts[0][:3].title()
                    day = int(parts[1])
                    
                    if month in self.MONTHS:
                        month_num = self.MONTHS[month]
                        
                        # Determine year
                        event_date = datetime(current_year, month_num, day)
                        if event_date.date() < today:
                            event_date = datetime(current_year + 1, month_num, day)
                        
                        result = event_date.strftime("%d/%m/%Y")
                        self.logger.debug(f"[DATE] Successfully converted to: {result}")
                        return result

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
        logger.setLevel(logging.DEBUG)
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

    async def run(self):
        """Entry point for the scraper."""
        await self.scrape_events()

if __name__ == "__main__":
    scraper = FacebookEventScraper("my_liked_pages.csv")
    asyncio.run(scraper.run())
