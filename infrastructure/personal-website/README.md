# Mark Cheli Personal Website

A modern, interactive terminal-style personal website with Flask API backend, built with Vue3/NuxtJS and deployed using Docker containers with Traefik reverse proxy.

## 🚀 Live Services

- **Production Website**: https://www.markcheli.com
- **Development Site**: https://www-dev.ops.markcheli.com (LAN-only)
- **API Server**: https://flask.markcheli.com
- **API Proxy**: https://www.markcheli.com/api (proxied to Flask server)

## 🏗️ Architecture

```
┌─────────────────────┐    ┌──────────────────┐    ┌─────────────────┐
│   Vue3/NuxtJS      │    │   Flask API      │    │   Traefik       │
│   Terminal UI       │◄──►│   Server         │◄──►│   Reverse Proxy │
│   Port: 3000        │    │   Port: 5000     │    │   Ports: 80/443 │
└─────────────────────┘    └──────────────────┘    └─────────────────┘
         │                           │                       │
         └───────────────────────────┼───────────────────────┘
                                     │
                         ┌──────────────────┐
                         │   Docker         │
                         │   Network        │
                         └──────────────────┘
```

## 🎯 Features

### Terminal Interface
- **Interactive Commands**: `help`, `neofetch`, `weather`, `services`, etc.
- **Command History**: Arrow key navigation through command history
- **Auto-completion**: Tab completion for available commands
- **Real-time API Integration**: Weather data, profile info, service status
- **Responsive Design**: Works on desktop and mobile devices

### Flask API Backend
- **Health Endpoint**: `/health` - Service status
- **Weather API**: `/weather` - Current weather in Ashland, MA
- **Profile Data**: `/profile` - Personal and service information
- **Ping Service**: `/ping` - Simple connectivity test

### Infrastructure Features
- **SSL Certificates**: Automatic Let's Encrypt certificates
- **Health Monitoring**: Container health checks and recovery
- **Load Balancing**: Traefik-managed routing and SSL termination
- **Development Environment**: Separate dev stack for testing
- **API Proxy**: Same-origin requests via `/api` path

## 🛠️ Development Setup

### Prerequisites
- Docker and Docker Compose
- Node.js 18+ (for local development)
- Python 3.11+ (for API development)

### Local Development

1. **Clone and Setup**:
   ```bash
   cd infrastructure/personal-website
   ```

2. **Backend Development**:
   ```bash
   cd backend
   python -m venv venv
   source venv/bin/activate  # or `venv\Scripts\activate` on Windows
   pip install -r requirements.txt
   python app.py
   ```
   API will be available at http://localhost:5000

3. **Frontend Development**:
   ```bash
   cd frontend
   npm install
   npm run dev
   ```
   Website will be available at http://localhost:3000

### Environment Variables

Create a `.env` file in the project root:
```env
# Weather API (optional - uses demo data if not provided)
OPENWEATHER_API_KEY=your_api_key_here

# Development settings
NODE_ENV=development
FLASK_ENV=development
```

## 🧪 Testing

### Backend Tests
```bash
cd backend
source venv/bin/activate
pytest test_app.py -v

# With coverage
pytest --cov=app test_app.py
```

### Frontend Tests
```bash
cd frontend
npm test

# Watch mode
npm run test:watch

# Coverage
npm run test:coverage
```

## 🚢 Deployment

### Production Deployment

1. **Build and Deploy**:
   ```bash
   # From infrastructure/personal-website/
   docker-compose up -d --build
   ```

2. **Verify Services**:
   ```bash
   docker-compose ps
   docker-compose logs -f
   ```

3. **Health Checks**:
   ```bash
   curl https://flask.markcheli.com/health
   curl https://www.markcheli.com/
   ```

### Service Management

```bash
# Start all services
docker-compose up -d

# Stop all services
docker-compose down

# View logs
docker-compose logs -f [service_name]

# Rebuild and deploy
docker-compose up -d --build

# Scale services (if needed)
docker-compose up -d --scale website=2
```

## 📊 Monitoring & Health Checks

### Container Health
All containers include built-in health checks:
- **Flask API**: HTTP health endpoint monitoring
- **Website**: Application availability checks
- **Auto-recovery**: Containers restart on failure

### Service Monitoring
- **Traefik Dashboard**: https://traefik-local.ops.markcheli.com (LAN-only)
- **Container Status**: `docker-compose ps`
- **Resource Usage**: `docker stats`

## 🔧 API Reference

### Flask API Endpoints

#### `GET /health`
Health check endpoint
```json
{
  "status": "healthy",
  "timestamp": "2024-01-13T12:00:00Z",
  "service": "mark-cheli-api"
}
```

