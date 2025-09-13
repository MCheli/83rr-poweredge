# Personal JupyterHub Data Science Environment

A comprehensive, Docker-based JupyterHub environment designed to replicate the "batteries included" experience of DataLore and DeepNote. Features real-time collaboration, SQL integration, and a rich data science stack for personal homelab deployment.

## Features

- 🤝 **Real-time Collaboration**: Multiple users can edit notebooks simultaneously
- 🗄️ **Advanced SQL Integration**: Database connection management UI, pre-configured connections, SQL template dropdowns, and enhanced query tools
- 📊 **Rich Data Science Stack**: Pre-installed pandas, plotly, scikit-learn, tensorflow, and more
- 🔍 **Enhanced DataFrame Support**: Data profiling, interactive exploration, and visualization
- 🤖 **AI Assistance**: Integrated Claude and ChatGPT support for code generation and analysis
- 🐳 **Containerized Users**: Isolated environments with persistent storage
- 🔐 **Multi-user Support**: User management with administrative controls
- 🌐 **Traefik Integration**: SSL termination and reverse proxy support

## Quick Start

### 1. Prerequisites

- Docker and Docker Compose installed
- Traefik reverse proxy running (for SSL/domain access)
- Domain name pointing to your server (optional, for external access)

### 2. Initial Setup

1. **Clone this repository:**
   ```bash
   git clone <your-repo-url>
   cd personal-jupyter
   ```

2. **Build the custom single-user image:**
   ```bash
   ./build.sh
   ```
   This creates a pre-built Docker image with all packages and extensions installed, ensuring stable and fast container startup.

2. **Create environment configuration:**
   ```bash
   cp example-stack.env stack.env
   chmod 600 stack.env
   ```

3. **Configure your environment variables in `stack.env`:**
   ```bash
   # Generate secure tokens
   CONFIGPROXY_AUTH_TOKEN=$(openssl rand -hex 32)
   POSTGRES_PASSWORD=$(openssl rand -base64 32)
   JUPYTER_PASSWORD=your-secure-password
   JUPYTER_ADMIN_USER=admin
   JUPYTER_DOMAIN=jupyter.yourdomain.com
   TZ=America/New_York
   ```

4. **Deploy the stack:**
   ```bash
   docker-compose --env-file stack.env up -d
   ```

5. **Monitor deployment:**
   ```bash
   docker-compose logs -f jupyterhub
   ```

### 3. Access Your JupyterHub

- **Local access**: http://localhost:8000
- **Domain access**: https://your-configured-domain.com
- **Login**: Use the username/password configured in your `stack.env`

## Docker Deployment Guide

### Environment Configuration

All sensitive configuration is managed through environment variables. Never commit secrets to version control.

**Required Variables:**
- `CONFIGPROXY_AUTH_TOKEN`: Secure proxy token
- `POSTGRES_PASSWORD`: Database password  
- `JUPYTER_PASSWORD`: User login password
- `JUPYTER_ADMIN_USER`: Administrative username
- `JUPYTER_DOMAIN`: External domain name
- `TZ`: Timezone setting
- `OPENAI_API_KEY`: OpenAI API key for ChatGPT integration (optional)
- `ANTHROPIC_API_KEY`: Anthropic API key for Claude integration (optional)

### Deployment Commands

```bash
# Start the stack
docker-compose --env-file stack.env up -d

# View logs
docker-compose logs -f

# Stop the stack
docker-compose down

# Update and restart
docker-compose pull
docker-compose --env-file stack.env up -d

# Clean restart (removes containers but preserves data)
docker-compose down && docker-compose --env-file stack.env up -d
```

### Volume Management

- `jupyterhub_data`: JupyterHub configuration and state
- `jupyterhub-user-{username}`: Individual user home directories
- `jupyterhub-shared`: Shared space accessible by all users
- `hub_db_data`: PostgreSQL database storage

### Resource Limits

Each user container is limited to:
- **Memory**: 4GB RAM
- **CPU**: 2 cores
- **Timeout**: 2 hours idle before auto-shutdown

## Enhanced SQL Features

### Database Connection Management

The environment includes advanced SQL capabilities with a user-friendly interface:

**Pre-configured Database Connections:**
- Local databases (PostgreSQL, MySQL, SQLite)
- Cloud databases (AWS RDS, Google Cloud SQL)
- Analytics databases (DuckDB local and in-memory)

