"""
SQLite → PostgreSQL Migration Script
=====================================
Migrates all data from a local site.db (SQLite) to a PostgreSQL database
on Railway using the DATABASE_URL environment variable.

Usage:
    DATABASE_URL=postgresql://... python migrate_sqlite_to_postgres.py

Tables migrated:
    vehicle, lead, article, review, visit, inspection_report
"""

import os
import sys
import json
import sqlite3
from datetime import datetime
from decimal import Decimal

# ─────────────────────────────────────────────────────────────────────────────
# 1. Validate environment before importing anything heavy
# ─────────────────────────────────────────────────────────────────────────────

SQLITE_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "site.db")
DATABASE_URL = os.environ.get("DATABASE_URL", "")

print("=" * 60)
print("  SQLite → PostgreSQL Migration")
print("=" * 60)

if not os.path.exists(SQLITE_PATH):
    print(f"\n[ERROR] SQLite file not found: {SQLITE_PATH}")
    print("  Make sure site.db is in the same directory as this script.")
    sys.exit(1)

if not DATABASE_URL:
    print("\n[ERROR] DATABASE_URL environment variable is not set.")
    print("  Export it before running:")
    print("  export DATABASE_URL=postgresql://user:pass@host:port/dbname")
    sys.exit(1)

if not DATABASE_URL.startswith("postgresql"):
    print(f"\n[ERROR] DATABASE_URL does not look like a PostgreSQL URL:")
    print(f"  {DATABASE_URL[:60]}...")
    print("  Expected format: postgresql://user:pass@host:port/dbname")
    sys.exit(1)

# Railway sometimes provides postgres:// — SQLAlchemy 2.x requires postgresql://
if DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql://", 1)
    print("[INFO] Rewrote postgres:// → postgresql:// for SQLAlchemy 2.x compatibility.")

print(f"\n[OK] SQLite source : {SQLITE_PATH}")
print(f"[OK] PostgreSQL URL: {DATABASE_URL[:40]}...  (truncated for safety)")

# ─────────────────────────────────────────────────────────────────────────────
# 2. Connect to SQLite
# ─────────────────────────────────────────────────────────────────────────────

print("\n[1/5] Connecting to SQLite …")
try:
    sqlite_conn = sqlite3.connect(SQLITE_PATH)
    sqlite_conn.row_factory = sqlite3.Row   # access columns by name
    sqlite_cur = sqlite_conn.cursor()
    print("      Connected.")
except Exception as e:
    print(f"[ERROR] Cannot open SQLite: {e}")
    sys.exit(1)

# ─────────────────────────────────────────────────────────────────────────────
# 3. Connect to PostgreSQL via SQLAlchemy (reuses the app's engine options)
# ─────────────────────────────────────────────────────────────────────────────

print("[2/5] Connecting to PostgreSQL …")
try:
    from sqlalchemy import create_engine, text
    pg_engine = create_engine(
        DATABASE_URL,
        pool_pre_ping=True,
        connect_args={"connect_timeout": 10},
    )
    with pg_engine.connect() as test_conn:
        test_conn.execute(text("SELECT 1"))
    print("      Connected.")
except Exception as e:
    print(f"[ERROR] Cannot connect to PostgreSQL: {e}")
    sys.exit(1)

# ─────────────────────────────────────────────────────────────────────────────
# 4. Bootstrap the PostgreSQL schema using the app's models
# ─────────────────────────────────────────────────────────────────────────────

print("[3/5] Bootstrapping PostgreSQL schema via Flask app …")
try:
    # Temporarily override DATABASE_URL so the app uses PostgreSQL
    os.environ["DATABASE_URL"] = DATABASE_URL

    # Patch config so it reads DATABASE_URL instead of hard-coding SQLite
    import config as _cfg
    _cfg.Config.SQLALCHEMY_DATABASE_URI = DATABASE_URL
    # PostgreSQL doesn't need the SQLite timeout connect_arg
    _cfg.Config.SQLALCHEMY_ENGINE_OPTIONS = {}

    from app import create_app
    from extensions import db

    flask_app = create_app(_cfg.Config)

    with flask_app.app_context():
        db.create_all()
    print("      Schema ready (all tables created / already exist).")
