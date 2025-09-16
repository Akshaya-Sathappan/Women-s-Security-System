import requests
import folium
from geopy.geocoders import Nominatim
import pandas as pd
from email.message import EmailMessage
import ssl
import smtplib
from typing import Tuple, Dict, Any


# ---------------------- News Retrieval ----------------------
def get_news() -> Dict[str, Any]:
    """
    Fetch latest news articles related to 'women safety' using NewsAPI.
    
    Returns:
        JSON response from NewsAPI containing news articles.
    """
    url = (
        "https://newsapi.org/v2/everything?"
        "q=women%20safety&apiKey=edaddbc3add54ca8920075e114cfec09"
    )
    response = requests.get(url)
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
        raise ValueError(f"Could not geocode address: {address}")
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
        "X-RapidAPI-Key": "d136a898admsh769a12d85806a56p1d0f24jsna19b023692ae",
        "X-RapidAPI-Host": "trueway-directions2.p.rapidapi.com"
    }
    return requests.get(url, headers=headers, params=querystring)


def create_map(response: requests.Response) -> folium.Map:
    """
    Create a folium map with a route plotted from API response.
    
    Args:
        response: Response object from get_route function.
    
    Returns:
        Folium Map object with route plotted.
    """
    route_coords = response.json()['route']['geometry']['coordinates']
    
    # Convert [lon, lat] to (lat, lon) tuples
    points = [(coord[1], coord[0]) for coord in route_coords]

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
        "X-RapidAPI-Key": "d136a898admsh769a12d85806a56p1d0f24jsna19b023692ae",
        "X-RapidAPI-Host": "trueway-places.p.rapidapi.com"
    }
    response = requests.get(url, headers=headers, params=querystring)
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
        Requires setting valid `mail_sender` and `mail_password` for Gmail SMTP.
    """
    print("************* Sending Email *************")
    
    mail_sender = ''  # Your Gmail address
    mail_password = ''  # Your Gmail app password
    
    subject = 'Emergency Alert'
    body = f'Emergency Help Request from {name} at location: ({lat}, {long})'

    em = EmailMessage()
    em['From'] = mail_sender
    em['To'] = mail_receiver
    em['Subject'] = subject
    em.set_content(body)

    context = ssl.create_default_context()
    with smtplib.SMTP_SSL('smtp.gmail.com', 465, context=context) as smtp:
        smtp.login(mail_sender, mail_password)
        smtp.send_message(em)