**SQL Template Library:**
- Table exploration queries
- Data profiling templates
- Common analytics patterns
- Date range analysis queries

### Getting Started with SQL

1. **Open the SQL Demo Notebook:**
   - Navigate to `SQL-Demo-Template.ipynb` in your home directory
   - This notebook provides interactive dropdowns for database selection and SQL templates

2. **Configure Your Database Connections:**
   - Edit `/home/jovyan/sql-configs/sql-connections-template.py`
   - Update connection strings with your actual database credentials
   - Add new database connections as needed

3. **Using the SQL Interface:**
   - Use dropdown menus to select databases and SQL templates
   - Generate queries with parameter substitution
   - Switch between databases seamlessly
   - Execute queries with `%%sql` magic commands

**Supported Database Engines:**
- PostgreSQL (via psycopg)
- MySQL (via PyMySQL)  
- SQLite (built-in)
- DuckDB (for analytics)

## JupyterHub Initial Setup

### First Login

1. Navigate to your JupyterHub URL
2. Login with your configured admin credentials
3. Click "Start My Server" to launch your first notebook environment
4. Wait for package installation (first startup takes 5-10 minutes)

### Admin Controls

As an admin user, you can:
- **Control Panel** → **Admin**: Manage all users and servers
- **Start/Stop** other users' servers
- **Access** other users' notebooks (for support)
- **Monitor** resource usage and activity

### Adding Users

Currently configured with dummy authentication. To add users:
1. Users can sign up with any username
2. Use the same password configured in `JUPYTER_PASSWORD`
3. For production, consider upgrading to OAuth or LDAP authentication

## Feature Guide

### Real-time Collaboration

**Setup:**
- Collaboration is enabled by default in all notebooks
- Multiple users can edit the same notebook simultaneously

**Usage:**
1. Open any `.ipynb` file
2. Share the notebook URL with collaborators
3. All users see real-time cursors and edits
4. Changes are synchronized automatically

**Tips:**
- Use comments for communication: `# @username: check this out`
- Avoid simultaneous edits to the same cell
- Save frequently to prevent conflicts

### Database Connections & SQL

**Built-in SQL Support:**
- SQL cells with syntax highlighting
- Visual query results
- Connection management interface

**Setting Up Database Connections:**

1. **PostgreSQL Example:**
   ```python
   import sqlalchemy
   engine = sqlalchemy.create_engine('postgresql://user:password@host:port/database')
   %sql engine
   ```

2. **Using SQL Cells:**
   ```sql
   %%sql
   SELECT * FROM your_table LIMIT 10;
   ```

3. **DuckDB (Built-in Analytics DB):**
   ```python
   import duckdb
   %sql duckdb:///:memory:
   ```

**Supported Databases:**
- PostgreSQL (`psycopg[binary]`)
- MySQL (`mysqlclient`) 
- SQLite (`sqlite3`)
- DuckDB (`duckdb`)

### Data Science Features

**DataFrame Enhancement:**
```python
# Automatic data profiling
import pandas as pd
df = pd.read_csv('data.csv')
df.profile_report()  # pandas-profiling

# Interactive DataFrame exploration
import qgrid
qgrid.show_grid(df)
```

**Visualization Libraries:**
- **Static**: matplotlib, seaborn
- **Interactive**: plotly, bokeh
- **Dashboards**: plotly-dash, streamlit, voila

**Machine Learning:**
```python
# Pre-installed ML libraries
import sklearn
import tensorflow as tf
import torch
import xgboost as xgb
import lightgbm as lgb
```

**Data Engineering:**
```python
# Modern data tools
import polars as pl  # Fast DataFrame library
import dask.dataframe as dd  # Parallel computing
import pyarrow  # Columnar data format
```

### Development Tools

**Git Integration:**
- Built-in Git GUI in JupyterLab
- Clone repositories directly in the interface
- Commit, push, and pull from notebooks

**Variable Inspector:**
- View all active variables and their values
- Inspect DataFrames, arrays, and objects
- Available in the JupyterLab sidebar

**Code Quality:**
- Language Server Protocol (LSP) support
- Auto-completion and error detection
- Code formatting tools

### Advanced Features

**Shared Workspace:**
- `/home/jovyan/shared` directory accessible by all users
- Share datasets, notebooks, and resources
- Collaborative project space

