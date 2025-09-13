# Claude Code Instructions

## Python Environment Setup

**IMPORTANT**: Always use the local virtual environment for Python development.

### Setup Commands:
```bash
# Create virtual environment (if not exists)
python3 -m venv venv

# Activate virtual environment (always do this first)
source venv/bin/activate

# Install/update dependencies
pip install -r requirements.txt
```

### Running Python Scripts:
Always activate the virtual environment before running any Python scripts:
```bash
source venv/bin/activate && python script_name.py
```

## Project Structure

- `scripts/deploy.sh` - Main deployment script (Python, despite .sh extension)
- `scripts/` - Utility scripts for server management
- `infrastructure/` - Local copies of docker-compose configurations from Portainer
- `requirements.txt` - Python dependencies
- `.env` - Environment configuration (contains API keys and URLs)
- `venv/` - Local Python virtual environment (do not commit to git)

## Script Management Policy

**IMPORTANT**: When Claude creates utility scripts that successfully interact with the server/APIs:

1. **DO NOT DELETE** successful scripts after use
2. **SAVE** them in the `scripts/` directory with descriptive names
3. **DOCUMENT** them in this file under "Available Scripts"
4. **ADD** usage examples and descriptions

This builds a library of useful tools for future sessions and tasks.

## Available Scripts

### Connectivity Testing
```bash
# Test SSH and Portainer API connectivity
source venv/bin/activate && python scripts/test_connectivity.py
```

### Container Management
```bash
# List all running containers and their status
source venv/bin/activate && python scripts/get_containers.py
```

### Stack Management
```bash
# List all Portainer stacks
source venv/bin/activate && python scripts/list_stacks.py

# Pull all stack configurations from Portainer to local infrastructure/ directory
source venv/bin/activate && python scripts/pull_stack_configs.py
```

## Environment Variables Required

The following environment variables must be set in `.env`:
- `PORTAINER_URL` - Portainer instance URL
- `PORTAINER_API_KEY` - API key for Portainer authentication
- `SSH_HOST` - Target server hostname
- `SSH_USER` - SSH username
- `PORTAINER_ENDPOINT_ID` - Portainer endpoint ID (default: 1)

## Git Usage and Security

### Security Requirements
**CRITICAL**: Never commit secrets or sensitive information to git.

- All environment files (`.env`, `stack.env`) are in `.gitignore`
- API keys, passwords, and tokens must only exist in environment files
- Review all changes before committing to ensure no secrets are included
- Use `git diff --cached` to review staged changes before committing

### Git Workflow with Claude

**Pre-commit Security Check:**
```bash
# Always check what will be committed
git status
git diff --cached

# Scan for potential secrets (if tools available)
rg -i "api[_-]?key|secret|password|token" --type-not=log .
```

**Safe Commit Process:**
```bash
# Stage files (Claude will do this automatically)
git add .

# Claude will create commits with this format:
# - Descriptive commit message explaining changes
# - Includes file/function references where appropriate
# - Ends with Claude signature for traceability
```

**Commit Message Format:**
Claude follows this commit message format:
- Clear, descriptive summary (50 chars or less)
- Detailed explanation of changes and reasoning
- References to specific files/functions modified
- Signed with Claude attribution

### Recovery and Rollback

**View Recent Changes:**
```bash
# View recent commits
git log --oneline -10

# See changes in specific commit
git show <commit-hash>

# Compare with previous version
git diff HEAD~1
```

**Rollback Changes:**
```bash
# Undo last commit (keep changes)
git reset --soft HEAD~1

# Undo last commit (discard changes)
git reset --hard HEAD~1

# Revert specific files
git checkout -- <file-path>

# Create revert commit
git revert <commit-hash>
```

### Ignore Patterns

The `.gitignore` includes these security patterns:
- Environment files: `.env`, `stack.env`, `*.env.*`
- Secrets directories: `secrets/`, `**/secrets/`
- Certificates: `*.key`, `*.pem`, `*.p12`, `*.keystore`
- Virtual environments: `venv/`
- Logs and backups: `logs/`, `backups/`, `*.log`