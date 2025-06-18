from flask_sqlalchemy import SQLAlchemy
from datetime import datetime
from flask_login import UserMixin
from werkzeug.security import generate_password_hash, check_password_hash

db = SQLAlchemy()

# Update User model to work with Flask-Login
class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False)
    password_hash = db.Column(db.String(128))
    belt_rank = db.Column(db.String(20), default='White')
    is_admin = db.Column(db.Boolean, default=False)
    class_code = db.Column(db.String(10), unique=True)
    created_at = db.Column(db.DateTime, default=datetime.now)
    last_login = db.Column(db.DateTime)
    star_count = db.Column(db.Integer, default=0)
    
    # Relationships
    progress = db.relationship('Progress', backref='user', lazy=True)
    library_items = db.relationship('LibraryItem', backref='user', lazy=True)
    activities = db.relationship('UserActivity', backref='user', lazy=True)
    
    # Specific relationships for videos and rhythms
    videos = db.relationship('LibraryItem', 
                           primaryjoin="and_(User.id==LibraryItem.user_id, LibraryItem.item_type=='video')",
                           lazy=True)
    rhythms = db.relationship('LibraryItem',
                            primaryjoin="and_(User.id==LibraryItem.user_id, LibraryItem.item_type=='metronome')",
                            lazy=True)
    
    # Remove duplicate relationship definitions
    # sent_messages and received_messages are defined in the Message model

    def is_authenticated(self):
        return True

    def is_active(self):
        return True

    def is_anonymous(self):
        return False

    def get_id(self):
        return str(self.id)

    def is_administrator(self):
        return self.is_admin

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)
        
    def check_password(self, password):
        return check_password_hash(self.password_hash, password)

    def generate_class_code(self):
        """Generate a fixed class code"""
        code = "WHITE-TIGER"
        print(f"Generated code: {code}")  # Debug log
        
        # Set the class code
        self.class_code = code
        print(f"Set class code to: {self.class_code}")  # Debug log
        
        return code


# Progress tracking model
class Progress(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    technique = db.Column(db.String(50), nullable=False)
    score = db.Column(db.Integer, nullable=False)
    date = db.Column(db.DateTime, nullable=False)


# Add this after the Progress model
class UserActivity(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    activity_date = db.Column(db.Date, nullable=False)
    activity_type = db.Column(db.String(50), nullable=False, default='login')
    details = db.Column(db.Text)  # Add details field for messages and other information

    __table_args__ = (
        db.UniqueConstraint('user_id', 'activity_date', 'activity_type', name='unique_user_activity'),
    )

class LibraryItem(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    item_type = db.Column(db.String(20), nullable=False)  # 'video' or 'metronome'
    title = db.Column(db.String(100), nullable=False)
    description = db.Column(db.Text)
    file_path = db.Column(db.String(255), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    form_type = db.Column(db.String(50))  # For videos: 'koryo', 'keumgang', etc.
    bpm = db.Column(db.Integer)  # For metronomes
    markers = db.Column(db.JSON)  # For metronomes: store timing markers

class Message(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    sender_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    receiver_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    content = db.Column(db.Text, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.now)
    is_read = db.Column(db.Boolean, default=False)

    # Relationships with backrefs
    sender = db.relationship('User', foreign_keys=[sender_id], backref=db.backref('sent_messages', lazy=True))
    receiver = db.relationship('User', foreign_keys=[receiver_id], backref=db.backref('received_messages', lazy=True))

    def __repr__(self):
        return f'<Message {self.id}>'


class VideoComment(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    video_id = db.Column(db.Integer, db.ForeignKey('library_item.id'), nullable=False)
    admin_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    timestamp = db.Column(db.Float, nullable=False)  # Time in seconds
    comment = db.Column(db.Text, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.now)
    
    # Relationships
    video = db.relationship('LibraryItem', backref=db.backref('comments', lazy=True))
    admin = db.relationship('User', backref=db.backref('video_comments', lazy=True))
    
    def __repr__(self):
        return f'<VideoComment {self.id}>'