**Extension Ecosystem:**
- Variable inspector for debugging
- Table of contents for navigation
- Git integration for version control
- SQL editor for database work

**Export Options:**
- Notebooks to HTML, PDF, slides
- Data to CSV, Excel, Parquet
- Dashboards via Voila

### AI Assistance

**Built-in AI Integration:**
- Jupyter AI extension with ChatGPT and Claude support
- Code completion and generation
- Natural language to code translation
- Data analysis suggestions

**Setup AI Services:**

1. **Get API Keys:**
   - OpenAI: https://platform.openai.com/api-keys
   - Anthropic: https://console.anthropic.com/

2. **Configure in your `stack.env`:**
   ```bash
   OPENAI_API_KEY=sk-your-openai-key-here
   ANTHROPIC_API_KEY=sk-ant-your-anthropic-key-here
   ```

**Using AI Assistance:**

1. **Load the Magic Extension (First Time Setup):**
   ```python
   # Run this once per notebook session
   %load_ext jupyter_ai_magics
   ```

2. **Magic Commands:**
   ```python
   # Generate code with AI (using OpenAI GPT-4)
   %%ai openai:gpt-4
   Create a function to analyze customer churn data
   
   # Using Claude
   %%ai anthropic:claude-3-sonnet-20240229
   Explain what this DataFrame shows and suggest improvements
   
   # Set output format for code
   %%ai openai:gpt-4 -f code
   Write a Python function to calculate correlation matrix
   ```

3. **Chat Interface:**
   - Open the AI chat panel in JupyterLab sidebar
   - Ask questions about your code or data
   - Get debugging help and optimization suggestions

4. **Format Options:**
   ```python
   # Available formats: code, math, html, text, images, json, markdown (default)
   %%ai openai:gpt-4 -f text
   Explain this in plain text
   
   %%ai anthropic:claude-3-sonnet-20240229 -f json
   Convert this data to JSON format
   ```

**Supported AI Models:**
- **OpenAI**: GPT-4, GPT-3.5-turbo, Code models
- **Anthropic**: Claude-3 (Opus, Sonnet, Haiku)
- **LangChain**: For advanced AI workflows and chains

## Troubleshooting

### Common Issues

**Startup Takes Too Long:**
- First launch installs packages and builds extensions (10-15 minutes)
- Check progress: `docker-compose logs -f jupyterhub`
- Look for "Building JupyterLab with extensions..." message
- Subsequent starts are much faster (2-3 minutes)

**Cannot Connect to Database:**
- Verify database credentials and network access
- Check if database allows connections from Docker containers
- Test connection with basic Python before using SQL magic

**Collaboration Not Working:**
- Ensure all users are on the same JupyterHub instance
- Check that `jupyter-collaboration` is installed
- Restart user servers if needed

**Out of Memory Errors:**
- Each user limited to 4GB RAM
- Process large datasets in chunks
- Use Dask for out-of-core processing

**AI Features Not Working:**
- Verify API keys are correctly set in `stack.env`
- Check API key validity and usage limits
- Restart user server after adding API keys: `Control Panel` → `Stop My Server` → `Start My Server`
- Wait for extension installation (first startup takes 10-15 minutes)
- Check server logs for extension building: `docker-compose logs -f jupyterhub`

**Extensions Not Visible in Left Panel:**
- Extensions install and build automatically on first server start
- Allow 10-15 minutes for full installation and JupyterLab build process
- Refresh browser page after build completes
- Restart user server if extensions still missing

### Maintenance

**Update Packages:**
```bash
# Recreate user containers with latest packages
docker-compose down
docker-compose --env-file stack.env up -d
```

**Backup Data:**
```bash
# Backup all user data and configuration
docker run --rm -v jupyterhub_data:/data -v $(pwd):/backup alpine tar czf /backup/jupyterhub-backup.tar.gz /data
```

**Monitor Resources:**
```bash
# Check container resource usage
docker stats
```

## Security Considerations

- Keep `stack.env` file secure (600 permissions)
- Regularly update container images
- Monitor user activity through admin panel
- Consider OAuth authentication for production
- Use strong, unique passwords for all accounts
- Regularly backup user data and configurations

## Support

For issues, feature requests, or contributions, please refer to the project repository. The configuration is designed to be self-contained and maintainable for homelab environments.