except Exception as e:
    print(f"[ERROR] Failed to bootstrap schema: {e}")
    sqlite_conn.close()
    sys.exit(1)

# ─────────────────────────────────────────────────────────────────────────────
# 5. Helper utilities
# ─────────────────────────────────────────────────────────────────────────────

def parse_json_column(value):
    """Return a Python object from a JSON column that may already be parsed."""
    if value is None:
        return None
    if isinstance(value, (list, dict)):
        return value
    try:
        return json.loads(value)
    except (json.JSONDecodeError, TypeError):
        return value  # leave as-is; let SQLAlchemy handle it


def parse_datetime(value):
    """Parse a datetime string from SQLite into a Python datetime object."""
    if value is None:
        return None
    if isinstance(value, datetime):
        return value
    for fmt in (
        "%Y-%m-%d %H:%M:%S.%f",
        "%Y-%m-%d %H:%M:%S",
        "%Y-%m-%dT%H:%M:%S.%f",
        "%Y-%m-%dT%H:%M:%S",
    ):
        try:
            return datetime.strptime(value, fmt)
        except (ValueError, TypeError):
            continue
    return None  # unparseable — let the DB use its default


def parse_bool(value):
    """Normalise SQLite integer booleans (0/1) to Python bool."""
    if value is None:
        return None
    return bool(value)


def parse_decimal(value):
    """Convert a numeric value to Decimal, or None."""
    if value is None:
        return None
    try:
        return Decimal(str(value))
    except Exception:
        return None


def rows_from_sqlite(table_name):
    """Return all rows from a SQLite table as a list of dicts."""
    try:
        sqlite_cur.execute(f"SELECT * FROM {table_name}")
        rows = sqlite_cur.fetchall()
        return [dict(row) for row in rows]
    except sqlite3.OperationalError as e:
        print(f"      [WARN] Table '{table_name}' not found in SQLite: {e}")
        return []


# ─────────────────────────────────────────────────────────────────────────────
# 6. Per-table migration logic
# ─────────────────────────────────────────────────────────────────────────────

def migrate_vehicle(rows, session):
    from models import Vehicle
    objects = []
    for r in rows:
        obj = Vehicle(
            id=r["id"],
            category=r.get("category"),
            brand=r.get("brand"),
            model=r.get("model"),
            price=parse_decimal(r.get("price")) or Decimal("0"),
            price_cny=parse_decimal(r.get("price_cny")),
            is_currency_fixed=parse_bool(r.get("is_currency_fixed")),
            year=r.get("year"),
            mileage=r.get("mileage"),
            body_type=r.get("body_type"),
            engine_vol=r.get("engine_vol"),
            power=r.get("power"),
            badge=r.get("badge"),
            status=r.get("status") or "active",
            description=r.get("description"),
            specifications=parse_json_column(r.get("specifications")),
            slug=r.get("slug"),
            created_at=parse_datetime(r.get("created_at")),
            main_image=r.get("main_image"),
            images=parse_json_column(r.get("images")),
        )
        objects.append(obj)
    session.bulk_save_objects(objects)


def migrate_lead(rows, session):
    from models import Lead
    objects = []
    for r in rows:
        obj = Lead(
            id=r["id"],
            created_at=parse_datetime(r.get("created_at")),
            name=r.get("name"),
            phone=r.get("phone"),
            city=r.get("city"),
            item=r.get("item"),
            message=r.get("message"),
            email=r.get("email"),
            status=r.get("status") or "new",
        )
        objects.append(obj)
    session.bulk_save_objects(objects)


def migrate_article(rows, session):
    from models import Article
    objects = []
    for r in rows:
        obj = Article(
            id=r["id"],
            title=r.get("title"),
            slug=r.get("slug"),
            summary=r.get("summary"),
            content=r.get("content") or "",
            main_image=r.get("main_image"),
            created_at=parse_datetime(r.get("created_at")),
        )
        objects.append(obj)
    session.bulk_save_objects(objects)


def migrate_review(rows, session):
    from models import Review
    objects = []
    for r in rows:
        obj = Review(
            id=r["id"],
            author_name=r.get("author_name") or "Anonymous",
            rating=r.get("rating") or 5,
            text=r.get("text") or "",
            source=r.get("source") or "2ГИС",
            vehicle_model=r.get("vehicle_model"),
            is_published=parse_bool(r.get("is_published")),
            created_at=parse_datetime(r.get("created_at")),
        )
        objects.append(obj)
    session.bulk_save_objects(objects)


