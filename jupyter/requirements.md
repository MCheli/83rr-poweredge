# Requirements for JupyterHub Data Analysis Environment

## Project Objective
Create a "batteries included" JupyterHub environment comparable to DataLore or DeepNote for personal homelab deployment.

## Core Requirements

### 1. Real-time Collaboration
- **Current Status**: Partially implemented in original setup with `jupyter-collaboration` and `ypy-websocket`
- **Requirements**:
  - Multiple users can edit the same notebook simultaneously
  - Real-time cursor tracking and change synchronization
  - Conflict resolution for concurrent edits
  - Live sharing of notebook state across sessions

### 2. SQL Integration & Database Connectivity
- **Current Status**: Basic SQL support with `jupyterlab-sql-editor`, `jupysql`, `sqlalchemy`
- **Requirements**:
  - SQL blocks/cells within notebooks (not just magic commands)
  - Visual query builder interface
  - Connection management for multiple databases
  - Support for major databases: PostgreSQL, MySQL, SQLite, DuckDB
  - Query result visualization and export
  - Database schema browsing within JupyterLab

### 3. Pre-installed Data Analysis Libraries
- **Current Status**: Using `jupyter/datascience-notebook` base image
- **Essential Libraries**:
  - **Core**: pandas, numpy, scipy
  - **Visualization**: matplotlib, seaborn, plotly, bokeh
  - **Machine Learning**: scikit-learn, tensorflow, pytorch
  - **Database**: sqlalchemy, psycopg, mysqlclient, duckdb
  - **Utils**: requests, openpyxl, tqdm, ipywidgets

### 4. Enhanced DataFrame Support
- **Requirements**:
  - Rich DataFrame previews with sorting/filtering
  - Statistical summaries and data profiling
  - Interactive data exploration widgets
  - Memory usage optimization for large datasets
  - Export capabilities (CSV, Excel, Parquet, etc.)

### 5. AI Assistance Integration
- **Current Status**: Not implemented
- **Requirements**:
  - Claude API integration for code assistance and data analysis
  - ChatGPT/OpenAI API integration for alternative AI assistance
  - Jupyter extensions for seamless AI interaction within notebooks
  - Code generation, debugging, and explanation capabilities
  - Data analysis suggestions and automated insights
  - Natural language to code translation
  - Secure API key management for AI services

### 6. Multi-user Environment
- **Current Status**: JupyterHub with Docker spawner and user persistence
- **Requirements**:
  - Simple built-in user authentication (no external dependencies)
  - Self-contained user management within JupyterHub
  - Individual user workspaces with persistent storage
  - Resource limits per user
  - Admin controls and monitoring
  - Idle timeout and cleanup

## Technical Architecture

### Infrastructure Components
- **Proxy**: Configurable HTTP Proxy for load balancing
- **Hub**: JupyterHub 4.1.6 with PostgreSQL backend
- **Spawner**: DockerSpawner for isolated user environments
- **Database**: PostgreSQL for hub state
- **Networking**: Docker bridge network with Traefik integration

### Container Strategy
- Base image: `jupyter/datascience-notebook:python-3.11`
- Runtime package installation for collaboration features
- Persistent volumes for user data
- Environment isolation per user

## Feature Gaps to Address

### High Priority
1. **AI Assistance Implementation**
   - Jupyter AI extension installation and configuration
   - Claude and OpenAI API integration
   - Code completion and generation capabilities
   - Natural language query processing

2. **Enhanced SQL Experience**
   - Visual query builder
   - Better database connection management
   - SQL syntax highlighting and completion

3. **Improved Collaboration UI**
   - User presence indicators
   - Comment/annotation system
   - Version history and branching

4. **Advanced DataFrame Tools**
   - Data profiling extensions
   - Interactive filtering/sorting
   - Statistical analysis widgets

### Medium Priority
1. **Enhanced Authentication Features**
   - User signup capabilities with FirstUseAuthenticator or NativeAuthenticator
   - Password security verification and user blocking
   - Role-based access control

2. **Resource Management**
   - CPU/memory limits per user
   - Storage quotas
   - Usage monitoring dashboard

3. **Extension Ecosystem**
   - Git integration
   - Code formatting tools
   - Variable inspector
   - Table of contents generator

### Nice to Have
1. **Advanced Features**
   - Notebook scheduling/automation
   - Template library
   - Shared datasets repository
   - Integration with external data sources

## Compatibility Notes
- **Primary Focus**: Python and SQL
- **Optional**: Julia and R (if they don't complicate installation)
- **Target Similarity**: DataLore, DeepNote feature parity
- **Deployment**: Docker Compose on homelab server

## Security & Configuration Management

### Environment Variables & Secrets
**CRITICAL: This repository is public - never commit secrets to version control.**

- Use `example-stack.env` as a template to create your own `stack.env` file
- All secrets and configuration must be managed through environment variables
- `example-stack.env` must be kept up-to-date when new environment variables are added
- Generate strong, unique secrets using `openssl rand -hex 32` or `openssl rand -base64 32`
- Set restrictive file permissions (600) on your actual `stack.env` file
- Never put credentials directly in `docker-compose.yaml` files

### Required Environment Variables
- `CONFIGPROXY_AUTH_TOKEN`: Secure token for proxy authentication
- `POSTGRES_PASSWORD`: Database password for JupyterHub state
- `JUPYTER_PASSWORD`: Authentication password for dummy authenticator
- `JUPYTER_ADMIN_USER`: Administrative user account
- `JUPYTER_DOMAIN`: Domain name for Traefik reverse proxy
- `TZ`: Timezone configuration

## Success Metrics
- Users can collaboratively edit notebooks in real-time
- SQL queries can be written and executed with rich result display
- Data analysis workflows are streamlined with pre-installed tools
- Environment setup is reproducible and maintainable
- Security best practices are followed with proper secret management