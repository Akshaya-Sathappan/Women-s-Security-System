from flask import Flask, render_template, request, redirect, url_for, flash, jsonify
import json
import utils

app = Flask(__name__)

# ---------------------- Global Variables ----------------------
# Used across multiple routes for storing source/destination and map data
global source, destination, routes_map, police_station_name, latitude, longitude
source = destination = routes_map = police_station_name = latitude = longitude = None

# Load news articles
news_list = utils.get_news()["articles"][:6]

class Post:
    """Represents a news post with title and image"""
    def __init__(self, title, image_url):
        self.title = title
        self.image_url = image_url

# Load user data
with open("details.json", "r") as jf:
    data = json.load(jf)

# Prepare posts for display on homepage
posts = [Post(article["title"], article["urlToImage"]) for article in news_list]


# ---------------------- Routes ----------------------
@app.route('/', methods=['GET', 'POST'])
def login():
    """Login page route"""
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password1']
        print(f'Login attempt - username: {username}, password: {password}')

        # Simple authentication logic
        if username in data["login"] and data["login"][username] == password:
            return redirect(url_for('home'))

    return render_template('login.html')


@app.route('/signup', methods=['GET', 'POST'])
def signup():
    """User signup route"""
    if request.method == 'POST':
        email = request.form['email']
        username = request.form['username']
        password = request.form['password1']
        confirmpassword = request.form['confirmpassword']

        print(f'Signup - email: {email}, username: {username}, password: {password}, confirm: {confirmpassword}')

        # Save new user to JSON
        data["login"][username] = password
        with open("details.json", "w") as jfk:
            json.dump(data, jfk)

        return redirect(url_for('login'))

    return render_template('signup.html')


@app.route('/home', methods=['GET', 'POST'])
def home():
    """Home page route where user can enter source/destination"""
    global source, destination, routes_map
    if request.method == 'POST':
        source = request.form.get('source')
        destination = request.form.get('destination')
        print(f'Source: {source}, Destination: {destination}')

        # Get coordinates
        source_lat, source_long = utils.get_lat_long_from_address(source)
        dest_lat, dest_long = utils.get_lat_long_from_address(destination)

        # Get route and create map
        route = utils.get_route(source_lat, source_long, dest_lat, dest_long)
        routes_map = utils.create_map(route)

        return render_template('map_1.html', map=routes_map._repr_html_(), source=source, destination=destination)

    return render_template('home.html', posts=posts)


@app.route('/dashboard', methods=['GET', 'POST'])
def dashboard():
    """User profile and dashboard route"""
    user_details = data.get("profile", {})

    if request.method == 'POST':
        # Update profile
        username = request.form.get('username')
        email = request.form.get('email')
        contact_number = request.form.get('contact-number')
        home_address = request.form.get('home-address')
        emergency_number = request.form.get('emergency-number')

        print(f'Profile update - {username}, {email}, {contact_number}, {home_address}, {emergency_number}')

        profile_data = {
            "username": username,
            "email": email,
            "contact": contact_number,
            "address": home_address,
            "emergency": emergency_number.strip()
        }

        data["profile"] = profile_data
        with open("details.json", "w") as jfd:
            json.dump(data, jfd)

    return render_template('dashboard.html', user_details=user_details)


@app.route('/dashboard/profile-picture-update', methods=['POST'])
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
        return jsonify({'error': str(e)}), 500


@app.route('/map_1', methods=['GET', 'POST'])
def map_1():
    """Render the route map from source to destination"""
    return render_template('map_1.html', map=routes_map._repr_html_() if routes_map else None,
                           source=source, destination=destination)


@app.route('/map_2', methods=['POST'])
def map_2():
    """Get nearest police station and create map"""
    global police_station_name, destination, routes_map, latitude, longitude
    try:
        data_json = request.get_json()
        latitude = data_json.get('latitude')
        longitude = data_json.get('longitude')
        print(f'Latitude: {latitude}, Longitude: {longitude}')

        # Find nearest police station
        nearest = utils.get_nearest(latitude, longitude)["results"][0]
        police_station_name = nearest["name"]
        destination = nearest["address"]
        dest_lat, dest_long = nearest["location"]["lat"], nearest["location"]["lng"]

        # Create route map
        route = utils.get_route(latitude, longitude, dest_lat, dest_long)
        routes_map = utils.create_map(route)
        print(f'Nearest Police Station: {police_station_name}')

        return jsonify({
            "status": "success",
            "police_station_name": police_station_name,
            "destination": destination,
            "map": routes_map._repr_html_()
        })

    except Exception as e:
        return render_template('map_2.html', error=str(e))


@app.route('/map_2/police', methods=['GET', 'POST'])
def map_2_police():
    """Simulate connecting to police"""
    message = None
    if request.method == 'POST':
        print("Contacting police...")
        message = "Connected to police"

    return render_template('map_2.html',
                           police_station_name=police_station_name,
                           destination=destination,
                           map=routes_map._repr_html_() if routes_map else None,
                           message=message)


@app.route('/help', methods=['GET', 'POST'])
def help_route():
    """Emergency SOS route to send email alert"""
    global latitude, longitude
    emergency_contact = data["profile"].get("emergency")
    user_name = data["profile"].get("username")

    if request.method == 'POST':
        print("SOS Request received!")
        try:
            utils.send_email(emergency_contact, user_name, latitude, longitude)
        except Exception as e:
            print(e)
            return jsonify({"status": "Failed", "emergency_contact_number": emergency_contact})

        return jsonify({"status": "success", "emergency_contact_number": emergency_contact})

    return render_template('help.html',
                           emergency_contact_number=emergency_contact,
                           lat=latitude,
                           long=longitude)


# ---------------------- Run App ----------------------
if __name__ == '__main__':
    app.run(debug=True)
