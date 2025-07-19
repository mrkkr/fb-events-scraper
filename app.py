import csv
import json
import os # <-- Import the os module
from datetime import datetime, timedelta
from flask import Flask, render_template

# --- SOLUTION: Define the absolute path to the project directory ---
# This gets the directory where this app.py file is located.
BASE_DIR = os.path.dirname(os.path.abspath(__file__))

# Construct absolute paths for your data files
EVENTS_DATA_FILE = os.path.join(BASE_DIR, "events_data.json")
CATEGORIES_FILE = os.path.join(BASE_DIR, "page_categories.csv")
# --- END SOLUTION ---


app = Flask(__name__)
app.config["DEBUG"] = True


def get_unique_categories():
    """
    Helper function - get unique categories from CSV file
    """
    categories = set()
    try:
        # Use the absolute path variable
        with open(CATEGORIES_FILE, encoding='utf-8') as f:
            reader = csv.DictReader(f)
            for row in reader:
                if 'category' in row and row['category']:
                    for cat in row['category'].split(','):
                        categories.add(cat.strip())
        return sorted(categories)
    except FileNotFoundError:
        # This will help you debug if the file is truly missing on the server
        print(f"Error: Could not find categories file at {CATEGORIES_FILE}")
        return []


@app.template_filter('str_to_datetime')
def str_to_datetime(date_str, date_format='%d/%m/%Y'):
    """
    Custom filter for display datetime.
    Converts date string in DD/MM/YYYY format to datetime object.
    """
    try:
        return datetime.strptime(date_str, date_format).date()
    except (ValueError, TypeError):
        # This will now safely handle None or other invalid values
        return None


@app.route("/")
def display_data_in_web_app():
    """
    Display scraped data in Flask web app
    """
    events = load_events_data()
    current_date = datetime.now().date()
    date_for_tomorrow = current_date + timedelta(days=1)
    unique_categories = get_unique_categories()

    return render_template("index.html", 
        events=events, 
        current_date=current_date, 
        tomorrow=date_for_tomorrow,
        unique_categories=unique_categories
    )


def load_events_data():
    """Load and sort events data from JSON file"""
    try:
        # Use the absolute path variable
        with open(EVENTS_DATA_FILE, encoding='utf-8') as json_file:
            events = json.load(json_file)
            
            events_with_dates = {
                (datetime.strptime(date, "%d/%m/%Y") if date != "Date TBD" else datetime.max): event_list
                for date, event_list in events.items()
            }
            
            sorted_events = dict(sorted(events_with_dates.items()))
            
            return {
                key.strftime("%d/%m/%Y") if key != datetime.max else "Date TBD": value
                for key, value in sorted_events.items()
            }
    except FileNotFoundError:
        print(f"Error: Could not find events file at {EVENTS_DATA_FILE}")
        return {}

if __name__ == "__main__":
    app.run(debug=True)
