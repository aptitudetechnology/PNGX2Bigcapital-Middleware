#!/bin/bash
set -e

echo "Starting middleware initialization..."

# Wait for PostgreSQL to be ready
echo "Waiting for PostgreSQL to be ready..."
while ! pg_isready -h "${DB_HOST:-db}" -p "${DB_PORT:-5432}" -U "${DB_USER:-middleware_user}" > /dev/null 2>&1; do
    echo "PostgreSQL is not ready yet, waiting..."
    sleep 2
done

echo "PostgreSQL is ready!"

# Check if database tables exist, if not run SQL initialization
echo "Checking database schema..."
TABLES_EXIST=$(PGPASSWORD="${DB_PASSWORD:-middleware_password}" psql -h "${DB_HOST:-db}" -p "${DB_PORT:-5432}" -U "${DB_USER:-middleware_user}" -d "${DB_NAME:-middleware_db}" -t -c "SELECT COUNT(*) FROM information_schema.tables WHERE table_schema = 'public';" 2>/dev/null || echo "0")

if [ "$TABLES_EXIST" -eq "0" ]; then
    echo "Database tables not found. Initializing database schema..."
    
    # Run all SQL files in the db directory
    for sql_file in /app/db/*.sql; do
        if [ -f "$sql_file" ]; then
            echo "Executing $sql_file..."
            PGPASSWORD="${DB_PASSWORD:-middleware_password}" psql -h "${DB_HOST:-db}" -p "${DB_PORT:-5432}" -U "${DB_USER:-middleware_user}" -d "${DB_NAME:-middleware_db}" -f "$sql_file"
        fi
    done
    
    echo "Database initialization completed!"
else
    echo "Database tables already exist, skipping initialization."
fi

# Start the middleware application
echo "Starting paperless-bigcapital middleware..."
exec python middleware.py "$@"
