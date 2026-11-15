import html
import os
import requests
import folium
from geopy.geocoders import Nominatim
import pandas as pd
from email.message import EmailMessage
import ssl
import smtplib
from typing import Tuple, Dict, Any


# ---------------------- Configuration ----------------------
# Secrets are read from environment variables, never hardcoded.
# See .env.example for the full list.
def _require_env(name: str) -> str:
    value = os.environ.get(name)
    if not value:
        raise RuntimeError(f"Missing required environment variable: {name}")
    return value


# ---------------------- News Retrieval ----------------------
def get_news() -> Dict[str, Any]:
    """
    Fetch latest news articles related to 'women safety' using NewsAPI.
    
    Returns:
        JSON response from NewsAPI containing news articles.
    """
    url = "https://newsapi.org/v2/everything"
    params = {"q": "women safety"}
    headers = {"X-Api-Key": _require_env("NEWS_API_KEY")}
    response = requests.get(url, params=params, headers=headers, timeout=10)
    response.raise_for_status()
    return response.json()


# ---------------------- Geocoding ----------------------
def get_lat_long_from_address(address: str) -> Tuple[float, float]:
    """
    Convert a physical address into latitude and longitude coordinates.
    
    Args:
        address: The address to geocode.
    
    Returns:
        Tuple containing (latitude, longitude)
    """
    locator = Nominatim(user_agent='women_safety_app')
    location = locator.geocode(address)
    if not location:
        raise ValueError(f'Could not find the address "{address}"')
    return location.latitude, location.longitude


# ---------------------- Route Planning ----------------------
def get_route(lat1: float, long1: float, lat2: float, long2: float) -> requests.Response:
    """
    Get driving route between two coordinates using TrueWay Directions API.
    
    Args:
        lat1, long1: Starting point latitude and longitude
        lat2, long2: Destination latitude and longitude
    
    Returns:
        Response object from TrueWay Directions API
    """
    url = "https://trueway-directions2.p.rapidapi.com/FindDrivingRoute"
    querystring = {"stops": f"{lat1},{long1};{lat2},{long2}"}
    headers = {
        "X-RapidAPI-Key": _require_env("RAPIDAPI_KEY"),
        "X-RapidAPI-Host": "trueway-directions2.p.rapidapi.com"
    }
    response = requests.get(url, headers=headers, params=querystring, timeout=15)
    if response.status_code != 200:
        raise RuntimeError(f"Route service error {response.status_code}: {response.text[:200]}")
    return response


def create_map(response: requests.Response) -> folium.Map:
    """
    Create a folium map with a route plotted from API response.

    Args:
        response: Response object from get_route function.

    Returns:
        Folium Map object with route plotted.
    """
    route = response.json().get('route')
    if not route:
        raise ValueError("No route found between these locations")

    # TrueWay returns coordinates as [lat, lon], which is the order folium expects
    points = [(coord[0], coord[1]) for coord in route['geometry']['coordinates']]

    m = folium.Map()

    # Add markers for start and end points
    folium.Marker(points[0], tooltip='Start').add_to(m)
    folium.Marker(points[-1], tooltip='End').add_to(m)

    # Draw route polyline
    folium.PolyLine(points, color='blue', weight=5, opacity=0.8).add_to(m)

    # Fit map bounds
    df = pd.DataFrame(points, columns=['Lat', 'Lon'])
    sw = df[['Lat', 'Lon']].min().values.tolist()
    ne = df[['Lat', 'Lon']].max().values.tolist()
    m.fit_bounds([sw, ne])

    return m


def map_to_html(m: folium.Map, height: int = 500) -> str:
    """
    Render a folium map as a self-contained iframe for embedding in a web page.

    folium's _repr_html_() is meant for Jupyter and adds a
    "Make this Notebook Trusted" message, so it is not used here.
    """
    page = m.get_root().render()
    return (
        f'<iframe srcdoc="{html.escape(page, quote=True)}" '
        f'style="width:100%;height:{height}px;border:0;border-radius:12px;" '
        'loading="lazy" title="Route map"></iframe>'
    )


# ---------------------- Nearby Police Stations ----------------------
def get_nearest_police_stations(my_lat: float, my_long: float) -> Dict[str, Any]:
    """
    Find nearby police stations using TrueWay Places API.
    
    Args:
        my_lat, my_long: Current location latitude and longitude
    
    Returns:
        JSON response containing nearby police stations.
    """
    url = "https://trueway-places.p.rapidapi.com/FindPlacesNearby"
    querystring = {
        "location": f"{my_lat},{my_long}",
        "type": "police_station",
        "radius": "2000",  # in meters
        "language": "en"
    }
    headers = {
        "X-RapidAPI-Key": _require_env("RAPIDAPI_KEY"),
        "X-RapidAPI-Host": "trueway-places.p.rapidapi.com"
    }
    response = requests.get(url, headers=headers, params=querystring, timeout=15)
    return response.json()


# ---------------------- Email Alert ----------------------
def send_email(mail_receiver: str, name: str, lat: float, long: float) -> None:
    """
    Send an emergency alert email with the user's location.
    
    Args:
        mail_receiver: Recipient email address
        name: Name of the person requesting help
        lat, long: Coordinates of the person
    
    Notes:
        Requires the MAIL_SENDER and MAIL_PASSWORD (Gmail app password)
        environment variables.
    """
    print("************* Sending Email *************")
    
    mail_sender = _require_env("MAIL_SENDER")
    mail_password = _require_env("MAIL_PASSWORD")
    
    subject = 'Emergency Alert'
    if lat is not None and long is not None:
        location = f'({lat}, {long})\nMap: https://www.google.com/maps?q={lat},{long}'
    else:
        location = 'unknown (location access was not available)'
    body = f'Emergency Help Request from {name}.\nLast known location: {location}'

    em = EmailMessage()
    em['From'] = mail_sender
    em['To'] = mail_receiver
    em['Subject'] = subject
    em.set_content(body)

    context = ssl.create_default_context()
    with smtplib.SMTP_SSL('smtp.gmail.com', 465, context=context) as smtp:
        try:
            smtp.login(mail_sender, mail_password)
        except smtplib.SMTPServerDisconnected as e:
            # Gmail hangs up after rejecting the credentials, which smtplib reports as a disconnect
            raise smtplib.SMTPAuthenticationError(535, b"Gmail rejected MAIL_SENDER / MAIL_PASSWORD") from e
        smtp.send_message(em)
