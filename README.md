# Facebook Events Scraper

A Python script to scrape events from Facebook pages and display them in a simple Flask web application.

## Prerequisites

- Python 3.8 or higher
- pip (Python package installer)
- Git

## Installation

1. Clone the repository:
```bash
git clone https://github.com/yourusername/fb-events-scraper.git
cd fb-events-scraper
```

2. Create and activate virtual environment:
```bash
python -m venv .venv
source .venv/bin/activate  # On Linux/Mac
# or
.venv\Scripts\activate  # On Windows
```

3. Install required packages:
```bash
pip install -r requirements.txt
```

4. Install Playwright and its dependencies:
```bash
playwright install
playwright install-deps
playwright install chrome
```

## Configuration

1. Create a CSV file (e.g., `my_liked_pages.csv`) with Facebook pages URLs and categories:
```csv
fb_page_link,category
https://facebook.com/your-page-1/upcoming_hosted_events,music,concert
https://facebook.com/your-page-2/upcoming_hosted_events,theater,exhibition
```

The category column can contain multiple categories separated by commas. These categories will be used to filter events in the web interface.

## Usage

### Running the Scraper

1. Make sure your virtual environment is activated
2. Run the scraper:
```bash
python -m fb_events_scraper
```

The script will:
- Read URLs from your CSV file
- Scrape events from each page
- Save results to `events_data.json`

### Running the Flask Web Application

1. Ensure you have scraped some events first (events_data.json should exist)
2. Start the Flask server:
```bash
python app.py
```
3. Open your browser and visit:
```
http://localhost:5000
```

## Flask Application Structure

The web application provides a simple interface to view scraped events:
- Events are grouped by date
- Today's events are highlighted
- Events are sorted chronologically

## Troubleshooting

If you encounter any issues:

1. Make sure all dependencies are installed:
```bash
pip install -r requirements.txt
```

2. Check if Playwright is installed correctly:
```bash
playwright install --help
```

3. Verify your CSV file format is correct
4. Ensure you have proper internet connection
5. Check if events_data.json exists before running Flask app

## Additional information
For scrape FB Page links to CSV File - I recommened using this browser extension -> [www.webscraper.io](https://www.webscraper.io)

## License

This project is licensed under the MIT License - see the LICENSE file for details.

## Contributing

1. Fork the repository
2. Create your feature branch
3. Commit your changes
4. Push to the branch
5. Open a Pull Request

## Notes

- This scraper is for educational purposes only
- Respect Facebook's terms of service and rate limiting
- Some events might not be accessible due to privacy settings