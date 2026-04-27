# AGENTS.md - migration_api

## Quick Start

```bash
# Run API server (development)
python -m app.main          # or: python app/run.py
# API available at http://localhost:8010 (or 8000)

# Run migration scripts
python migrate_citas.py    # Migrate appointments
python migrate_medicos.py # Migrate doctors
python preparar_mysql.py  # Prepare MySQL data
python migrar_postgres.py  # Migrate to PostgreSQL
```

## Architecture

- **Framework**: FastAPI with SQLAlchemy
- **Databases**: MySQL (legacy, read-only) → PostgreSQL (target)
- **Entry point**: `app/main.py` → `app.run.py`
- **Migration scripts**: Root-level Python files handle data migration

## Environment (.env)

- PostgreSQL: `localhost:5432` (user: admin, db: hospital)
- MySQL: `localhost:3306` (user: root, db: test_api)
- API runs on port `8010` (dev) or `8000` (prod)

## Key Files

| File | Purpose |
|------|---------|
| `mapeo_migracion.json` | ID mapping between MySQL/PostgreSQL |
| `preparar_mysql.py` | Extract and prepare data from MySQL |
| `migrar_postgres.py` | Load data into PostgreSQL |
| `deduplicar.py` | Remove duplicate records |
| `vincular_mysql.py` | Link related records |

## Dependencies

Install via: `pip install -r requirements.txt`
Key packages: `fastapi`, `sqlalchemy`, `pymysql`, `psycopg2`