from extensions import db
from flask_login import UserMixin

class Vehicle(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    # 'cars_new', 'cars_used', 'trucks_tractors', etc.
    category = db.Column(db.String(50), nullable=False, index=True)
    brand = db.Column(db.String(100), nullable=False, index=True)
    model = db.Column(db.String(100), nullable=False, index=True)
    price = db.Column(db.Numeric(12, 2), nullable=False, default=0, index=True)
    price_cny = db.Column(db.Numeric(12, 2), default=None)  # Цена в юанях
    is_currency_fixed = db.Column(db.Boolean, default=False)  # Фиксирована ли цена в рублях
    year = db.Column(db.Integer, index=True)
    mileage = db.Column(db.Integer, index=True)
    body_type = db.Column(db.String(50), index=True) # sedan, suv, etc.
    engine_vol = db.Column(db.Float)
    power = db.Column(db.Integer)
    badge = db.Column(db.String(50))  # 'Новый', 'С пробегом'
    status = db.Column(db.String(20), default='active', index=True)  # 'active', 'sold'
    description = db.Column(db.Text)
    specifications = db.Column(db.JSON)  # List of dicts
    slug = db.Column(db.String(100), unique=True, nullable=False)
    created_at = db.Column(db.DateTime, default=db.func.now(), index=True)

    # Images relationship would be better, but for MVP we use a list
    main_image = db.Column(db.String(255))
    images = db.Column(db.JSON)  # List of image paths

    def __repr__(self):
        return f'<Vehicle {self.brand} {self.model}>'

class User(UserMixin):
    def __init__(self, id):
        self.id = id

class Lead(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    created_at = db.Column(db.DateTime, default=db.func.now(), index=True)
    name = db.Column(db.String(100))
    phone = db.Column(db.String(50))
    city = db.Column(db.String(100))
    item = db.Column(db.String(255))
    message = db.Column(db.Text)
    email = db.Column(db.String(120))
    status = db.Column(db.String(20), default='new', index=True) # new, processed, archived

    def __repr__(self):
        return f'<Lead {self.name} {self.phone}>'

class Article(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(255), nullable=False)
    slug = db.Column(db.String(255), unique=True, nullable=False)
    summary = db.Column(db.Text)
    content = db.Column(db.Text, nullable=False) # HTML content
    main_image = db.Column(db.String(255))
    created_at = db.Column(db.DateTime, default=db.func.now(), index=True)

    def __repr__(self):
        return f'<Article {self.title}>'

class Review(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    author_name = db.Column(db.String(100), nullable=False)
    rating = db.Column(db.Integer, default=5)
    text = db.Column(db.Text, nullable=False)
    source = db.Column(db.String(50), default='2ГИС')
    vehicle_model = db.Column(db.String(100)) # e.g. "Geely Monjaro 2023"
    is_published = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=db.func.now(), index=True)

    def __repr__(self):
        return f'<Review {self.author_name} - {self.rating} stars>'


class Visit(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    created_at = db.Column(db.DateTime, default=db.func.now(), index=True)
    ip_hash = db.Column(db.String(64), index=True) # Anonymized IP for privacy
    path = db.Column(db.String(255), index=True)
    user_agent = db.Column(db.String(512))
    referrer = db.Column(db.String(512))

    def __repr__(self):
        return f'<Visit {self.path} from {self.ip_hash[:8]}>'


class InspectionReport(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    report_uid = db.Column(db.String(50), unique=True, nullable=False, index=True)
    model_name = db.Column(db.String(150), nullable=False)
    year = db.Column(db.Integer)
    horsepower = db.Column(db.Integer)
    mileage = db.Column(db.Integer)
    price_cny = db.Column(db.Integer)
    description = db.Column(db.Text)
    images = db.Column(db.JSON)  # List of image paths
    created_at = db.Column(db.DateTime, default=db.func.now(), index=True)
    
    def __repr__(self):
        return f'<InspectionReport {self.report_uid}>'
