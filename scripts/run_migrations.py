#!/usr/bin/env python3
"""PostgreSQL migration runner for Vectra QA.

Reads .sql files from the migrations/ directory, tracks applied migrations
in a migration_version table, and applies pending ones in order.

Usage:
    python scripts/run_migrations.py
    python scripts/run_migrations.py --dry-run
    python scripts/run_migrations.py --check
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path
from typing import List, Set, Tuple

try:
    import psycopg
    from psycopg import sql
    from psycopg.rows import dict_row

    HAS_PSYCOPG = True
except ImportError:
    HAS_PSYCOPG = False

try:
    import structlog

    logger = structlog.get_logger()
    HAS_STRUCTLOG = True
except ImportError:
    HAS_STRUCTLOG = False


DATABASE_URL = os.getenv(
    "DATABASE_URL",
    "postgresql://vectra:vectra_dev_password_change_in_production@localhost:5432/vectra_qa",
)

MIGRATIONS_DIR = Path(__file__).resolve().parent.parent / "migrations"

MIGRATION_TRACKING_TABLE = "migration_version"


def _log(msg: str, **kwargs) -> None:
    """Log a message via structlog if available, otherwise print."""
    if HAS_STRUCTLOG:
        logger.info(msg, **kwargs)
    else:
        extra = f" [{', '.join(f'{k}={v}' for k, v in kwargs.items())}]" if kwargs else ""
        print(f"[migrations] {msg}{extra}")


def _error(msg: str, **kwargs) -> None:
    """Log an error via structlog if available, otherwise print to stderr."""
    if HAS_STRUCTLOG:
        logger.error(msg, **kwargs)
    else:
        extra = f" [{', '.join(f'{k}={v}' for k, v in kwargs.items())}]" if kwargs else ""
        print(f"[migrations] ERROR: {msg}{extra}", file=sys.stderr)


def parse_args() -> argparse.Namespace:
    """Parse and return CLI arguments."""
    parser = argparse.ArgumentParser(
        description="Run PostgreSQL migrations for Vectra QA.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print pending migrations without executing them.",
    )
    parser.add_argument(
        "--check",
        action="store_true",
        help="Exit 0 if all migrations are applied, 1 if any are pending.",
    )
    return parser.parse_args()


def collect_migration_files(migrations_dir: Path) -> List[Path]:
    """Return all .sql files from migrations_dir, sorted alphabetically."""
    if not migrations_dir.exists():
        _error("migrations_directory_not_found", path=str(migrations_dir))
        sys.exit(1)

    sql_files = sorted(migrations_dir.glob("*.sql"))
    if not sql_files:
        _error("no_migration_files_found", path=str(migrations_dir))
        sys.exit(1)

    return sql_files


def ensure_tracking_table(conn: psycopg.Connection) -> None:
    """Create the migration_version tracking table if it does not exist."""
    conn.execute(
        sql.SQL(
            "CREATE TABLE IF NOT EXISTS {} ("
            "    id SERIAL PRIMARY KEY,"
            "    filename TEXT NOT NULL UNIQUE,"
            "    applied_at TIMESTAMPTZ DEFAULT NOW()"
            ")"
        ).format(sql.Identifier(MIGRATION_TRACKING_TABLE))
    )
    conn.commit()


def fetch_applied_filenames(conn: psycopg.Connection) -> Set[str]:
    """Return the set of filenames already recorded in the tracking table."""
    rows = conn.execute(
        sql.SQL("SELECT filename FROM {}").format(sql.Identifier(MIGRATION_TRACKING_TABLE))
    ).fetchall()
    return {row["filename"] for row in rows}


def run_single_migration(conn: psycopg.Connection, filepath: Path) -> None:
    """Execute a single migration file in a transaction and record it."""
    filename = filepath.name
    sql_content = filepath.read_text(encoding="utf-8")

    if not sql_content.strip():
        _log("migration_file_empty", filename=filename)
        return

    with conn.transaction():
        conn.execute(sql_content)
        conn.execute(
            sql.SQL("INSERT INTO {} (filename) VALUES (%s)").format(
                sql.Identifier(MIGRATION_TRACKING_TABLE)
            ),
            (filename,),
        )

    _log("migration_applied", filename=filename)


def build_pending_list(
    sql_files: List[Path], applied_filenames: Set[str]
) -> List[Tuple[Path, str]]:
    """Build a list of (filepath, filename) for migrations not yet applied."""
    pending: List[Tuple[Path, str]] = []
    for filepath in sql_files:
        filename = filepath.name
        if filename not in applied_filenames:
            pending.append((filepath, filename))
    return pending


def run_migrations(conn: psycopg.Connection, sql_files: List[Path]) -> bool:
    """Apply all pending migrations. Returns True if all succeeded."""
    applied_filenames = fetch_applied_filenames(conn)
    pending = build_pending_list(sql_files, applied_filenames)

    if not pending:
        _log("all_migrations_applied")
        return True

    _log("pending_migrations_found", count=len(pending))

    for filepath, filename in pending:
        try:
            run_single_migration(conn, filepath)
        except psycopg.Error as e:
            _error("migration_failed", filename=filename, error=str(e))
            return False

    return True


def check_migrations(conn: psycopg.Connection, sql_files: List[Path]) -> bool:
    """Check whether all migrations are applied. Returns True if all applied."""
    applied_filenames = fetch_applied_filenames(conn)
    pending = build_pending_list(sql_files, applied_filenames)

    if not pending:
        _log("check_passed_all_applied")
        return True

    _log("check_failed_pending_found", count=len(pending))
    for _, filename in pending:
        _log("  pending", filename=filename)

    return False


def dry_run_pending(conn: psycopg.Connection, sql_files: List[Path]) -> None:
    """Print pending migrations without executing them."""
    applied_filenames = fetch_applied_filenames(conn)
    pending = build_pending_list(sql_files, applied_filenames)

    if not pending:
        _log("dry_run_all_applied")
        return

    _log("dry_run_pending_migrations", count=len(pending))
    for filepath, filename in pending:
        size = len(filepath.read_text(encoding="utf-8"))
        _log("  would_run", filename=filename, size_bytes=size)


def main() -> int:
    """Entry point: parse args, connect, run or check migrations."""
    args = parse_args()

    if not HAS_PSYCOPG:
        _error("psycopg_not_installed")
        print("Install it with: pip install psycopg[binary]", file=sys.stderr)
        return 1

    sql_files = collect_migration_files(MIGRATIONS_DIR)

    try:
        conn = psycopg.connect(DATABASE_URL, row_factory=dict_row)
    except psycopg.OperationalError as e:
        _error("database_connection_failed", error=str(e))
        return 1

    try:
        ensure_tracking_table(conn)

        if args.check:
            return 0 if check_migrations(conn, sql_files) else 1

        if args.dry_run:
            dry_run_pending(conn, sql_files)
            return 0

        success = run_migrations(conn, sql_files)
        return 0 if success else 1

    finally:
        conn.close()


if __name__ == "__main__":
    sys.exit(main())
