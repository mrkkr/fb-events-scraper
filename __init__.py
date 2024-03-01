import csv
import json
import logging
import re
import time
import traceback
from bs4 import BeautifulSoup
from datetime import datetime
from seleniumwire import webdriver
from selenium.common.exceptions import NoSuchElementException
from selenium.common.exceptions import TimeoutException
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from concurrent.futures import ThreadPoolExecutor
from urllib.parse import urlparse, urlunparse


class EventScraper:
    def __init__(self, csv_file):
        """
        Initializes the scraper with necessary variables and configurations.
        :param csv_file: Path to the CSV file for storing scraped data.
        """
        # CSV file with URLs
        self.CSV_FILE = csv_file

        # Define CSS class selectors for scraping content using both Selenium and BeautifulSoup
        self.CLASS_TO_SCRAPE_SELENIUM = "div.x6s0dn4.x1lq5wgf.xgqcy7u.x30kzoy.x9jhf4c.x1olyfxc.x9f619.x78zum5.x1e56ztr.xyamay9.x1pi30zi.x1l90r2v.x1swvt13.x1gefphp"
        self.CLASS_TO_SCRAPE_BS4 = "x6s0dn4 x1lq5wgf xgqcy7u x30kzoy x9jhf4c x1olyfxc x9f619 x78zum5 x1e56ztr xyamay9 x1pi30zi x1l90r2v x1swvt13 x1gefphp"
        self.COOKIE_CONSENT_CSS_CLASS = ".x9f619.x1n2onr6.x1ja2u2z.x78zum5.xdt5ytf.x193iq5w.xeuugli.x1iyjqo2.xs83m0k.x150jy0e.x1e558r4.xjkvuk6.x1iorvi4.xdl72j9"
        self.LOGIN_PROMPT_CSS_CLASS = ".x1i10hfl.x1ejq31n.xd10rxx.x1sy0etr.x17r0tee.x1ypdohk.xe8uvvx.xdj266r.x11i5rnm.xat24cr.x1mh8g0r.x16tdsg8.x1hl2dhg.xggy1nq.x87ps6o.x1lku1pv.x1a2a7pz.x6s0dn4.x14yjl9h.xudhj91.x18nykt9.xww2gxu.x972fbf.xcfux6l.x1qhh985.xm0m39n.x9f619.x78zum5.xl56j7k.xexx8yu.x4uap5.x18d9i69.xkhd6sd.x1n2onr6.xc9qbxq.x14qfxbe.x1qhmfi1"
        # Event parts elements to scrap by BS4
        self.EVENT_DATE_ELEMENT_CSS_CLASS = "x193iq5w xeuugli x13faqbe x1vvkbs x10flsy6 x1lliihq x1s928wv xhkezso x1gmr53x x1cpjm7i x1fgarty x1943h6x x1tu3fi x3x7a5m x1nxh6w3 x1sibtaa xo1l8bm xzsf02u x1yc453h"
        self.EVENT_DATE_CSS_CLASS = "x1lliihq x6ikm8r x10wlt62 x1n2onr6 xlyipyv xuxw1ft"
        self.EVENT_LINK = "x1i10hfl xjbqb8w x1ejq31n xd10rxx x1sy0etr x17r0tee x972fbf xcfux6l x1qhh985 xm0m39n x9f619 x1ypdohk xt0psk2 xe8uvvx xdj266r x11i5rnm xat24cr x1mh8g0r xexx8yu x4uap5 x18d9i69 xkhd6sd x16tdsg8 x1hl2dhg xggy1nq x1a2a7pz x1heor9g xt0b8zv x1s688f"
        self.EVENT_PLACE_PARENT = "x1gslohp"
        self.EVENT_BY_PLACE = "x1i10hfl xjbqb8w x1ejq31n xd10rxx x1sy0etr x17r0tee x972fbf xcfux6l x1qhh985 xm0m39n x9f619 x1ypdohk xt0psk2 xe8uvvx xdj266r x11i5rnm xat24cr x1mh8g0r xexx8yu x4uap5 x18d9i69 xkhd6sd x16tdsg8 x1hl2dhg xggy1nq x1a2a7pz xt0b8zv xi81zsa x1s688f"

        # Setup logging to file for error tracking and debugging
        self.logger = logging.getLogger(__name__)
        logging.basicConfig(filename="scraping.log", level=logging.WARNING)

        # Flag to track whether popups have been dismissed
        self.popups_dismissed = False

        # start driver only one time during instance
        self.start_driver()

        # calculate time
        self.start_time = None
        self.end_time = None


    def remove_query_string(self, url):
        """
        Cleans URLs by removing the query string.
        :param url: The original URL with a possible query string.
        :return: The URL without the query string.
        """
        parsed_url = urlparse(url)
        cleaned_url = urlunparse((parsed_url.scheme, parsed_url.netloc, parsed_url.path, '', '', ''))
        return cleaned_url


    def convert_dates(self, date_string):
        """
        Converts Polish date strings into a standardized date format.
        :param date_string: The original date string in Polish format.
        :return: The date in 'DD/MM/YY' format.
        """
        # empty formatted date
        formatted_date = ""
        # Remove everything after "o" letter if it exists
        date_string = date_string.split(" o ")[0]
        # Remove leading and trailing whitespaces
        date_string = date_string.strip()
        
        # Dictionary mapping Polish month abbreviations to their numeric equivalents
        months_polish = {
            "sty": 1,
            "lut": 2,
            "mar": 3,
            "kwi": 4,
            "maj": 5,
            "cze": 6,
            "lip": 7,
            "sie": 8,
            "wrz": 9,
            "paź": 10,
            "lis": 11,
            "gru": 12
        }
        
        # Check if there's a range of dates (indicated by "-") and trasform to format: dd month - dd month
        if "–" in date_string:
            date_array = date_string.split("–")
            if len(date_array) > 0:
                date_array[0] = date_array[0].split(' ', 1)[1].strip()
                formatted_date = (" –").join(date_array)
        else:
            try:
                # Extract day, month abbreviation, and year from the date string parts
                # Split the date string by comma
                parts = date_string.split(",")
                if len(parts) >= 2:
                    day_str, rest = parts[1].strip().split()
                    day_num = int(day_str)
                    month_str = rest.split()[0].lower()[:3]  # Convert month abbreviation to lowercase
                else:
                    formatted_date = date_string
                    raise ValueError("Date string does not contain expected parts")
            except ValueError:
                return "Brak daty" # formatted_date = "Brak Daty"

            # Convert month abbreviation to its numeric equivalent
            month = months_polish.get(month_str)

            # Convert the date string to a formatted date
            formatted_date = f"{day_num:02d}/{month:02d}/24"

        return formatted_date


    def scroll_down_page(self, driver):
        """
        Scrolls to the bottom of a dynamically loading webpage to ensure all content is loaded.
        :param driver: The Selenium WebDriver instance.
        """
        last_height = 0

        while True:
            # Scroll down to the bottom of the page
            driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
            time.sleep(2)  # Wait for new content to load

            # Calculate new scroll height and compare with last scroll height
            new_height = driver.execute_script("return document.body.scrollHeight")
            if new_height == last_height:
                break  # Break the loop when the bottom of the page is reached
            last_height = new_height


    def dismiss_popups(self, driver):
        """
        Dismisses cookie consent popup and login prompt that may appear on the webpage.
        This function aims to ensure that these popups do not interfere with the scraping process
        by explicitly looking for and clicking the dismissal buttons.

        :param driver: The Selenium WebDriver instance used for navigating and interacting with web pages.
        """

        # Attempt to dismiss the cookie consent popup if it appears
        if not self.popups_dismissed:
            # Attempt to dismiss the cookie consent popup if it appears
            try:
                # Locate the accept button for cookie consent using its CSS selector
                accept_cookie_button = driver.find_element(By.CSS_SELECTOR, self.COOKIE_CONSENT_CSS_CLASS)
                # Click the accept button to dismiss the cookie consent popup
                accept_cookie_button.click()
            except NoSuchElementException:
                self.logger.warning("Cookie consent popup not found")
                # Print the full traceback to help diagnose the issue
                traceback.print_exc()

            # Update the flag to indicate that popups have been dismissed
            self.popups_dismissed = True

        # Attempt to dismiss the login prompt if it appears
        try:
            # Locate the close button for the login prompt using its CSS selector
            close_login_prompt = driver.find_element(By.CSS_SELECTOR, self.LOGIN_PROMPT_CSS_CLASS)
            # Click the close button to dismiss the login prompt
            close_login_prompt.click()
        except NoSuchElementException:
            self.logger.warning("Login prompt popup not found")
            # Print the full traceback to help diagnose the issue
            traceback.print_exc()


    def scrape_page(self, url):
        """
        Processes each URL by loading the page in a Selenium WebDriver, extracting data,
        and returning the structured data.
        :param url: The URL to process and scrape data from.
        :return: A dictionary of extracted data keyed by date.
        """
        driver = self.driver # Initialize the driver variable

        try:
            # Configure and initialize the Selenium WebDriver
            driver.get(url)
            time.sleep(2)
            print(f"url: {url}")

            # Dismiss any pop-ups or consent modals that may interfere with page content access
            self.dismiss_popups(driver)

            # Scroll down the page to trigger loading of all dynamic content
            self.scroll_down_page(driver)

            # Step 1: Check if elements are present immediately after page load
            if not driver.find_elements(By.CSS_SELECTOR, self.CLASS_TO_SCRAPE_SELENIUM):
                # Step 2: Wait for the page to fully load and then recheck
                try:
                    WebDriverWait(driver, 5).until(EC.presence_of_all_elements_located((By.CSS_SELECTOR, self.CLASS_TO_SCRAPE_SELENIUM)))
                except TimeoutException:
                    self.logger.info(f"No events found on the Facebook page: {url}")
                    extracted_contents = {}  # Return an empty dictionary to indicate no events
            page_source = driver.page_source
            extracted_contents = self.create_soup(page_source)
            if not extracted_contents:
                self.logger.warning(f"No content extracted from {url}")
        except Exception as e:
            self.logger.error(f"Error processing URL {url}: {e}")
            traceback.print_exc()
            extracted_contents = {}
        return extracted_contents


    def scrape_subpages(self, urls):
        """
        Main method to control the scraping process. It reads URLs from a CSV file,
        iterates over them, and scrapes data using multiple threads for efficiency.
        
        Parameters:
            urls (list): List of URLs to scrape data from.
        """
        # Initialize a dictionary to store all scraped events
        all_events_obj = {}
        
        # Use ThreadPoolExecutor to execute scraping tasks concurrently
        with ThreadPoolExecutor(max_workers=1) as executor:
            # Map each URL to the scrape_page function and execute asynchronously
            results = list(executor.map(self.scrape_page, urls))
            
            # Iterate over the results of scraping each URL
            for result in results:
                # Extract the date and events from the result
                for date, events in result.items():
                    # Extend the events list if the date already exists in the dictionary,
                    # otherwise, add a new entry for the date
                    if date in all_events_obj:
                        all_events_obj[date].extend(events)
                    else:
                        all_events_obj[date] = events
                        
        # Sort the events by date and save them to a JSON file
        self.sort_and_save_data_to_file(all_events_obj, "events_data.json")


    def create_soup(self, page_source):
        """
        Parses the page source with BeautifulSoup to extract relevant event information.
        :param page_source: The HTML content of the page.
        :return: A dictionary of events categorized by date.
        """
        try:
            soup = BeautifulSoup(page_source, "html.parser")
            contents = soup.find_all("div", class_=self.CLASS_TO_SCRAPE_BS4)
            # create extracted object with event details
            extracted_events = {}

            # loop through events
            for content in contents:
                # defines particular event elements
                event_date_element = content.find("span", class_ = self.EVENT_DATE_ELEMENT_CSS_CLASS)
                event_date = event_date_element.find("span", class_ = self.EVENT_DATE_CSS_CLASS).text if event_date_element else "No Date Available"
                converted_event_date = self.convert_dates(event_date)
                event_link = content.find("a", class_ = self.EVENT_LINK)["href"]
                event_title = content.find("a", class_=self.EVENT_LINK).find("span", class_="").text
                event_place_parent = content.find('div', class_ = self.EVENT_PLACE_PARENT)
                # calculate event place based on conditions
                event_place = ""
                event_by_place_css_class = self.EVENT_BY_PLACE
                if event_place_parent.find('a', class_ = event_by_place_css_class):
                    event_place = event_place_parent.find('a', class_ = event_by_place_css_class).text
                else:
                    event_place = content.find('div', class_='x1gslohp').find('div').get_text(strip=True)

                # local event
                local_event_object = {
                    "event_title": event_title,
                    "event_link": self.remove_query_string(event_link),
                    "event_place": event_place
                }

                # Check if date exists in main events object
                if converted_event_date not in extracted_events:
                    extracted_events[converted_event_date] = []

                # Check if the event link already exists for this date
                existing_links = {event['event_link'] for event in extracted_events[converted_event_date]}
                if local_event_object['event_link'] not in existing_links:
                    extracted_events[converted_event_date].append(local_event_object)

        except Exception as e:
            self.logger.error(f"Error creating soup: {e}")
            traceback.print_exc()
            return {}

        return extracted_events


    def convert_to_date(self, date_str):
        """
        Converts a date string to a datetime object.
        :param date_str: The date string to convert.
        :return: The datetime object representing the date.
        """
        try:
            return datetime.strptime(date_str, '%d/%m/%y')
        except ValueError:
            return None


    def sort_and_save_data_to_file(self, all_events_obj, filename):
        """
        Sorts the events object by date in ascending order and saves it to a JSON file.
        
        Parameters:
            all_events_obj (dict): The events object to be saved.
            filename (str): The name of the JSON file to save the object to.
        """
        try:
            # Sort the dictionary by date
            sorted_events_obj = dict(sorted(all_events_obj.items(), key=lambda item: self.convert_to_date(item[0]) or datetime.max))

            # Convert keys back to strings
            sorted_events_obj_str = {key.strftime('%d/%m/%y') if isinstance(key, datetime) else key: value for key, value in sorted_events_obj.items()}

            # Save the sorted events object to a JSON file
            with open(filename, "w", encoding="utf-8") as output:
                json.dump(sorted_events_obj, output, ensure_ascii=False, indent=4)
        except Exception as e:
            self.logger.error(f"Error saving data to file: {e}")


    def set_chrome_options(self):
        """
        Configures Chrome options for the Selenium WebDriver to optimize scraping efficiency and effectiveness.
        :return: Configured ChromeOptions object.
        """
        options = webdriver.ChromeOptions()
        options.add_argument("--headless")
        options.add_argument("--disable-gpu")
        options.add_argument("--disable-notifications")
        options.add_argument("--disable-extensions")
        options.add_argument("--disable-popup-blocking")
        options.add_argument("--disable-default-apps")
        options.add_argument("--disable-infobars")
        options.add_argument("--disable-web-security")
        options.add_argument("--disable-features=IsolateOrigins,site-per-process")
        options.add_argument("--enable-features=NetworkService,NetworkServiceInProcess")
        options.add_argument("--profile-directory=Default")
        options.add_experimental_option("excludeSwitches", ["enable-logging"])
        return options


    def start_driver(self):
        """
        Initializes and starts the Chrome WebDriver with configured options.
        """
        # Set Chrome options
        options = self.set_chrome_options()
        # Initialize Chrome WebDriver
        self.driver = webdriver.Chrome(options=options)


    def stop_driver(self):
        """
        Stops the Chrome WebDriver if it is running.
        """
        # Check if the driver attribute exists and is not None
        if hasattr(self, 'driver') and self.driver:
            # Quit the WebDriver
            self.driver.quit()


    def start_timer(self):
        """
        Start the timer.
        """
        self.start_time = time.time()


    def stop_timer(self):
        """
        Stop the timer and calculate the elapsed time.
        """
        self.end_time = time.time()
        elapsed_time = self.end_time - self.start_time
        return elapsed_time


if __name__ == "__main__":
    scraper = EventScraper("my_liked_pages.csv")
    # start timer
    scraper.start_timer()

    urls = []

    with open(scraper.CSV_FILE, "r") as csvfile:
        reader = csv.reader(csvfile)
        next(reader)  # Skip the header row
        for row in reader:
            urls.extend(row)

    try:
        scraper.scrape_subpages(urls)
    finally:
        scraper.stop_driver()

    elapsed_time = scraper.stop_timer()
    print(f"Elapsed time: {elapsed_time} seconds")