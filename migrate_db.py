import sqlite3

conn = sqlite3.connect('site.db')
cur = conn.cursor()

try:
    cur.execute('ALTER TABLE vehicle ADD COLUMN price_cny NUMERIC(12, 2)')
    print("Added price_cny column")
except sqlite3.OperationalError:
    print("Column price_cny already exists")

try:
    cur.execute('ALTER TABLE vehicle ADD COLUMN is_currency_fixed BOOLEAN DEFAULT 1')
    print("Added is_currency_fixed column")
except sqlite3.OperationalError:
    print("Column is_currency_fixed already exists")

try:
    cur.execute("ALTER TABLE vehicle ADD COLUMN status VARCHAR(20) DEFAULT 'active'")
    print("Added status column")
except sqlite3.OperationalError:
    print("Column status already exists")

try:
    cur.execute("ALTER TABLE vehicle ADD COLUMN badge VARCHAR(50)")
    print("Added badge column")
except sqlite3.OperationalError:
    print("Column badge already exists")

try:
    cur.execute("ALTER TABLE vehicle ADD COLUMN body_type VARCHAR(50)")
    cur.execute("CREATE INDEX idx_vehicle_body_type ON vehicle(body_type)")
    print("Added body_type column")
except sqlite3.OperationalError:
    print("Column body_type already exists")

try:
    cur.execute("ALTER TABLE vehicle ADD COLUMN created_at DATETIME DEFAULT CURRENT_TIMESTAMP")
    print("Added created_at column")
except sqlite3.OperationalError:
    print("Column created_at already exists")

# Auto-creating new performance indexes
try:
    cur.execute("CREATE INDEX IF NOT EXISTS ix_vehicle_year ON vehicle (year)")
    cur.execute("CREATE INDEX IF NOT EXISTS ix_vehicle_mileage ON vehicle (mileage)")
    cur.execute("CREATE INDEX IF NOT EXISTS ix_vehicle_status ON vehicle (status)")
    cur.execute("CREATE INDEX IF NOT EXISTS ix_lead_status ON lead (status)")
    cur.execute("CREATE INDEX IF NOT EXISTS ix_lead_created_at ON lead (created_at)")
    print("Added performance indexes")
except sqlite3.OperationalError as e:
    print(f"Error adding indexes: {e}")

# Auto-creating the new tables via Flask context
from extensions import db
from app import create_app

app = create_app()
with app.app_context():
    db.create_all()
    print("Database synced successfully for new models (like Review).")

conn.commit()
conn.close()
