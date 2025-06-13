from flask import Flask, render_template, Response, jsonify, request, redirect, url_for, flash, session
from flask_sqlalchemy import SQLAlchemy
from werkzeug.security import generate_password_hash, check_password_hash
from capture import Capture
from PracticeStudio import PracticeStudio
from white_belt_form import WhiteBeltForm
from functools import wraps
import os
from datetime import datetime
import cv2

app = Flask(__name__)
app.config['SECRET_KEY'] = os.urandom(24)
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///tkd.db'
db = SQLAlchemy(app)

# User model for authentication
class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False)
    password_hash = db.Column(db.String(120), nullable=False)
    belt_rank = db.Column(db.String(20), default='White Belt')
    progress = db.relationship('Progress', backref='user', lazy=True)

# Progress tracking model
class Progress(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    technique = db.Column(db.String(50), nullable=False)
    score = db.Column(db.Integer, nullable=False)
    date = db.Column(db.DateTime, nullable=False)

camera = None
practice_studio = None
white_belt_form = None

# Login required decorator
def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session:
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated_function

def init_camera():
    global camera, practice_studio
    if camera is None:
        try:
            camera = Capture(0)
            practice_studio = PracticeStudio(movement_type=1)  # Initialize with Front Kick
        except Exception as e:
            print(f"Error initializing camera: {e}")
            return False
    return True

def generate_frames():
    if not init_camera():
        return

    while True:
        frame = camera.get_frame()
        if frame is None:
            continue
            
        # Process frame with PracticeStudio or WhiteBeltForm
        frame = cv2.flip(frame, 1)  # Mirror effect
        
        if white_belt_form:
            # Use WhiteBeltForm processing
            frame = white_belt_form.process_frame(frame)
        elif practice_studio:
            # Use PracticeStudio processing
            frame_rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            results = practice_studio.pose.process(frame_rgb)
            
            if results.pose_landmarks:
                frame_rgb = cv2.cvtColor(frame_rgb, cv2.COLOR_RGB2BGR)
                practice_studio.mp_drawing.draw_landmarks(
                    frame_rgb,
                    results.pose_landmarks,
                    practice_studio.mp_pose.POSE_CONNECTIONS
                )
                frame = frame_rgb

        # Encode frame
        ret, buffer = cv2.imencode('.jpg', frame)
        if not ret:
            continue
            
        frame_bytes = buffer.tobytes()
        yield (b'--frame\r\n'
               b'Content-Type: image/jpeg\r\n\r\n' + frame_bytes + b'\r\n')

@app.route('/')
def landing():
    return render_template('landing.html')

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        user = User.query.filter_by(username=request.form['username']).first()
        if user and check_password_hash(user.password_hash, request.form['password']):
            session['user_id'] = user.id
            return redirect(url_for('dashboard'))
        flash('Invalid username or password')
    return render_template('login.html')

@app.route('/signup', methods=['GET', 'POST'])
def signup():
    if request.method == 'POST':
        hashed_password = generate_password_hash(request.form['password'])
        new_user = User(
            username=request.form['username'],
            email=request.form['email'],
            password_hash=hashed_password
        )
        db.session.add(new_user)
        db.session.commit()
        return redirect(url_for('login'))
    return render_template('signup.html')

@app.route('/logout')
def logout():
    session.pop('user_id', None)
    return redirect(url_for('landing'))

@app.route('/dashboard')
@login_required
def dashboard():
    user = User.query.get(session['user_id'])
    return render_template('dashboard.html', user=user)

@app.route('/practice')
@login_required
def practice():
    return render_template('practice.html')

@app.route('/rhythm')
@login_required
def rhythm():
    user = User.query.get(session['user_id'])
    return render_template('rhythm.html')

@app.route('/front-kick')
@login_required
def front_kick():
    global practice_studio
    practice_studio = PracticeStudio(1)
    return render_template('front_kick.html')

@app.route('/roundhouse-kick')
@login_required
def roundhouse_kick():
    global practice_studio
    practice_studio = PracticeStudio(2)
    return render_template('roundhouse_kick.html')

@app.route('/basic-punches')
@login_required
def basic_punches():
    global practice_studio
    practice_studio = PracticeStudio(3)
    return render_template('basic_punches.html')

@app.route('/poomsae')
@login_required
def poomsae():
    global practice_studio
    practice_studio = PracticeStudio(4)
    return render_template('poomsae.html')

@app.route('/white-belt-form')
@login_required
def white_belt_form_route():
    global white_belt_form, practice_studio
    practice_studio = None  # Disable practice studio
    white_belt_form = WhiteBeltForm()  # Initialize white belt form
    return render_template('white_belt_form.html')

@app.route('/progress')
@login_required
def progress():
    user = User.query.get(session['user_id'])
    progress_data = Progress.query.filter_by(user_id=user.id).all()
    return render_template('progress.html', progress=progress_data)

@app.route('/video_feed')
def video_feed():
    return Response(generate_frames(),
                    mimetype='multipart/x-mixed-replace; boundary=frame')

@app.route('/practice_video_feed')
def practice_video_feed():
    return Response(generate_frames(),
                    mimetype='multipart/x-mixed-replace; boundary=frame')

@app.route('/save_progress', methods=['POST'])
@login_required
def save_progress():
    data = request.get_json()
    new_progress = Progress(
        user_id=session['user_id'],
        technique=data['technique'],
        score=data['score'],
        date=datetime.now()
    )
    db.session.add(new_progress)
    db.session.commit()
    return jsonify({'success': True})

@app.route('/next_pose', methods=['POST'])
@login_required
def next_pose():
    if white_belt_form and white_belt_form.pose_confirmed:
        success = white_belt_form.next_pose()
        return jsonify({
            'success': success,
            'completed': white_belt_form.is_form_completed(),
            'current_pose': white_belt_form.get_current_pose_name()
        })
    return jsonify({'success': False, 'error': 'Current pose not confirmed yet'})

if __name__ == '__main__':
    with app.app_context():
        db.create_all()
    app.run(debug=True, port=5002)
