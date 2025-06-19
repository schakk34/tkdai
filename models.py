from flask_sqlalchemy import SQLAlchemy
from datetime import datetime
import enum
from flask_login import UserMixin
from werkzeug.security import generate_password_hash, check_password_hash

db = SQLAlchemy()

class Role(enum.Enum):
    STUDENT = 'student'
    MASTER = 'master'
    ADMIN = 'admin'

# Update User model to work with Flask-Login
class User(UserMixin, db.Model):
    __tablename__ = 'user'

    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False)
    password_hash = db.Column(db.String(128), nullable=False)
    belt_rank = db.Column(db.String(20), default='White')
    role = db.Column(db.Enum(Role), default=Role.STUDENT, nullable=False)
    class_code = db.Column(db.String(10), unique=True, nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
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
                            primaryjoin="and_(User.id==LibraryItem.user_id, LibraryItem.item_type=='rhythm')",
                            lazy=True)

    sent_messages = db.relationship('Message', foreign_keys='Message.sender_id', backref='sender', lazy=True)
    received_messages = db.relationship('Message', foreign_keys='Message.receiver_id', backref='receiver', lazy=True)
    video_comments = db.relationship('VideoComment', backref='admin', lazy=True)
    created_events = db.relationship('CustomEvent', backref='creator', lazy=True)

    def is_student(self):
        return self.role == Role.STUDENT

    def is_master(self):
        return self.role == Role.MASTER

    def is_admin(self):
        return self.role == Role.ADMIN

    def is_authenticated(self):
        return True

    def is_active(self):
        return True

    def is_anonymous(self):
        return False

    def get_id(self):
        return str(self.id)

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


class Progress(db.Model):
    __tablename__ = 'progress'

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    technique = db.Column(db.String(50), nullable=False)
    score = db.Column(db.Integer, nullable=False)
    date = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)


class UserActivity(db.Model):
    __tablename__ = 'user_activity'

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    activity_date = db.Column(db.Date, nullable=False)
    activity_type = db.Column(db.String(50), nullable=False, default='login')
    details = db.Column(db.Text)

    __table_args__ = (
        db.UniqueConstraint('user_id', 'activity_date', 'activity_type', name='unique_user_activity'),
    )

class LibraryItem(db.Model):
    __tablename__ = 'library_item'

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    item_type = db.Column(db.String(20), nullable=False)  # 'video' or 'rhythm'
    title = db.Column(db.String(100), nullable=False)
    description = db.Column(db.Text)
    file_path = db.Column(db.String(255), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    form_type = db.Column(db.String(50))  # e.g. 'koryo'
    bpm = db.Column(db.Integer)
    markers = db.Column(db.JSON)
    analysis = db.Column(db.JSON)  # For rhythms: store timing markers

class Message(db.Model):
    __tablename__ = 'message'

    id = db.Column(db.Integer, primary_key=True)
    sender_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    receiver_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    content = db.Column(db.Text, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    is_read = db.Column(db.Boolean, default=False)

    def __repr__(self):
        return f'<Message {self.id}>'


class VideoComment(db.Model):
    __tablename__ = 'video_comment'

    id = db.Column(db.Integer, primary_key=True)
    video_id = db.Column(db.Integer, db.ForeignKey('library_item.id'), nullable=False)
    admin_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    timestamp = db.Column(db.Float, nullable=False)
    comment = db.Column(db.Text, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    # Annotation fields
    has_annotation = db.Column(db.Boolean, default=False)  # Whether this comment has a visual annotation
    annotation_x = db.Column(db.Float)  # X coordinate of circle center (percentage of video width)
    annotation_y = db.Column(db.Float)  # Y coordinate of circle center (percentage of video height)
    annotation_radius = db.Column(db.Float, default=5.0)  # Radius of circle (percentage of video width)
    annotation_color = db.Column(db.String(7), default='#ff0000')  # Color of circle (hex)
    
    def __repr__(self):
        return f'<VideoComment {self.id}>'


class CustomEvent(db.Model):
    __tablename__ = 'custom_event'

    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(200), nullable=False)
    description = db.Column(db.Text)
    event_date = db.Column(db.Date, nullable=False)
    event_time = db.Column(db.Time)
    location = db.Column(db.String(200))
    event_type = db.Column(db.String(50), default='general')
    created_by = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    is_all_day = db.Column(db.Boolean, default=True)
    send_to_all = db.Column(db.Boolean, default=True)
    target_students = db.Column(db.JSON)
    
    def __repr__(self):
        return f'<CustomEvent {self.title}>'


class PracticeVideo(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(200), nullable=False)
    description = db.Column(db.Text)
    video_url = db.Column(db.String(500), nullable=False)
    thumbnail_url = db.Column(db.String(500))  # Optional thumbnail
    duration = db.Column(db.Integer)  # Duration in seconds
    tags = db.Column(db.JSON)  # List of tags like ['sparring', 'poomsae', 'demo']
    creators = db.Column(db.JSON)  # List of creators like ['Kristopher', 'Master Kim']
    difficulty_level = db.Column(db.String(20), default='beginner')  # beginner, intermediate, advanced
    belt_level = db.Column(db.String(20))  # White, Yellow, Green, etc.
    created_at = db.Column(db.DateTime, default=datetime.now)
    views = db.Column(db.Integer, default=0)
    is_featured = db.Column(db.Boolean, default=False)
    
    def __repr__(self):
        return f'<PracticeVideo {self.title}>'


class VideoFavorite(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    video_id = db.Column(db.Integer, db.ForeignKey('practice_video.id'), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.now)
    
    # Relationships
    user = db.relationship('User', backref=db.backref('favorite_videos', lazy=True))
    video = db.relationship('PracticeVideo', backref=db.backref('favorited_by', lazy=True))
    
    # Ensure a user can only favorite a video once
    __table_args__ = (
        db.UniqueConstraint('user_id', 'video_id', name='unique_user_video_favorite'),
    )
    
    def __repr__(self):
        return f'<VideoFavorite {self.user_id}-{self.video_id}>'