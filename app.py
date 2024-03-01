import json
from datetime import datetime
from flask import Flask, render_template

app = Flask(__name__)
app.config["DEBUG"] = True

EVENTS_DATA_FILE = "events_data.json"

@app.route("/")
def display_data_in_web_app():
    """
    Display scraped data in Flask web app
    """
    events = load_events_data()
    return render_template("index.html", events=events)

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
