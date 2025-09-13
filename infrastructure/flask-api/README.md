# Flask API Infrastructure

Standalone Flask API service that provides backend functionality for the personal website and other applications.

## Architecture

The Flask API runs as a separate Docker stack with two environments:

- **Production**: `flask.markcheli.com` - Public API accessible from internet
- **Development**: `flask-dev.ops.markcheli.com` - LAN-only API for development and testing

## Services

### Production API (`flask-api`)
- **URL**: https://flask.markcheli.com
- **Environment**: Production
- **Access**: Public (internet-accessible)
- **Container**: `mark-cheli-flask-api`
- **Port**: 5000

### Development API (`flask-api-dev`)
- **URL**: https://flask-dev.ops.markcheli.com
- **Environment**: Development
- **Access**: LAN-only
- **Container**: `mark-cheli-flask-api-dev`
- **Port**: 5000

## API Endpoints

- `GET /health` - Health check endpoint
- `GET /weather` - Weather data (requires OpenWeather API key)
- `GET /profile` - Developer profile information

## Environment Variables

Required in `.env` file:
- `OPENWEATHER_API_KEY` - OpenWeather API key for weather data

## Communication with Personal Website

The personal website services communicate with the Flask API:

- **Production Website** (`www.markcheli.com`) → **Production API** (`flask.markcheli.com`)
- **Development Website** (`www-dev.ops.markcheli.com`) → **Development API** (`flask-dev.ops.markcheli.com`)

Communication occurs via:
1. **Direct API calls**: Website makes HTTP requests to Flask API endpoints
2. **Proxy routing**: Website proxies `/api/*` requests to Flask API via Traefik

## Deployment

Deploy the Flask API stack:

```bash
# Deploy production and development Flask API
python scripts/deploy_via_ssh.py flask-api infrastructure/flask-api/docker-compose.yml
```

## Health Checks

Both services include health checks that verify the `/health` endpoint responds correctly.

## SSL Certificates

- **Production API**: Uses `*.markcheli.com` wildcard certificate
- **Development API**: Uses `*.ops.markcheli.com` wildcard certificate

## Network Configuration

- Connected to `traefik_default` network for reverse proxy routing
- No internal network needed since this is a standalone API service
- Personal website services connect to Flask API via external HTTP requests

## Dependencies

- Traefik reverse proxy for routing and SSL termination
- Manual wildcard SSL certificates
- OpenWeather API for weather data (optional)

## Monitoring

- Health check endpoints available at `/health`
- Integrated with infrastructure health tests
- Container health checks with 30-second intervals