#### `GET /ping`
Simple ping test
```json
{
  "message": "pong",
  "timestamp": "2024-01-13T12:00:00Z",
  "server": "Mark Cheli Personal API"
}
```

#### `GET /weather`
Current weather in Ashland, MA
```json
{
  "location": "Ashland, MA",
  "temperature": 72,
  "feels_like": 75,
  "humidity": 65,
  "description": "Partly Cloudy",
  "wind_speed": 8,
  "timestamp": "2024-01-13T12:00:00Z",
  "source": "OpenWeatherMap"
}
```

#### `GET /profile`
Personal profile and services
```json
{
  "name": "Mark Cheli",
  "title": "Developer",
  "location": "Ashland, MA",
  "links": {
    "linkedin": "https://www.linkedin.com/in/mark-cheli-0354a163/",
    "github": "https://github.com/MCheli",
    "home_assistant": "https://home.markcheli.com"
  },
  "services": {
    "public": [...],
    "infrastructure": [...]
  }
}
```

## 🌐 Terminal Commands

| Command | Description |
|---------|-------------|
| `help` | Show all available commands |
| `clear` | Clear terminal screen |
| `neofetch` | Display system information with ASCII art |
| `whoami` | Show current user information |
| `ls` | List available services |
| `about` | About Mark Cheli |
| `contact` | Contact information |
| `weather` | Current weather in Ashland, MA |
| `services` | List public services |
| `infrastructure` | List infrastructure services (LAN-only) |
| `linkedin` | Open LinkedIn profile |
| `github` | Open GitHub profile |
| `home` | Open Home Assistant |
| `jupyter` | Open JupyterHub |
| `exit` | Exit message |

## 🔒 Security Features

- **HTTPS Everywhere**: All services use SSL certificates
- **LAN-only Services**: Development and admin interfaces restricted to local network
- **CORS Protection**: API endpoints properly configured
- **Container Security**: Non-root users in containers
- **Network Isolation**: Internal Docker networks for service communication

## 📁 Project Structure

```
infrastructure/personal-website/
├── backend/                 # Flask API server
│   ├── app.py              # Main Flask application
│   ├── test_app.py         # API tests
│   ├── requirements.txt    # Python dependencies
│   └── Dockerfile         # Backend container config
├── frontend/               # Vue3/NuxtJS website
│   ├── app.vue            # Main application component
│   ├── composables/       # Vue composables
│   │   └── useTerminal.ts # Terminal functionality
│   ├── assets/css/        # Styling
│   │   └── terminal.css   # Terminal theme
│   ├── tests/             # Frontend tests
│   ├── package.json       # Node.js dependencies
│   ├── nuxt.config.ts     # NuxtJS configuration
│   └── Dockerfile         # Frontend container config
├── docker-compose.yml      # Service orchestration
└── README.md              # This documentation
```

## 🚨 Troubleshooting

### Common Issues

1. **Services won't start**:
   ```bash
   # Check logs
   docker-compose logs -f

   # Rebuild containers
   docker-compose down
   docker-compose up -d --build
   ```

2. **SSL Certificate Issues**:
   ```bash
   # Check Traefik logs
   docker logs traefik

   # Verify DNS resolution
   nslookup www.markcheli.com
   nslookup flask.markcheli.com
   ```

3. **API Connection Issues**:
   ```bash
   # Test API directly
   curl https://flask.markcheli.com/health

   # Check internal connectivity
   docker-compose exec website curl http://flask-api:5000/health
   ```

4. **Frontend Build Issues**:
   ```bash
   # Clear node_modules and rebuild
   cd frontend
   rm -rf node_modules package-lock.json
   npm install
   npm run build
   ```

### Health Check Commands
```bash
# Comprehensive infrastructure test
python ../../scripts/test_infrastructure.py

# Check DNS configuration
python ../../scripts/infrastructure_dns.py audit

# Test individual services
curl -I https://www.markcheli.com
curl https://flask.markcheli.com/health
curl https://www.markcheli.com/api/weather
```

## 🔄 Updates & Maintenance

### Updating the Website
1. Make changes to source code
2. Test locally with `npm run dev` / `python app.py`
3. Run tests: `npm test` / `pytest`
4. Deploy: `docker-compose up -d --build`
5. Verify: Run infrastructure tests

### Adding New Features
1. Update backend API endpoints in `backend/app.py`
2. Add corresponding frontend commands in `composables/useTerminal.ts`
3. Write tests for new functionality
4. Update documentation
5. Deploy and test

## 📞 Support

- **Personal**: https://www.linkedin.com/in/mark-cheli-0354a163/
- **GitHub**: https://github.com/MCheli
- **Issues**: Create GitHub issues for bugs or feature requests

---

Built with ❤️ by Mark Cheli | Powered by Vue3, NuxtJS, Flask, and Docker