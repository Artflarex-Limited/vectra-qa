# PostgreSQL Setup

Vectra QA uses PostgreSQL with the pgvector extension for structured data, vector search, and LLM response caching.

## Docker (Recommended)

The included `docker-compose.yml` starts PostgreSQL automatically:

```bash
docker compose up --build
```

This launches `ankane/pgvector:latest` with:

- Database: `vectra_qa`
- User: `vectra`
- Password: `vectra_dev_password_change_in_production` (override via `DB_PASSWORD`)
- Port: `5432`

Migrations in `./migrations/` are auto-applied on first start via the Docker `initdb` mechanism.

### Verify the Database

```bash
docker compose exec postgres pg_isready -U vectra -d vectra_qa
```

Expected output:

```
/vectra_qa accepting connections
```

## Manual Setup

If you prefer a local PostgreSQL instance:

### 1. Install PostgreSQL + pgvector

**macOS:**

```bash
brew install postgresql@16
brew install pgvector
```

**Ubuntu/Debian:**

```bash
sudo apt install postgresql-16 postgresql-16-pgvector
```

**Arch:**

```bash
sudo pacman -S postgresql postgresql-pgvector
```

### 2. Create Database and User

```bash
sudo -u postgres psql -c "CREATE USER vectra WITH PASSWORD 'your_password';"
sudo -u postgres psql -c "CREATE DATABASE vectra_qa OWNER vectra;"
sudo -u postgres psql -d vectra_qa -c "CREATE EXTENSION IF NOT EXISTS vector;"
```

### 3. Set `DATABASE_URL`

```bash
export DATABASE_URL="postgresql://vectra:your_password@localhost:5432/vectra_qa"
```

Add to your `.env` file for persistence.

## Running Migrations

### Docker Auto-Run

With Docker Compose, migrations run automatically when the `postgres` container first starts. Files in `./migrations/` are executed in alphabetical order.

### Manual via Script

For local development or after pulling schema updates:

```bash
python scripts/run_migrations.py
```

Options:

```bash
# Dry-run: see what would run without applying
python scripts/run_migrations.py --dry-run

# Check: exit 0 if all applied, 1 if pending (useful for CI)
python scripts/run_migrations.py --check
```

The script:

1. Reads `.sql` files from `migrations/`
2. Tracks applied migrations in the `migration_version` table
3. Applies only pending files in a transaction
4. Records each applied migration

## Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `DATABASE_URL` | `postgresql://vectra:vectra_dev_password_change_in_production@localhost:5432/vectra_qa` | PostgreSQL connection string |
| `VECTRA_BACKEND` | `dual` | Storage mode: `markdown`, `postgresql`, or `dual` |
| `DB_PASSWORD` | `vectra_dev_password_change_in_production` | PostgreSQL password (Docker Compose only) |

### Storage Backends

- **`markdown`** — Filesystem only. No PostgreSQL required. Legacy mode.
- **`postgresql`** — SQL only. Fast queries, no Markdown files.
- **`dual`** — Both. Markdown for human readability, PostgreSQL for queries and caching.

## Rollback

Rollback scripts live in `migrations/rollback/`.

### Roll Back the Latest Migration

```bash
# Apply the rollback SQL manually
psql "$DATABASE_URL" -f migrations/rollback/001_rollback.sql
```

### Full Database Reset (Docker)

```bash
docker compose down -v
docker compose up --build
```

This destroys all data and reapplies migrations from scratch.

### Full Database Reset (Manual)

```bash
# Drop and recreate
dropdb vectra_qa
createdb vectra_qa -O vectra
psql "$DATABASE_URL" -c "CREATE EXTENSION IF NOT EXISTS vector;"
python scripts/run_migrations.py
```

## Troubleshooting

### Connection Refused

```bash
# Check PostgreSQL is running
pg_isready -h localhost -p 5432

# Docker: check container health
docker compose ps postgres
```

### Migration Fails Mid-Run

Migrations run in transactions. If one fails, the transaction rolls back and the migration is not recorded. Fix the issue and re-run:

```bash
python scripts/run_migrations.py
```

### pgvector Extension Missing

```bash
psql "$DATABASE_URL" -c "CREATE EXTENSION IF NOT EXISTS vector;"
```
