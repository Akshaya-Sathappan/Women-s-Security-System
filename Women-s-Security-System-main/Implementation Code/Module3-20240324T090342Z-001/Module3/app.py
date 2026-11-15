import json
import os
import secrets
import smtplib
import threading
from functools import wraps

from flask import Flask, render_template, request, redirect, url_for, flash, jsonify, session
from werkzeug.security import generate_password_hash, check_password_hash

import utils

app = Flask(__name__)

# ---------------------- Security Configuration ----------------------
_secret_key = os.environ.get("FLASK_SECRET_KEY")
if not _secret_key:
    # Fallback for local development only: sessions are invalidated on every restart.
    print("WARNING: FLASK_SECRET_KEY is not set; using a temporary random key.")
    _secret_key = secrets.token_hex(32)
app.config.update(
    SECRET_KEY=_secret_key,
    SESSION_COOKIE_HTTPONLY=True,
    SESSION_COOKIE_SAMESITE="Lax",
    SESSION_COOKIE_SECURE=os.environ.get("SESSION_COOKIE_SECURE", "0") == "1",
)

MIN_PASSWORD_LENGTH = 8


def hash_password(password: str) -> str:
    # PBKDF2 is used explicitly because scrypt (Werkzeug's default) is missing
    # from some Python builds, including the macOS system Python.
    return generate_password_hash(password, method="pbkdf2:sha256:600000")

# ---------------------- User Data Storage ----------------------
DATA_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "details.json")
_data_lock = threading.Lock()


def _is_hashed(value: str) -> bool:
    return isinstance(value, str) and value.startswith(("pbkdf2:", "scrypt:"))


def save_data() -> None:
    with _data_lock:
        tmp_path = DATA_FILE + ".tmp"
        with open(tmp_path, "w") as f:
            json.dump(data, f, indent=2)
        os.replace(tmp_path, DATA_FILE)


def load_data() -> tuple:
    """Load user data, migrating legacy formats (plaintext passwords, single shared profile)."""
    if os.path.exists(DATA_FILE):
        with open(DATA_FILE, "r") as f:
            loaded = json.load(f)
    else:
        loaded = {}

    loaded.setdefault("login", {})
    loaded.setdefault("profiles", {})
    changed = False

    # Hash any plaintext passwords left over from the old format.
    for username, password in loaded["login"].items():
        if not _is_hashed(password):
            loaded["login"][username] = hash_password(password)
            changed = True

    # Move the old single shared profile under its owner's username.
    legacy_profile = loaded.pop("profile", None)
    if legacy_profile is not None:
        owner = legacy_profile.get("username")
        if owner and owner not in loaded["profiles"]:
            loaded["profiles"][owner] = legacy_profile
        changed = True

    return loaded, changed


data, _needs_save = load_data()
if _needs_save:
    save_data()


# ---------------------- Per-user Session State ----------------------
# Route/map state is kept per logged-in user instead of in shared globals.
# Map HTML is too large for a cookie, so it lives server-side keyed by username.
_user_state = {}


def get_state() -> dict:
    return _user_state.setdefault(session["user"], {
        "source": None,
        "destination": None,
        "routes_map": None,
        "police_station_name": None,
        "latitude": None,
        "longitude": None,
    })


def current_profile() -> dict:
    return data["profiles"].get(session["user"], {})


