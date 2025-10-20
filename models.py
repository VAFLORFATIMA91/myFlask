# models.py
from flask_sqlalchemy import SQLAlchemy
from werkzeug.security import generate_password_hash, check_password_hash
from flask_login import UserMixin
from datetime import datetime

# Initialize SQLAlchemy object (it will be bound to the app later)
db = SQLAlchemy()

# --- User Mixin and Base User Classes ---
# UserMixin provides properties like is_authenticated, is_active, get_id()

class Guest(UserMixin, db.Model):
    __tablename__ = 'guest'
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    email = db.Column(db.String(100), unique=True, nullable=False)
    password_hash = db.Column(db.String(128), nullable=False)
    
    # Relationship to Reservations
    reservations = db.relationship('Reservation', backref='guest', lazy='dynamic')

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)
    
    # Flask-Login method to distinguish from Admin
    def get_id(self):
        # We return the simple integer ID for Guests
        return str(self.id)

    def __repr__(self):
        return f"<Guest {self.email}>"


class Admin(UserMixin, db.Model):
    __tablename__ = 'admin'
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(50), unique=True, nullable=False)
    password_hash = db.Column(db.String(128), nullable=False)

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)
    
    # Flask-Login method: Crucial for app.py's load_user function
    def get_id(self):
        # We prefix the ID to distinguish Admins from Guests in flask-login
        return f'admin_{self.id}'

    def __repr__(self):
        return f"<Admin {self.username}>"

# --- Resort Models ---

class Room(db.Model):
    __tablename__ = 'room'
    id = db.Column(db.Integer, primary_key=True)
    room_number = db.Column(db.String(10), unique=True, nullable=False)
    room_type = db.Column(db.String(50), nullable=False) # e.g., 'Standard', 'Deluxe', 'Suite'
    price = db.Column(db.Float, nullable=False) # Price per night
    status = db.Column(db.String(20), default='Available') # 'Available', 'Maintenance'
    
    # NEW COLUMN FOR IMAGE UPLOAD (As per app.py updates)
    image_file = db.Column(db.String(120), nullable=True, default=None) 

    # Relationship to Reservations
    reservations = db.relationship('Reservation', backref='room', lazy='dynamic')

    def __repr__(self):
        return f"<Room {self.room_number} - {self.room_type}>"


class Reservation(db.Model):
    __tablename__ = 'reservation'
    id = db.Column(db.Integer, primary_key=True)
    
    # Foreign Keys
    guest_id = db.Column(db.Integer, db.ForeignKey('guest.id'), nullable=False)
    room_id = db.Column(db.Integer, db.ForeignKey('room.id'), nullable=False)

    # Dates
    check_in = db.Column(db.Date, nullable=False)
    check_out = db.Column(db.Date, nullable=False)
    
    # Status
    status = db.Column(db.String(20), default='Reserved') # 'Reserved', 'Cancelled', 'Completed'
    
    # Timestamps
    date_booked = db.Column(db.DateTime, default=datetime.utcnow)

    def __repr__(self):
        return f"<Reservation {self.id} | Room {self.room_id} | Guest {self.guest_id}>"