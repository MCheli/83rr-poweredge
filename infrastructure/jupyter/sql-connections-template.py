"""
SQL Database Connections Configuration Template
This file provides pre-configured database connections for easy selection in Jupyter notebooks.
Copy this to your user directory and customize with your database credentials.
"""

import sqlalchemy as sa
from sqlalchemy import create_engine
import os

# Database connection configurations
DATABASE_CONNECTIONS = {
    # Local Development Databases
    "local_postgres": {
        "name": "Local PostgreSQL",
        "engine": "postgresql",
        "connection_string": "postgresql://username:password@localhost:5432/database_name",
        "description": "Local PostgreSQL development database"
    },
    
    "local_mysql": {
        "name": "Local MySQL", 
        "engine": "mysql+pymysql",
        "connection_string": "mysql+pymysql://username:password@localhost:3306/database_name",
        "description": "Local MySQL development database"
    },
    
    "local_sqlite": {
        "name": "Local SQLite",
        "engine": "sqlite",
        "connection_string": "sqlite:///./data/local_database.db",
        "description": "Local SQLite file database"
    },
    
    # Cloud Databases
    "aws_rds_postgres": {
        "name": "AWS RDS PostgreSQL",
        "engine": "postgresql", 
        "connection_string": "postgresql://username:password@your-rds-endpoint.amazonaws.com:5432/database_name",
        "description": "AWS RDS PostgreSQL instance"
    },
    
    "gcp_postgres": {
        "name": "Google Cloud PostgreSQL",
        "engine": "postgresql",
        "connection_string": "postgresql://username:password@your-gcp-ip:5432/database_name", 
        "description": "Google Cloud SQL PostgreSQL"
    },
    
    # Analytics Databases
    "duckdb_local": {
        "name": "DuckDB Local",
        "engine": "duckdb",
        "connection_string": "duckdb:///./data/analytics.duckdb",
        "description": "Local DuckDB for analytics"
    },
    
    "duckdb_memory": {
        "name": "DuckDB In-Memory",
        "engine": "duckdb", 
        "connection_string": "duckdb:///:memory:",
        "description": "DuckDB in-memory database for fast analytics"
    }
}

# Common SQL query templates
SQL_TEMPLATES = {
    "explore_tables": "SELECT table_name FROM information_schema.tables WHERE table_schema = 'public';",
    "table_info": "SELECT column_name, data_type, is_nullable FROM information_schema.columns WHERE table_name = '{table_name}';",
    "row_count": "SELECT COUNT(*) as row_count FROM {table_name};",
    "sample_data": "SELECT * FROM {table_name} LIMIT 10;",
    "data_profile": """
        SELECT 
            COUNT(*) as total_rows,
            COUNT(DISTINCT {column_name}) as unique_values,
            COUNT(CASE WHEN {column_name} IS NULL THEN 1 END) as null_count,
            MIN({column_name}) as min_value,
            MAX({column_name}) as max_value
        FROM {table_name};
    """,
    "date_range": """
        SELECT 
            MIN({date_column}) as earliest_date,
            MAX({date_column}) as latest_date,
            COUNT(*) as total_records
        FROM {table_name};
    """
}

def get_database_engine(connection_name):
    """Get SQLAlchemy engine for a pre-configured connection"""
    if connection_name not in DATABASE_CONNECTIONS:
        raise ValueError(f"Unknown connection: {connection_name}")
    
    config = DATABASE_CONNECTIONS[connection_name]
    return create_engine(config["connection_string"])

def list_connections():
    """List available database connections"""
    print("Available Database Connections:")
    print("=" * 40)
    for key, config in DATABASE_CONNECTIONS.items():
        print(f"• {key}: {config['name']}")
        print(f"  {config['description']}")
        print()

def get_sql_template(template_name, **kwargs):
    """Get formatted SQL template"""
    if template_name not in SQL_TEMPLATES:
        available = ", ".join(SQL_TEMPLATES.keys())
        raise ValueError(f"Unknown template: {template_name}. Available: {available}")
    
    return SQL_TEMPLATES[template_name].format(**kwargs)

# Usage Examples:
"""
# 1. List available connections
list_connections()

# 2. Load the sql extension with a pre-configured connection
%load_ext sql
%sql $get_database_engine('local_postgres').url

# 3. Use SQL templates
query = get_sql_template('sample_data', table_name='users')
%sql $query

# 4. Quick connection switching
%sql $DATABASE_CONNECTIONS['duckdb_memory']['connection_string']
"""