def login_required(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        if "user" not in session or session["user"] not in data["login"]:
            session.clear()
            if request.is_json or request.method == "POST":
                return jsonify({"status": "error", "error": "Authentication required"}), 401
            return redirect(url_for("login"))
        return view(*args, **kwargs)
    return wrapped


# ---------------------- News ----------------------
class Post:
    """Represents a news post with title and image"""
    def __init__(self, title, image_url):
        self.title = title
        self.image_url = image_url


try:
    news_list = utils.get_news().get("articles", [])[:6]
except Exception as e:
    print(f"Could not load news: {e}")
    news_list = []

posts = [Post(article.get("title"), article.get("urlToImage")) for article in news_list]


# ---------------------- Routes ----------------------
@app.route('/', methods=['GET', 'POST'])
def login():
    """Login page route"""
    if request.method == 'POST':
        username = request.form.get('username', '').strip()
        password = request.form.get('password1', '')

        stored_hash = data["login"].get(username)
        if stored_hash and check_password_hash(stored_hash, password):
            session.clear()
            session["user"] = username
            return redirect(url_for('home'))

        print(f'Failed login attempt for username: {username!r}')
        flash('Invalid username or password', 'error')

    return render_template('login.html')


@app.route('/logout')
def logout():
    """Log out and clear per-user state"""
    user = session.pop("user", None)
    _user_state.pop(user, None)
    session.clear()
    return redirect(url_for('login'))


@app.route('/signup', methods=['GET', 'POST'])
def signup():
    """User signup route"""
    if request.method == 'POST':
        email = request.form.get('email', '').strip()
        username = request.form.get('username', '').strip()
        password = request.form.get('password1', '')
        confirmpassword = request.form.get('confirmpassword', '')

        error = None
        if not email or not username or not password:
            error = 'All fields are required'
        elif username in data["login"]:
            error = 'That username is already taken'
        elif len(password) < MIN_PASSWORD_LENGTH:
            error = f'Password must be at least {MIN_PASSWORD_LENGTH} characters'
        elif password != confirmpassword:
            error = 'Passwords do not match'

        if error:
            flash(error, 'error')
            return render_template('signup.html')

        data["login"][username] = hash_password(password)
        data["profiles"][username] = {"username": username, "email": email}
        save_data()
        print(f'New user signed up: {username!r}')

        flash('Account created, please log in', 'success')
        return redirect(url_for('login'))

    return render_template('signup.html')


@app.route('/home', methods=['GET', 'POST'])
@login_required
def home():
    """Home page route where user can enter source/destination"""
    state = get_state()
    if request.method == 'POST':
        source = (request.form.get('source') or '').strip()
        destination = (request.form.get('destination') or '').strip()

        try:
            # Get coordinates
            source_lat, source_long = utils.get_lat_long_from_address(source)
            dest_lat, dest_long = utils.get_lat_long_from_address(destination)

            # Get route and create map
            route = utils.get_route(source_lat, source_long, dest_lat, dest_long)
            routes_map = utils.create_map(route)
        except ValueError as e:
            # Address not found or no route: tell the user what to fix
            flash(f'{e}. Try a more specific address that includes the city and country.', 'error')
            return render_template('home.html', posts=posts)
        except Exception as e:
            print(f'Route lookup failed: {e}')
            flash('Could not get directions right now. Please try again in a moment.', 'error')
            return render_template('home.html', posts=posts)

        state.update(source=source, destination=destination, routes_map=routes_map)
        return redirect(url_for('map_1'))

    return render_template('home.html', posts=posts)


@app.route('/dashboard', methods=['GET', 'POST'])
@login_required
def dashboard():
    """User profile and dashboard route"""
    if request.method == 'POST':
        # Update profile (username is the logged-in account and cannot be changed here)
        emergency_email = request.form.get('emergency-email') or ''
        data["profiles"][session["user"]] = {
            "username": session["user"],
            "email": request.form.get('email'),
            "contact": request.form.get('contact-number'),
            "address": request.form.get('home-address'),
            "emergency": emergency_email.strip(),
        }
        save_data()

    return render_template('dashboard.html', user_details=current_profile())


@app.route('/dashboard/profile-picture-update', methods=['POST'])
@login_required
def update_profile_picture():
    """Update profile picture"""
    try:
        if 'profilePicture' not in request.files:
            return jsonify({'error': 'No file provided'}), 400
        file = request.files['profilePicture']
        if file.filename == '':
            return jsonify({'error': 'No file selected'}), 400

        # In production, save file to a folder
        return jsonify({'profilePicturePath': file.filename})

    except Exception as e:
        print(f'Profile picture update failed: {e}')
        return jsonify({'error': 'Upload failed'}), 500


@app.route('/map_1', methods=['GET', 'POST'])
@login_required
def map_1():
    """Render the route map from source to destination"""
    state = get_state()
    routes_map = state["routes_map"]
    if routes_map is None:
        flash('Enter a source and destination to see directions.', 'error')
        return redirect(url_for('home'))
    return render_template('map_1.html', map=utils.map_to_html(routes_map),
                           source=state["source"], destination=state["destination"])


@app.route('/map_2', methods=['GET', 'POST'])
@login_required
def map_2():
    """GET: show the police-station page. POST (JSON lat/long): find the nearest station and route."""
    state = get_state()
    if request.method == 'GET':
        return render_template('map_2.html')

    try:
        data_json = request.get_json()
        state["latitude"] = data_json.get('latitude')
        state["longitude"] = data_json.get('longitude')

        # Find nearest police station
        results = utils.get_nearest_police_stations(state["latitude"], state["longitude"]).get("results") or []
        if not results:
            return jsonify({"status": "error", "error": "No police station found within 10 km"}), 404
        # TrueWay also tags things like traffic cameras as police_station; prefer real stations
        nearest = next((r for r in results if "police" in r.get("name", "").lower()), results[0])
        state["police_station_name"] = nearest["name"]
        state["destination"] = nearest["address"]
        dest_lat, dest_long = nearest["location"]["lat"], nearest["location"]["lng"]

        # Create route map
        route = utils.get_route(state["latitude"], state["longitude"], dest_lat, dest_long)
        state["routes_map"] = utils.create_map(route)

        return jsonify({
            "status": "success",
            "police_station_name": state["police_station_name"],
            "destination": state["destination"],
            "map": utils.map_to_html(state["routes_map"])
        })

    except Exception as e:
        print(f'map_2 failed: {e}')
        return jsonify({"status": "error", "error": "Could not find a nearby police station"}), 502


@app.route('/map_2/police', methods=['GET', 'POST'])
@login_required
def map_2_police():
    """Simulate connecting to police"""
    state = get_state()
    message = None
    if request.method == 'POST':
        print("Contacting police...")
        message = "Connected to police"

    routes_map = state["routes_map"]
    return render_template('map_2.html',
                           police_station_name=state["police_station_name"],
                           destination=state["destination"],
                           map=utils.map_to_html(routes_map) if routes_map else None,
                           message=message)


def local_emergency_number(state: dict) -> str:
    """Local emergency number for the user's last known location (cached per location)."""
    lat, lng = state.get("latitude"), state.get("longitude")
    if lat is None or lng is None:
        return utils.DEFAULT_EMERGENCY_NUMBER
    key = (round(lat, 2), round(lng, 2))
    if state.get("emergency_key") != key:
        state["emergency_key"] = key
        state["emergency_info"] = utils.get_emergency_number(lat, lng)
    return state["emergency_info"]["number"]


@app.route('/emergency-number')
@login_required
def emergency_number():
    """Return the local emergency number for ?lat=&lng= (used by the SOS page)."""
    state = get_state()
    try:
        state["latitude"] = float(request.args["lat"])
        state["longitude"] = float(request.args["lng"])
    except (KeyError, ValueError):
        return jsonify({"number": utils.DEFAULT_EMERGENCY_NUMBER, "country": ""})
    number = local_emergency_number(state)
    return jsonify({"number": number, "country": state["emergency_info"].get("country", "")})


@app.route('/help', methods=['GET', 'POST'])
@login_required
def help_route():
    """Emergency SOS route to send email alert"""
    state = get_state()
    profile = current_profile()
    emergency_contact = profile.get("emergency")
    user_name = profile.get("username")

    if request.method == 'POST':
        print("SOS Request received!")
        # The page sends the browser's current location; fall back to the last known one
        payload = request.get_json(silent=True) or {}
        if payload.get("latitude") is not None and payload.get("longitude") is not None:
            state["latitude"], state["longitude"] = payload["latitude"], payload["longitude"]

        number = local_emergency_number(state)
        call_now = f"Please call your local emergency number ({number}) directly."

        if not emergency_contact:
            return jsonify({"status": "failed", "emergency_contact": None, "emergency_number": number,
                            "error": "No emergency contact set. Add an emergency contact email on the Dashboard. "
                                     + call_now}), 400

        try:
            utils.send_email(emergency_contact, user_name, state["latitude"], state["longitude"])
        except smtplib.SMTPAuthenticationError as e:
            print(f'SOS email login failed: {e}')
            return jsonify({"status": "failed", "emergency_contact": emergency_contact, "emergency_number": number,
                            "error": "The app's email account could not log in, so the alert was not sent. "
                                     + call_now}), 502
        except Exception as e:
            print(f'SOS email failed: {e}')
            return jsonify({"status": "failed", "emergency_contact": emergency_contact, "emergency_number": number,
                            "error": "The alert could not be sent. " + call_now}), 502

        return jsonify({"status": "success", "emergency_contact": emergency_contact, "emergency_number": number})

    return render_template('help.html',
                           emergency_contact=emergency_contact,
                           lat=state["latitude"],
                           long=state["longitude"])


# ---------------------- Run App ----------------------
if __name__ == '__main__':
    # Never enable the Werkzeug debugger by default: it allows remote code execution.
    app.run(debug=os.environ.get("FLASK_DEBUG", "0") == "1")
