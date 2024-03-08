import json
from datetime import datetime, timedelta
from flask import Flask, render_template

app = Flask(__name__)
app.config["DEBUG"] = True

EVENTS_DATA_FILE = "events_data.json"

@app.template_filter('str_to_datetime')
def str_to_datetime(date_str, date_format='%d/%m/%y'):
    """
    Custom filter for display datetime
    """
    try:
        return datetime.strptime(date_str, date_format).date()
    except ValueError:
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
        tomorrow=date_for_tomorrow, 
        after_tomorrow=date_after_tomorrow
    )


def load_events_data():
    """
    Load events data from JSON file
    """
    try:
        with open(EVENTS_DATA_FILE) as json_file:
            events = json.load(json_file)
        return events
    except FileNotFoundError:
        # Return empty dictionary if file does not exist yet
        return {}

if __name__ == "__main__":
    app.run(debug=True)
