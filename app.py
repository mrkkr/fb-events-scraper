import json
from datetime import datetime, timedelta
from flask import Flask, render_template

app = Flask(__name__)
app.config["DEBUG"] = True

EVENTS_DATA_FILE = "events_data.json"

@app.template_filter('str_to_datetime')
def str_to_datetime(date_str, date_format='%d/%m/%Y'):
    """
    Custom filter for display datetime.
    Converts date string in DD/MM/YYYY format to datetime object.
    """
    try:
        print(f"Converting date: {date_str}, format: {date_format}")
        result = datetime.strptime(date_str, date_format).date()
        print(f"Conversion result: {result}")
        return result
    except ValueError as e:
        print(f"Error converting date {date_str}: {str(e)}")
        return None

@app.route("/")
def display_data_in_web_app():
    """
    Display scraped data in Flask web app
    """
    events = load_events_data()

    # Get current date
    current_date = datetime.now().date()

    # Calculate date for tomorrow and day after tomorrow
    date_for_tomorrow = current_date + timedelta(days=1)
    date_after_tomorrow = current_date + timedelta(days=2)

    return render_template("index.html", 
        events=events, 
        current_date=current_date, 
        tomorrow=date_for_tomorrow
    )


def load_events_data():
    """Load and sort events data from JSON file"""
    try:
        with open(EVENTS_DATA_FILE) as json_file:
            events = json.load(json_file)
            
            # Convert dates to datetime for sorting
            events_with_dates = {
                (datetime.strptime(date, "%d/%m/%Y") if date != "Date TBD" else datetime.max): event_list
                for date, event_list in events.items()
            }
            
            # Sort by date
            sorted_events = dict(sorted(events_with_dates.items()))
            
            # Convert back to string format
            return {
                key.strftime("%d/%m/%Y") if key != datetime.max else "Date TBD": value
                for key, value in sorted_events.items()
            }
    except FileNotFoundError:
        return {}

if __name__ == "__main__":
    app.run(debug=True)
