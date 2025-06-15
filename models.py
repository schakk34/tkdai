from flask_sqlalchemy import SQLAlchemy
from datetime import datetime

db = SQLAlchemy()

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