def migrate_visit(rows, session):
    from models import Visit
    objects = []
    for r in rows:
        obj = Visit(
            id=r["id"],
            created_at=parse_datetime(r.get("created_at")),
            ip_hash=r.get("ip_hash"),
            path=r.get("path"),
            user_agent=r.get("user_agent"),
            referrer=r.get("referrer"),
        )
        objects.append(obj)
    session.bulk_save_objects(objects)


def migrate_inspection_report(rows, session):
    from models import InspectionReport
    objects = []
    for r in rows:
        obj = InspectionReport(
            id=r["id"],
            report_uid=r.get("report_uid"),
            model_name=r.get("model_name") or "",
            year=r.get("year"),
            horsepower=r.get("horsepower"),
            mileage=r.get("mileage"),
            price_cny=r.get("price_cny"),
            description=r.get("description"),
            images=parse_json_column(r.get("images")),
            created_at=parse_datetime(r.get("created_at")),
        )
        objects.append(obj)
    session.bulk_save_objects(objects)


# Map: SQLite table name → (migration function, friendly label)
TABLE_MIGRATORS = [
    ("vehicle",           migrate_vehicle,           "Vehicle"),
    ("lead",              migrate_lead,               "Lead"),
    ("article",           migrate_article,            "Article"),
    ("review",            migrate_review,             "Review"),
    ("visit",             migrate_visit,              "Visit"),
    ("inspection_report", migrate_inspection_report,  "InspectionReport"),
]

# ─────────────────────────────────────────────────────────────────────────────
# 7. Run migrations inside the Flask app context
# ─────────────────────────────────────────────────────────────────────────────

print("[4/5] Migrating data …\n")

summary = {}

with flask_app.app_context():
    for table_name, migrator_fn, label in TABLE_MIGRATORS:
        print(f"  → {label:<20}", end="", flush=True)

        rows = rows_from_sqlite(table_name)
        if not rows:
            print("0 rows (table empty or missing — skipped)")
            summary[label] = 0
            continue

        try:
            # Clear existing rows in PostgreSQL to avoid duplicate-key errors
            # on re-runs. Uses raw SQL so we don't need to load ORM objects.
            with pg_engine.begin() as conn:
                conn.execute(text(f"DELETE FROM {table_name}"))

            # Bulk-insert via SQLAlchemy ORM session
            with db.session.begin():
                migrator_fn(rows, db.session)

            # Sync the PostgreSQL sequence so future INSERTs don't collide
            # with the IDs we just inserted.
            with pg_engine.begin() as conn:
                conn.execute(
                    text(
                        f"SELECT setval(pg_get_serial_sequence('{table_name}', 'id'), "
                        f"COALESCE(MAX(id), 1)) FROM {table_name}"
                    )
                )

            print(f"{len(rows)} rows migrated ✓")
            summary[label] = len(rows)

        except Exception as e:
            print(f"FAILED ✗")
            print(f"      [ERROR] {e}")
            summary[label] = f"ERROR: {e}"

# ─────────────────────────────────────────────────────────────────────────────
# 8. Close SQLite and print summary
# ─────────────────────────────────────────────────────────────────────────────

sqlite_conn.close()

print("\n[5/5] Migration complete.\n")
print("─" * 60)
print(f"  {'Table':<22} {'Result'}")
print("─" * 60)
for label, result in summary.items():
    if isinstance(result, int):
        status = f"{result} rows" if result > 0 else "0 rows (skipped)"
    else:
        status = str(result)
    print(f"  {label:<22} {status}")
print("─" * 60)

errors = [k for k, v in summary.items() if isinstance(v, str) and v.startswith("ERROR")]
if errors:
    print(f"\n[WARN] {len(errors)} table(s) had errors: {', '.join(errors)}")
    print("  Check the output above for details.")
    sys.exit(1)
else:
    print("\n[SUCCESS] All tables migrated without errors.")
    print("  Your Railway PostgreSQL database is ready to use.\n")
