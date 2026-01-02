# Personal JupyterHub Data Science Environment
# Based on jupyter/datascience-notebook with enhanced collaboration and SQL capabilities
FROM jupyter/datascience-notebook:python-3.11

# Switch to root for system-level installations
USER root

# Install system dependencies required for compilation
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    pkg-config \
    default-libmysqlclient-dev \
    && rm -rf /var/lib/apt/lists/*

# Install core collaboration packages (as root to avoid permission issues)
RUN pip install --no-cache-dir \
    ypy-websocket==0.12.4 \
    jupyter-collaboration==4.1.1

# Install SQL and database packages with enhanced UI features
RUN pip install --no-cache-dir \
    jupyterlab-sql-editor==1.6.1 \
    jupysql==0.11.1 \
    sqlalchemy==2.0.22 \
    duckdb==1.3.2 \
    psycopg[binary]==3.2.9 \
    PyMySQL==1.1.2 \
    ipython-sql==0.5.0 \
    sqlparse==0.4.4

# Install JupyterLab extensions with enhanced SQL features
RUN pip install --no-cache-dir \
    jupyterlab-lsp==5.2.0 \
    jupyterlab-git==0.41.0 \
    lckr-jupyterlab-variableinspector==3.2.1 \
    jupyterlab-execute-time \
    jupyterlab_code_formatter \
    jupyterlab-spreadsheet-editor

# Install core data visualization packages
RUN pip install --no-cache-dir \
    ipywidgets==8.1.1 \
    voila==0.5.11 \
    plotly==5.17.0 \
    dash==2.14.1

# Install enhanced data analysis packages (pandas-profiling is deprecated, use ydata-profiling)
RUN pip install --no-cache-dir \
    ydata-profiling==4.6.4 \
    sweetviz==2.3.1

# Install additional file format support
RUN pip install --no-cache-dir \
    openpyxl==3.1.2 \
    xlsxwriter==3.1.9

# Install cloud and web packages (let pip resolve compatible versions)
RUN pip install --no-cache-dir \
    boto3 \
    s3fs \
    requests \
    beautifulsoup4

# Install ML/AI packages (let pip resolve compatible versions)
RUN pip install --no-cache-dir \
    scikit-learn \
    xgboost \
    lightgbm

# Install big data processing (let pip resolve compatible versions)
RUN pip install --no-cache-dir \
    pyarrow \
    fastparquet \
    polars \
    "dask[complete]"

# AI integration packages removed to avoid dependency conflicts
# Uncomment if needed in the future:
# RUN pip install --no-cache-dir \
#     jupyter-ai==2.31.7 \
#     openai \
#     anthropic \
#     langchain \
#     langchain-openai \
#     langchain-anthropic

# Enable server extensions
RUN jupyter server extension enable jupyterlab_git
# RUN jupyter server extension enable jupyter_ai

# Build JupyterLab with all extensions
RUN jupyter lab build --dev-build=False --minimize=False

# Copy SQL configuration templates and demo notebook
COPY sql-connections-template.py /opt/sql-connections-template.py
COPY SQL-Demo-Template.ipynb /opt/SQL-Demo-Template.ipynb
RUN mkdir -p /home/jovyan/shared && \
    mkdir -p /home/jovyan/sql-configs && \
    cp /opt/sql-connections-template.py /home/jovyan/sql-configs/ && \
    cp /opt/SQL-Demo-Template.ipynb /home/jovyan/ && \
    fix-permissions /home/jovyan/shared && \
    fix-permissions /home/jovyan/sql-configs && \
    fix-permissions /home/jovyan/SQL-Demo-Template.ipynb

# Switch back to notebook user for runtime
USER ${NB_UID}

# Set default working directory
WORKDIR /home/jovyan

# Configure standalone JupyterLab with collaborative editing
ENV JUPYTER_ENABLE_LAB=yes

# Default command for standalone JupyterLab (not JupyterHub singleuser)
CMD ["start-notebook.sh", "--ServerApp.token=''", "--ServerApp.password=''", "--ServerApp.allow_origin=*"]