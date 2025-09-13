#!/usr/bin/env python3
"""
Personal Website Flask API Server
Provides backend services for Mark Cheli's personal website
"""
import os
import requests
from datetime import datetime
from flask import Flask, jsonify, request
from flask_cors import CORS
from dotenv import load_dotenv

load_dotenv()

app = Flask(__name__)
CORS(app)

# Weather API configuration
WEATHER_API_KEY = os.getenv('OPENWEATHER_API_KEY', 'demo-key')
ASHLAND_LAT = 42.2612
ASHLAND_LON = -71.4633

@app.route('/health', methods=['GET'])
def health():
    """Health check endpoint"""
    return jsonify({
        'status': 'healthy',
        'timestamp': datetime.utcnow().isoformat(),
        'service': 'mark-cheli-api'
    })

@app.route('/ping', methods=['GET'])
def ping():
    """Simple ping endpoint"""
    return jsonify({
        'message': 'pong',
        'timestamp': datetime.utcnow().isoformat(),
        'server': 'Mark Cheli Personal API'
    })

@app.route('/weather', methods=['GET'])
def get_weather():
    """Get current weather for Ashland, MA"""
    try:
        # Use OpenWeatherMap API if key is available, otherwise return mock data
        if WEATHER_API_KEY and WEATHER_API_KEY != 'demo-key':
            weather_url = f"https://api.openweathermap.org/data/2.5/weather"
            params = {
                'lat': ASHLAND_LAT,
                'lon': ASHLAND_LON,
                'appid': WEATHER_API_KEY,
                'units': 'imperial'
            }

            response = requests.get(weather_url, params=params, timeout=5)
            response.raise_for_status()
            weather_data = response.json()

            return jsonify({
                'location': 'Ashland, MA',
                'temperature': round(weather_data['main']['temp']),
                'feels_like': round(weather_data['main']['feels_like']),
                'humidity': weather_data['main']['humidity'],
                'description': weather_data['weather'][0]['description'].title(),
                'wind_speed': round(weather_data['wind']['speed']),
                'timestamp': datetime.utcnow().isoformat(),
                'source': 'OpenWeatherMap'
            })
        else:
            # Return mock weather data for demo
            return jsonify({
                'location': 'Ashland, MA',
                'temperature': 72,
                'feels_like': 75,
                'humidity': 65,
                'description': 'Partly Cloudy',
                'wind_speed': 8,
                'timestamp': datetime.utcnow().isoformat(),
                'source': 'Demo Data',
                'note': 'Set OPENWEATHER_API_KEY environment variable for live data'
            })

    except requests.RequestException as e:
        return jsonify({
            'error': 'Weather service unavailable',
            'message': str(e),
            'timestamp': datetime.utcnow().isoformat()
        }), 503
    except Exception as e:
        return jsonify({
            'error': 'Internal server error',
            'message': str(e),
            'timestamp': datetime.utcnow().isoformat()
        }), 500

@app.route('/profile', methods=['GET'])
def get_profile():
    """Get Mark Cheli's profile information"""
    return jsonify({
        'name': 'Mark Cheli',
        'title': 'Developer',
        'location': 'Ashland, MA',
        'links': {
            'linkedin': 'https://www.linkedin.com/in/mark-cheli-0354a163/',
            'github': 'https://github.com/MCheli',
            'home_assistant': 'https://home.markcheli.com',
            'jupyter': 'https://jupyter.ops.markcheli.com',
            'portainer': 'https://portainer-local.ops.markcheli.com',
            'traefik': 'https://traefik-local.ops.markcheli.com',
            'logs': 'https://logs-local.ops.markcheli.com'
        },
        'services': {
            'public': [
                {'name': 'JupyterHub', 'url': 'https://jupyter.ops.markcheli.com', 'description': 'Data Science Environment'},
                {'name': 'Home Assistant', 'url': 'https://home.markcheli.com', 'description': 'Smart Home Control'},
                {'name': 'Personal Website', 'url': 'https://www.markcheli.com', 'description': 'Terminal Interface'}
            ],
            'infrastructure': [
                {'name': 'Portainer', 'url': 'https://portainer-local.ops.markcheli.com', 'description': 'Container Management (LAN)'},
                {'name': 'Traefik', 'url': 'https://traefik-local.ops.markcheli.com', 'description': 'Reverse Proxy Dashboard (LAN)'},
                {'name': 'OpenSearch', 'url': 'https://logs-local.ops.markcheli.com', 'description': 'Log Analytics (LAN)'}
            ]
        },
        'timestamp': datetime.utcnow().isoformat()
    })

@app.errorhandler(404)
def not_found(error):
    return jsonify({
        'error': 'Endpoint not found',
        'available_endpoints': ['/ping', '/health', '/weather', '/profile'],
        'timestamp': datetime.utcnow().isoformat()
    }), 404

if __name__ == '__main__':
    port = int(os.getenv('PORT', 5000))
    debug = os.getenv('FLASK_ENV') == 'development'

    print(f"🚀 Starting Mark Cheli Personal API on port {port}")
    print(f"📊 Debug mode: {debug}")
    print(f"🌤️  Weather API: {'Live' if WEATHER_API_KEY != 'demo-key' else 'Demo mode'}")

    app.run(host='0.0.0.0', port=port, debug=debug)