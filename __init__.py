"""
Facebook Events Scraper Module - Fixed Version
Resilient scraping without XPath dependencies.
"""

import csv
import json
import logging
import asyncio
from pathlib import Path
from typing import Dict, List, Optional, Set
from datetime import datetime, timedelta, timezone
from dataclasses import dataclass, asdict
from bs4 import BeautifulSoup
from playwright.async_api import async_playwright, Page, BrowserContext


@dataclass
class EventData:
    """Data class for event information."""
    event_title: str
    event_link: str
    date: str
    event_place: str
    event_categories: List[str]
    
    def to_dict(self) -> dict:
        return asdict(self)


class ResilientSelectors:
    """
    Multiple selector strategies for finding elements regardless of CSS changes.
    """
    
    # Cookie consent - multiple strategies
    COOKIE_SELECTORS = [
        'button[data-cookiebanner="accept_button"]',
        'button:has-text("Accept")',
        'button:has-text("Allow")',
        '[aria-label*="Accept"]',
        '[aria-label*="cookies"]',
    ]
    
    # Login popup - multiple strategies
    LOGIN_CLOSE_SELECTORS = [
        '[aria-label="Close"]',
        'div[role="dialog"] button:has-text("Close")',
        'div[role="dialog"] [aria-label*="close" i]',
        'button:has-text("Not Now")',
    ]


