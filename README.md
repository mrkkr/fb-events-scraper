# Facebook Events Scraper
With this script you can scrape events from your liked facebook pages to one file and display it in simple Flask one-page website. 

## Installation:
1. Scrape FB Page links to CSV File. To do it I recommened using this browser extension -> [www.webscraper.io](https://www.webscraper.io)
2. Clone repository
3. Put your file with fb page link as `my_liked_pages.csv`
4. Run`__init__.py`
5. Feel free to customize Flask app in `app.py`, `templates` and `static` folder


### Additional information:
1. Scraper data are stored in `events_data.json` file
2. Main key for scraped dict date is date in format `DD/MM/YY`
3. If you have problem with running webdriver from `seleniumwire` you can try use webdriver from `selenium` using `from seleniumwire import webdriver`