#!/usr/bin/env python3
"""
Tests for Personal Website Flask API
"""
import pytest
import json
from app import app

@pytest.fixture
def client():
    """Test client fixture"""
    app.config['TESTING'] = True
    with app.test_client() as client:
        yield client

def test_health_endpoint(client):
    """Test health check endpoint"""
    response = client.get('/health')
    assert response.status_code == 200

    data = json.loads(response.data)
    assert data['status'] == 'healthy'
    assert 'timestamp' in data
    assert data['service'] == 'mark-cheli-api'

def test_ping_endpoint(client):
    """Test ping endpoint"""
    response = client.get('/ping')
    assert response.status_code == 200

    data = json.loads(response.data)
    assert data['message'] == 'pong'
    assert 'timestamp' in data
    assert data['server'] == 'Mark Cheli Personal API'

def test_weather_endpoint(client):
    """Test weather endpoint"""
    response = client.get('/weather')
    assert response.status_code == 200

    data = json.loads(response.data)
    assert data['location'] == 'Ashland, MA'
    assert 'temperature' in data
    assert 'humidity' in data
    assert 'description' in data
    assert 'timestamp' in data

    # Should return demo data since no API key is set in tests
    assert data['source'] == 'Demo Data'

def test_profile_endpoint(client):
    """Test profile endpoint"""
    response = client.get('/profile')
    assert response.status_code == 200

    data = json.loads(response.data)
    assert data['name'] == 'Mark Cheli'
    assert data['title'] == 'Developer'
    assert data['location'] == 'Ashland, MA'

    # Check required links
    links = data['links']
    assert 'linkedin' in links
    assert 'github' in links
    assert 'home_assistant' in links

    # Check services structure
    services = data['services']
    assert 'public' in services
    assert 'infrastructure' in services
    assert len(services['public']) > 0
    assert len(services['infrastructure']) > 0

def test_404_handler(client):
    """Test 404 error handler"""
    response = client.get('/nonexistent')
    assert response.status_code == 404

    data = json.loads(response.data)
    assert data['error'] == 'Endpoint not found'
    assert 'available_endpoints' in data

    # Check that main endpoints are listed
    endpoints = data['available_endpoints']
    assert '/ping' in endpoints
    assert '/health' in endpoints
    assert '/weather' in endpoints
    assert '/profile' in endpoints

def test_cors_headers(client):
    """Test CORS headers are present"""
    response = client.get('/ping')
    assert 'Access-Control-Allow-Origin' in response.headers

def test_weather_endpoint_structure(client):
    """Test weather endpoint returns proper structure"""
    response = client.get('/weather')
    data = json.loads(response.data)

    required_fields = ['location', 'temperature', 'humidity', 'description', 'timestamp', 'source']
    for field in required_fields:
        assert field in data

    # Temperature should be numeric
    assert isinstance(data['temperature'], (int, float))
    assert isinstance(data['humidity'], (int, float))

def test_profile_services_structure(client):
    """Test profile services have proper structure"""
    response = client.get('/profile')
    data = json.loads(response.data)

    # Check public services structure
    for service in data['services']['public']:
        assert 'name' in service
        assert 'url' in service
        assert 'description' in service
        assert service['url'].startswith('https://')

    # Check infrastructure services structure
    for service in data['services']['infrastructure']:
        assert 'name' in service
        assert 'url' in service
        assert 'description' in service
        assert service['url'].startswith('https://')

if __name__ == '__main__':
    pytest.main([__file__, '-v'])