class FacebookEventScraper:
    """
    Modernized Facebook events scraper with resilient selectors.
    """
    
    MONTHS = {
        'jan': 1, 'feb': 2, 'mar': 3, 'apr': 4, 'may': 5, 'jun': 6,
        'jul': 7, 'aug': 8, 'sep': 9, 'oct': 10, 'nov': 11, 'dec': 12
    }
    
    def __init__(
        self, 
        csv_file: str, 
        max_concurrent: int = 3,
        enable_resource_blocking: bool = True
    ) -> None:
        """
        Initialize the scraper.
        
        Args:
            csv_file: Path to CSV file containing Facebook page URLs and categories
            max_concurrent: Maximum concurrent page scraping operations
            enable_resource_blocking: Block unnecessary resources for performance
        """
        self.csv_file = Path(csv_file)
        self.max_concurrent = max_concurrent
        self.enable_resource_blocking = enable_resource_blocking
        self.logger = self._setup_logger()
        self.page_to_categories = self._load_page_categories()
        self.selectors = ResilientSelectors()
        
    def _setup_logger(self) -> logging.Logger:
        """Setup structured logger."""
        logger = logging.getLogger(__name__)
        if not logger.handlers:
            handler = logging.StreamHandler()
            formatter = logging.Formatter(
                '%(asctime)s - %(name)s - %(levelname)s - %(message)s',
                datefmt='%Y-%m-%d %H:%M:%S'
            )
            handler.setFormatter(formatter)
            logger.addHandler(handler)
            logger.setLevel(logging.INFO)
        return logger
    
    def _load_page_categories(self) -> Dict[str, List[str]]:
        """Load page-category mappings from CSV with fb_page_link and category columns."""
        mapping = {}
        try:
            if not self.csv_file.exists():
                self.logger.warning(f"CSV file not found: {self.csv_file}")
                return mapping
                
            with open(self.csv_file, encoding="utf-8") as f:
                reader = csv.DictReader(f)
                for row in reader:
                    if 'fb_page_link' in row and 'category' in row:
                        page_url = self._normalize_url(row['fb_page_link'])
                        # Handle both single and comma-separated categories
                        category_str = row['category'].strip('"').strip()
                        if category_str:
                            categories = [cat.strip() for cat in category_str.split(',')]
                            mapping[page_url] = categories
            self.logger.info(f"Loaded {len(mapping)} page-category mappings")
        except Exception as e:
            self.logger.error(f"Error loading categories: {e}")
        return mapping
    
    def _normalize_url(self, url: str) -> str:
        """Normalize URL for consistent matching."""
        return url.replace('www.', '').replace('web.', '').replace('m.', '').replace('https://', '').replace('http://', '').rstrip('/')
    
    def _get_categories_for_url(self, url: str) -> List[str]:
        """Get categories for URL with normalized matching."""
        normalized = self._normalize_url(url)
        return self.page_to_categories.get(normalized, [])
    
    async def scrape_events(self) -> None:
        """Main orchestration method."""
        urls = self._read_urls()
        if not urls:
            self.logger.error("No URLs found to scrape")
            return
            
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
            
            context = await self._create_browser_context(browser)
            
            try:
                results = await self._process_urls_in_batches(context, urls)
                events = self._merge_results(results)
                
                if not events:
                    self.logger.warning("No events were extracted")
                else:
                    total_events = sum(len(e) for e in events.values())
                    self.logger.info(f"Successfully extracted {total_events} events across {len(events)} dates")
                
                self._save_events(events)
                
            finally:
                await context.close()
                await browser.close()
    
    async def _create_browser_context(self, browser) -> BrowserContext:
        """Create browser context with optimized settings."""
        context = await browser.new_context(
            user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36',
            viewport={'width': 1920, 'height': 1080},
            locale='en-US',
            timezone_id='Europe/Warsaw',
            java_script_enabled=True,
        )
        
        context.set_default_timeout(60000)
        
        # Resource blocking for performance
        if self.enable_resource_blocking:
            await context.route("**/*", self._route_handler)
        
        return context
    
    async def _route_handler(self, route) -> None:
        """Block unnecessary resources to improve performance."""
        request = route.request
        resource_type = request.resource_type
        
        # Block resource-heavy types
        if resource_type in ["image", "media", "font"]:
            await route.abort()
        # Block tracking domains
        elif any(domain in request.url for domain in ["analytics", "doubleclick", "tracking", "ads"]):
            await route.abort()
        else:
            await route.continue_()
    
    async def _process_urls_in_batches(self, context: BrowserContext, urls: List[str]) -> List[Dict]:
        """Process URLs in concurrent batches."""
        results = []
        batch_size = self.max_concurrent
        
        for i in range(0, len(urls), batch_size):
            batch = urls[i:i + batch_size]
            batch_num = i // batch_size + 1
            total_batches = (len(urls) + batch_size - 1) // batch_size
            
            self.logger.info(f"Processing batch {batch_num}/{total_batches}")
            
            tasks = [self._scrape_page_with_retry(context, url) for url in batch]
            batch_results = await asyncio.gather(*tasks, return_exceptions=True)
            
            for result in batch_results:
                if isinstance(result, Exception):
                    self.logger.error(f"Batch task failed: {result}")
                elif result:
                    results.append(result)
            
            # Delay between batches
            if i + batch_size < len(urls):
                await asyncio.sleep(3)
        
        return results
    
    async def _scrape_page_with_retry(
        self, 
        context: BrowserContext, 
        url: str, 
        max_retries: int = 3
    ) -> Dict:
        """Scrape page with exponential backoff retry logic."""
        for attempt in range(max_retries):
            try:
                return await self._scrape_page(context, url)
            except Exception as e:
                self.logger.warning(f"Attempt {attempt + 1}/{max_retries} failed for {url}: {str(e)}")
                if attempt < max_retries - 1:
                    await asyncio.sleep(5 * (2 ** attempt))
                else:
                    self.logger.error(f"All retries exhausted for {url}")
                    return {}
    
    async def _scrape_page(self, context: BrowserContext, url: str) -> Dict:
        """Scrape events from single page."""
        page = await context.new_page()
        try:
            self.logger.info(f"Processing: {url}")
            
            await page.goto(url, wait_until='networkidle', timeout=45000)
            await self._handle_popups_resilient(page)
            await self._smart_scroll(page)
            
            content = await page.content()
            events = self._parse_content_resilient(content, url)
            
            self.logger.info(f"Extracted {sum(len(e) for e in events.values())} events from {url}")
            return events
            
        except Exception as e:
            self.logger.error(f"Error processing {url}: {str(e)}", exc_info=True)
            return {}
        finally:
            await page.close()
    
    async def _handle_popups_resilient(self, page: Page) -> None:
        """Handle popups with multiple selector strategies."""
        # Handle cookie consent
        for selector in self.selectors.COOKIE_SELECTORS:
            try:
                element = page.locator(selector).first
                if await element.count() > 0:
                    await element.click(timeout=3000)
                    self.logger.info(f"Clicked cookie consent using: {selector}")
                    await page.wait_for_timeout(1000)
                    break
            except Exception:
                continue
        
        # Handle login/signup popups
        for selector in self.selectors.LOGIN_CLOSE_SELECTORS:
            try:
                element = page.locator(selector).first
                if await element.count() > 0:
                    await element.click(timeout=3000)
                    self.logger.info(f"Closed login popup using: {selector}")
                    await page.wait_for_timeout(1000)
                    break
            except Exception:
                continue
    
    async def _smart_scroll(self, page: Page, max_scrolls: int = 8) -> None:
        """Optimized scrolling that stops when no new content loads."""
        previous_height = 0
        no_change_count = 0
        
        for i in range(max_scrolls):
            await page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
            await page.wait_for_timeout(1500)
            
            current_height = await page.evaluate("document.body.scrollHeight")
            
            if current_height == previous_height:
                no_change_count += 1
                if no_change_count >= 2:
                    self.logger.debug(f"Stopped scrolling at iteration {i} (no new content)")
                    break
            else:
                no_change_count = 0
            
            previous_height = current_height
    
    def _parse_content_resilient(self, content: str, url: str) -> Dict[str, List[Dict]]:
        """
        Parse content using structure-based detection (no XPath needed).
        This approach is resistant to CSS class changes.
        """
        events = {}
        soup = BeautifulSoup(content, 'lxml')
        
        # Find event containers by structure
        event_containers = self._find_events_by_structure(soup)
        self.logger.debug(f"Found {len(event_containers)} event containers")
        
        page_categories = self._get_categories_for_url(url)
        
        for container in event_containers:
            try:
                event_data = self._extract_event_data_resilient(container)
                if event_data and event_data.date != "Date TBD":
                    event_data.event_categories = page_categories
                    
                    if event_data.date not in events:
                        events[event_data.date] = []
                    
                    events[event_data.date].append(event_data.to_dict())
                    
            except Exception as e:
                self.logger.debug(f"Could not extract event from container: {e}")
                continue
        
        return events
    
    def _find_events_by_structure(self, soup: BeautifulSoup) -> List:
        """
        Find events by HTML structure patterns.
        Multiple strategies for maximum resilience.
        """
        containers = []
        seen_links = set()
        
        # Strategy 1: Find all event links
        event_links = soup.find_all('a', href=lambda x: x and '/events/' in x)
        
        for link in event_links:
            event_url = link.get('href', '')
            if event_url in seen_links:
                continue
            seen_links.add(event_url)
            
            # Traverse up to find the container
            container = link
            for depth in range(15):
                if not container or not hasattr(container, 'parent'):
                    break
                container = container.parent
                
                if not container or container.name != 'div':
                    continue
                
                # Check if this looks like an event container
                # Must have: event link, text spans, and some structure
                has_link = container.find('a', href=lambda x: x and '/events/' in x)
                has_spans = container.find_all('span')
                has_structure = len(container.find_all('div')) > 2
                
                # Additional check: look for date-like text
                container_text = container.get_text().lower()
                has_date_indicator = any(indicator in container_text 
                                        for indicator in ['at ', 'pm', 'am', 'mon', 'tue', 'wed', 'thu', 'fri', 'sat', 'sun'])
                
                if has_link and len(has_spans) >= 2 and has_structure and has_date_indicator:
                    if container not in containers:
                        containers.append(container)
                    break
        
        self.logger.info(f"Found {len(containers)} unique event containers")
        return containers
    
    def _extract_event_data_resilient(self, container) -> Optional[EventData]:
        """
        Extract event data using multiple strategies for each field.
        """
        if not container:
            return None
        
        # Extract event link
        link_tag = container.find('a', href=lambda x: x and '/events/' in x)
        if not link_tag:
            return None
        event_url = self._clean_url(link_tag.get('href', ''))
        
        # Extract title
        title = self._extract_title_resilient(container, link_tag)
        
        # Extract date
        date = self._extract_date_resilient(container)
        
        # Extract location
        location = self._extract_location_resilient(container)
        
        return EventData(
            event_title=title,
            event_link=event_url,
            date=date,
            event_place=location,
            event_categories=[]
        )
    
    def _extract_title_resilient(self, container, link_tag) -> str:
        """Extract title using multiple fallback strategies."""
        # Strategy 1: Find span with html-span class
        title_span = container.find('span', class_=lambda x: x and 'html-span' in str(x))
        if title_span:
            text = title_span.get_text(strip=True)
            if text and len(text) > 3:
                return text
        
        # Strategy 2: Find heading elements
        for tag in ['h1', 'h2', 'h3', 'h4']:
            heading = container.find(tag)
            if heading:
                text = heading.get_text(strip=True)
                if text and len(text) > 3:
                    return text
        
        # Strategy 3: Find span with role="heading"
        heading_span = container.find('span', attrs={'role': 'heading'})
        if heading_span:
            text = heading_span.get_text(strip=True)
            if text and len(text) > 3:
                return text
        
        # Strategy 4: Get text from the link itself
        if link_tag:
            link_text = link_tag.get_text(strip=True)
            if len(link_text) > 3 and len(link_text) < 200:
                return link_text
        
        # Strategy 5: Find the longest meaningful span text
        spans = container.find_all('span')
        candidates = []
        for span in spans:
            text = span.get_text(strip=True)
            # Filter out date/time text and very short text
            if (len(text) > 5 and len(text) < 200 and 
                not any(time_word in text.lower() for time_word in ['at ', ' pm', ' am', 'cest', 'cet'])):
                candidates.append(text)
        
        if candidates:
            # Return the longest one
            return max(candidates, key=len)
        
        return "No Title"
    
    def _extract_date_resilient(self, container) -> str:
        """Extract date using multiple fallback strategies."""
        # Strategy 1: Find time element (semantic HTML)
        time_tag = container.find('time')
        if time_tag:
            datetime_attr = time_tag.get('datetime')
            if datetime_attr:
                return self._convert_date(datetime_attr)
            time_text = time_tag.get_text(strip=True)
            if time_text:
                return self._convert_date(time_text)
        
        # Strategy 2: Find spans containing time indicators
        time_indicators = ['at ', 'pm', 'am', 'pst', 'est', 'cest', 'cet']
        all_spans = container.find_all('span')
        for span in all_spans:
            text = span.get_text(strip=True)
            if any(indicator in text.lower() for indicator in time_indicators):
                date_result = self._convert_date(text)
                if date_result != "Date TBD":
                    return date_result
        
        # Strategy 3: Look for specific class patterns
        date_selectors = [
            {'class_': lambda x: x and 'xu06os2' in str(x)},
            {'class_': lambda x: x and 'x1lliihq' in str(x)},
        ]
        
        for selector in date_selectors:
            date_div = container.find('div', **selector)
            if date_div:
                date_span = date_div.find('span')
                if date_span:
                    date_result = self._convert_date(date_span.get_text(strip=True))
                    if date_result != "Date TBD":
                        return date_result
        
        # Strategy 4: Search all text for date patterns
        all_text = container.get_text()
        lines = [line.strip() for line in all_text.split('\n') if line.strip()]
        for line in lines:
            if any(indicator in line.lower() for indicator in time_indicators):
                date_result = self._convert_date(line)
                if date_result != "Date TBD":
                    return date_result
        
        return "Date TBD"
    
    def _extract_location_resilient(self, container) -> str:
        """Extract location using multiple fallback strategies."""
        # Strategy 1: Find address element
        address = container.find('address')
        if address:
            return address.get_text(strip=True).split('·')[0].strip()
        
        # Strategy 2: Find elements with location-related classes
        location_selectors = [
            {'class_': lambda x: x and 'x1gslohp' in str(x)},
        ]
        
        for selector in location_selectors:
            location_div = container.find('div', **selector)
            if location_div:
                # Get first div inside
                venue_div = location_div.find('div')
                if venue_div:
                    venue_text = venue_div.get_text(strip=True)
                    if 'Event by' in venue_text:
                        return venue_text.split('Event by')[0].strip()
                    return venue_text.split('·')[0].strip() if '·' in venue_text else venue_text
        
        # Strategy 3: Find text with location separator (·)
        all_text = container.get_text()
        if '·' in all_text:
            parts = [p.strip() for p in all_text.split('·')]
            for part in parts:
                # Location usually doesn't contain time and is reasonable length
                if ('at ' not in part.lower() and 
                    'pm' not in part.lower() and 
                    'am' not in part.lower() and
                    5 < len(part) < 100 and
                    not part.isdigit()):
                    # Check if it looks like a location (not a date, not too generic)
                    if any(char.isalpha() for char in part):
                        return part
        
        return "No location"
    
    def _clean_url(self, url: str) -> str:
        """Clean and standardize Facebook event URL."""
        if not url:
            return ""
        url = url.split('?')[0].split('#')[0]
        if not url.startswith('http'):
            url = f"https://www.facebook.com{url}"
        return url
    
    def _convert_date(self, date_string: str) -> str:
        """Convert various Facebook date formats to standardized format."""
        if not date_string:
            return "Date TBD"
        
        self.logger.debug(f"Converting date: '{date_string}'")
        date_string_lower = date_string.lower().strip()
        
        warsaw_tz = timezone(timedelta(hours=1))
        now = datetime.now(warsaw_tz)
        today = now.date()
        
        # Handle relative dates
        if "happening now" in date_string_lower or "today" in date_string_lower:
            return today.strftime("%d/%m/%Y")
        if "tomorrow" in date_string_lower:
            return (today + timedelta(days=1)).strftime("%d/%m/%Y")
        
        try:
            # Handle "Mon, Oct 13 at 6:00 PM" format
            if " at " in date_string_lower:
                date_part = date_string_lower.split(" at ")[0].strip()
            else:
                date_part = date_string_lower
            
            # Remove day of week if present
            if ',' in date_part:
                date_part = date_part.split(',', 1)[1].strip()
            
            parts = date_part.split()
            if len(parts) >= 2:
                month_str = parts[0][:3]
                day_str = parts[1].replace(',', '').strip()
                
                try:
                    month = self.MONTHS.get(month_str)
                    day = int(day_str)
                except (ValueError, AttributeError):
                    return "Date TBD"
                
                if month and 1 <= day <= 31:
                    # Determine year
                    event_date_this_year = datetime(now.year, month, day).date()
                    year = now.year + 1 if event_date_this_year < today else now.year
                    return datetime(year, month, day).strftime("%d/%m/%Y")
        
        except Exception as e:
            self.logger.debug(f"Date parsing error: {e}")
        
        return "Date TBD"
    
    def _merge_results(self, results: List[Dict]) -> Dict[str, List[Dict]]:
        """Merge and deduplicate events from multiple pages."""
        merged = {}
        seen_events: Set[str] = set()
        
        for result in results:
            for date, events in result.items():
                if date not in merged:
                    merged[date] = []
                
                for event in events:
                    event_id = f"{event['event_title']}|{date}|{event['event_link']}"
                    
                    if event_id not in seen_events:
                        merged[date].append(event)
                        seen_events.add(event_id)
        
        merged = {date: events for date, events in merged.items() if events}
        
        self.logger.info(f"Merged {len(seen_events)} unique events across {len(merged)} dates")
        return merged
    
    def _read_urls(self) -> List[str]:
        """Read URLs from CSV file (from fb_page_link column)."""
        urls = []
        try:
            with open(self.csv_file, "r", encoding="utf-8") as csvfile:
                reader = csv.DictReader(csvfile)
                for row in reader:
                    if 'fb_page_link' in row:
                        url = row['fb_page_link'].strip()
                        if url.startswith("http"):
                            # Add /upcoming_hosted_events if not present
                            if '/upcoming_hosted_events' not in url:
                                url = url.rstrip('/') + '/upcoming_hosted_events'
                            urls.append(url)
        except Exception as e:
            self.logger.error(f"Error reading URLs from {self.csv_file}: {e}")
        
        return list(set(urls))
    
    def _save_events(self, events: Dict[str, List[Dict]]) -> None:
        """Save events to JSON with date sorting."""
        try:
            # Sort by date
            events_with_dates = {
                (datetime.strptime(date, "%d/%m/%Y") if date != "Date TBD" else datetime.max): event_list
                for date, event_list in events.items()
            }
            
            sorted_events = dict(sorted(events_with_dates.items()))
            
            sorted_events_str = {
                key.strftime("%d/%m/%Y") if key != datetime.max else "Date TBD": value
                for key, value in sorted_events.items()
            }
            
            output_file = Path("events_data.json")
            with open(output_file, "w", encoding="utf-8") as f:
                json.dump(sorted_events_str, f, ensure_ascii=False, indent=2)
            
            self.logger.info(f"Successfully saved events to {output_file}")
            
        except Exception as e:
            self.logger.error(f"Error saving events: {e}")
    
    async def run(self) -> None:
        """Entry point for the scraper."""
        await self.scrape_events()


if __name__ == "__main__":
    scraper = FacebookEventScraper(
        csv_file="page_categories.csv",
        max_concurrent=3,
        enable_resource_blocking=True
    )
    asyncio.run(scraper.run())
