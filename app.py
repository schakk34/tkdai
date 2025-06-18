import os
import os.path
import subprocess
import time
import math
from datetime import datetime
from functools import wraps

import cv2
import requests
from bs4 import BeautifulSoup
from flask import Flask, render_template, Response, jsonify, request, redirect, url_for, flash, send_file
from flask_login import LoginManager, login_user, logout_user, login_required, current_user
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename
import numpy as np

from PracticeStudio import PracticeStudio
from capture import Capture
from utils.form_utils.form_comparison import FormComparison
from utils.form_utils.form_analyzer import FormAnalyzer
from models import db, LibraryItem, User, Progress, UserActivity, Message
from white_belt_form import WhiteBeltForm

app = Flask(__name__)
app.config['SECRET_KEY'] = os.urandom(24)
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///tkdai.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['UPLOAD_FOLDER'] = 'static/uploads'
app.config['MAX_CONTENT_LENGTH'] = 64 * 1024 * 1024  # 16MB max file size

# Initialize database
db.init_app(app)

# Create database tables
with app.app_context():
    # Only create tables if they don't exist
    db.create_all()

# Initialize Flask-Login
login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'login'

@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))

camera = None
practice_studio = None
white_belt_form = None

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
    # Debug: Print all users in database
    print("\n=== Current Users in Database ===")
    all_users = User.query.all()
    for user in all_users:
        print(f"Username: {user.username}, Email: {user.email}, Is Admin: {user.is_admin}")
    print("===============================\n")

    # If user is already logged in, redirect to appropriate dashboard
    if current_user.is_authenticated:
        if current_user.is_administrator():
            return redirect(url_for('admin_dashboard'))
        return redirect(url_for('dashboard'))

    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')

        print(f"Login attempt for username: {username}")  # Debug log

        # Check if user exists
        user = User.query.filter_by(username=username).first()

        if user:
            print(f"User found: {user.username}, is_admin: {user.is_admin}")  # Debug log

            # Verify password
            if check_password_hash(user.password_hash, password):
                print(f"Password check passed for user: {username}")  # Debug log

                # Log in the user
                login_user(user)
                print(f"User logged in successfully: {username}")  # Debug log

                # Update last login time
                user.last_login = datetime.now()

                # Record login activity
                today = datetime.now().date()
                activity = UserActivity.query.filter_by(
                    user_id=user.id,
                    activity_date=today,
                    activity_type='login'
                ).first()

                if not activity:
                    activity = UserActivity(
                        user_id=user.id,
                        activity_date=today,
                        activity_type='login'
                    )
                    db.session.add(activity)

                db.session.commit()
                print(f"Login activity recorded for user: {username}")  # Debug log

                flash('Login successful!')

                # Determine where to redirect
                next_page = request.args.get('next')
                if not next_page or not next_page.startswith('/'):
                    if user.is_administrator():
                        print(f"Redirecting admin user {username} to admin dashboard")  # Debug log
                        next_page = url_for('admin_dashboard')
                    else:
                        print(f"Redirecting regular user {username} to user dashboard")  # Debug log
                        next_page = url_for('dashboard')

                print(f"Redirecting to: {next_page}")  # Debug log
                return redirect(next_page)
            else:
                print(f"Password check failed for user: {username}")  # Debug log
                flash('Invalid password')
        else:
            print(f"No user found with username: {username}")  # Debug log
            flash('User not found')

        return render_template('login.html')

    return render_template('login.html')

@app.route('/signup', methods=['GET', 'POST'])
def signup():
    if request.method == 'POST':
        # Check if username already exists
        if User.query.filter_by(username=request.form['username']).first():
            flash('Username already exists. Please choose a different one.')
            return render_template('signup.html')

        # Check if email already exists
        if User.query.filter_by(email=request.form['email']).first():
            flash('Email already registered. Please use a different email or login.')
            return render_template('signup.html')

        # Verify class code
        class_code = request.form.get('class_code')
        admin_user = User.query.filter_by(class_code=class_code, is_admin=True).first()
        if not admin_user:
            flash('Invalid class code. Please check with your instructor.')
            return render_template('signup.html')

        try:
            hashed_password = generate_password_hash(request.form['password'])
            new_user = User(
                username=request.form['username'],
                email=request.form['email'],
                password_hash=hashed_password,
                belt_rank=request.form.get('belt_rank', 'White')
            )
            db.session.add(new_user)
            db.session.commit()
            flash('Account created successfully! Please login.')
            return redirect(url_for('login'))
        except Exception as e:
            db.session.rollback()
            flash('An error occurred while creating your account. Please try again.')
            return render_template('signup.html')

    return render_template('signup.html')

@app.route('/logout')
@login_required
def logout():
    logout_user()
    return redirect(url_for('landing'))

def get_wt_calendar_events():
    try:
        # URL of the WT calendar page - using the current year and month
        current_date = datetime.now()
        year = current_date.year
        month = current_date.month
        url = f"https://m.worldtaekwondo.org/calendar/cld_list.html?cym={year}-{month}"

        headers = {
            'User-Agent': 'Mozilla/5.0 (iPhone; CPU iPhone OS 14_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/14.0 Mobile/15E148 Safari/604.1'
        }
        print(f"Fetching WT calendar from: {url}")
        response = requests.get(url, headers=headers)
        response.raise_for_status()

        print(f"Response status code: {response.status_code}")
        print(f"Response content length: {len(response.text)}")

        soup = BeautifulSoup(response.text, 'html.parser')
        events = []

        # Find the calendar section
        calendar_section = soup.find('div', class_='calendar_bx')
        if calendar_section:
            print("Found calendar section")

            # Find the events list
            events_list = calendar_section.find('ul', class_='date_day')
            if events_list:
                print("Found events list")

                # Find all event items
                event_items = events_list.find_all('li')
                print(f"Found {len(event_items)} event items")

                for item in event_items:
                    try:
                        # Get the event link and details
                        link_tag = item.find('a')
                        if not link_tag:
                            print("No link tag found in event item")
                            continue

                        # Get the event name from the title span
                        title_span = link_tag.find('span', class_='title')
                        if not title_span:
                            print("No title span found in event item")
                            continue

                        event_name = title_span.get_text(strip=True)

                        # Get the date from the day span
                        day_span = link_tag.find('span', class_='day')
                        date = day_span.get_text(strip=True) if day_span else 'TBD'

                        # Get the event link
                        event_link = link_tag.get('href', '')
                        if event_link and not event_link.startswith('http'):
                            event_link = f"https://m.worldtaekwondo.org/calendar/{event_link}"

                        print(f"Processing event: {event_name}")
                        print(f"Found date: {date}")

                        # Clean up the date format
                        if date != 'TBD':
                            try:
                                # Handle date ranges (e.g., "1 ~ 7")
                                if '~' in date:
                                    start_day = date.split('~')[0].strip()
                                    # Use the start day for sorting
                                    date = f"{current_date.year}-{current_date.month}-{start_day}"
                                    date_obj = datetime.strptime(date, '%Y-%m-%d')
                                    date = date_obj.strftime('%B %d, %Y')
                                else:
                                    # Single day
                                    date = f"{current_date.year}-{current_date.month}-{date}"
                                    date_obj = datetime.strptime(date, '%Y-%m-%d')
                                    date = date_obj.strftime('%B %d, %Y')
                                print(f"Formatted date: {date}")
                            except Exception as e:
                                print(f"Error formatting date: {str(e)}")

                        event_data = {
                            'name': event_name,
                            'date': date,
                            'location': 'TBD',  # Location not available in the list view
                            'link': event_link
                        }
                        print(f"Added event: {event_data}")
                        events.append(event_data)
                    except Exception as e:
                        print(f"Error processing event item: {str(e)}")
                        continue
            else:
                print("Events list not found")
        else:
            print("Calendar section not found")

        # Sort events by date if possible
        try:
            def get_date_key(event):
                if event['date'] == 'TBD':
                    return datetime.max
                try:
                    return datetime.strptime(event['date'], '%B %d, %Y')
                except:
                    return datetime.max

            events.sort(key=get_date_key)
        except Exception as e:
            print(f"Error sorting events: {str(e)}")

        print(f"Total events found: {len(events)}")
        return events
    except Exception as e:
        print(f"Error fetching WT calendar: {str(e)}")
        return []

@app.route('/dashboard')
@login_required
def dashboard():
    print(f"Accessing dashboard for user: {current_user.username}")  # Debug log

    # Get WT calendar events
    wt_events = get_wt_calendar_events()

    return render_template('dashboard.html',
                         user=current_user,
                         wt_events=wt_events)

@app.route('/practice')
@login_required
def practice():
    return render_template('practice.html')

@app.route('/rhythm')
@login_required
def rhythm():
    return render_template('rhythm.html', user=current_user)

# @app.route('/front-kick')
# @login_required
# def front_kick():
#     global practice_studio
#     practice_studio = PracticeStudio(1)
#     return render_template('front_kick.html')
#
# @app.route('/roundhouse-kick')
# @login_required
# def roundhouse_kick():
#     global practice_studio
#     practice_studio = PracticeStudio(2)
#     return render_template('roundhouse_kick.html')
#
# @app.route('/basic-punches')
# @login_required
# def basic_punches():
#     global practice_studio
#     practice_studio = PracticeStudio(3)
#     return render_template('basic_punches.html')
#
# @app.route('/poomsae')
# @login_required
# def poomsae():
#     global practice_studio
#     practice_studio = PracticeStudio(4)
#     return render_template('poomsae.html')

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
    progress_data = Progress.query.filter_by(user_id=current_user.id).all()
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
        user_id=current_user.id,
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

@app.route('/form-comparison')
@login_required
def form_comparison():
    return render_template('form_comparison.html')

@app.route('/process-form-comparison', methods=['POST'])
@login_required
def process_form_comparison():
    if 'video' not in request.files:
        return jsonify({'error': 'No video file provided'}), 400

    video_file = request.files['video']
    form_type = request.form.get('formType')

    if not form_type:
        return jsonify({'error': 'Form type not specified'}), 400

    if video_file.filename == '':
        return jsonify({'error': 'No selected file'}), 400

    try:
        # Create user-specific upload directory
        user_upload_dir = os.path.join(app.config['UPLOAD_FOLDER'], str(current_user.id))
        os.makedirs(user_upload_dir, exist_ok=True)

        # Save the uploaded video
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        video_filename = f"{form_type}_{timestamp}.webm"
        video_path = os.path.join(user_upload_dir, video_filename)
        video_file.save(video_path)

        # Convert webm to mp4
        mp4_filename = f"{form_type}_{timestamp}.mp4"
        mp4_path = os.path.join(user_upload_dir, mp4_filename)
        subprocess.run([
            'ffmpeg', '-i', video_path,
            '-c:v', 'libx264', '-preset', 'medium', '-crf', '23',
            '-c:a', 'aac', '-b:a', '128k',
            mp4_path
        ], check=True)

        # Process rhythm file if provided
        rhythm_path = None
        if 'rhythm' in request.files and request.files['rhythm'].filename:
            rhythm_file = request.files['rhythm']
            rhythm_filename = f"{form_type}_rhythm_{timestamp}.mp3"
            rhythm_path = os.path.join(user_upload_dir, rhythm_filename)
            rhythm_file.save(rhythm_path)

        # Check if ideal data exists for this form
        ideal_data_path = os.path.join(app.static_folder, 'data', 'forms', 'pose_data', f'{form_type}_ideal_data.json')
        if not os.path.exists(ideal_data_path):
            return jsonify({'error': f'No ideal data found for {form_type}'}), 400

        # Process the video
        form_comparison = FormComparison()
        result_video_path, feature_vectors = form_comparison.process_user_video(
            user_video_path=mp4_path,
            output_path=os.path.join(user_upload_dir, f"{form_type}_comparison_{timestamp}.mp4"),
            audio_path=rhythm_path
        )

        # Calculate average score and convert to percentage
        avg_score = np.mean([fv['overall_score'] for fv in feature_vectors])
        score_percentage = round(avg_score * 100, 1)

        # Calculate stars earned (1-5)
        stars_earned = math.ceil((score_percentage / 100) * 5) - 1

        # Ensure minimum of 1 star
        stars_earned = max(1, stars_earned)

        # Update user's star count
        current_user.star_count += stars_earned
        db.session.commit()

        # Log the activity
        try:
            # Check if an activity already exists for today
            existing_activity = UserActivity.query.filter_by(
                user_id=current_user.id,
                activity_date=datetime.now().date(),
                activity_type='form_practice'
            ).first()

            if existing_activity:
                # Update the existing activity
                existing_activity.details = f'Practiced {form_type} form and earned {stars_earned} stars'
            else:
                # Create new activity
                activity = UserActivity(
                    user_id=current_user.id,
                    activity_type='form_practice',
                    details=f'Practiced {form_type} form and earned {stars_earned} stars',
                    activity_date=datetime.now().date()
                )
                db.session.add(activity)

            db.session.commit()
        except Exception as e:
            print(f"Error logging activity: {str(e)}")
            db.session.rollback()

        return jsonify({
            'success': True,
            'video_url': url_for('static', filename=f'uploads/{current_user.id}/{os.path.basename(result_video_path)}'),
            'score': score_percentage,
            'stars_earned': stars_earned,
            'total_stars': current_user.star_count,
            'all_feature_vectors': feature_vectors
        })

    except Exception as e:
        print(f"Error processing form comparison: {str(e)}")
        return jsonify({'error': str(e)}), 500

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in {'mp4', 'mov', 'avi', 'mp3', 'wav'}

# Initialize the form analyzer
form_analyzer = FormAnalyzer()

# @app.route('/analyze-form', methods=['POST'])
# @login_required
# def analyze_form():
#     try:
#         data = request.get_json()
#         video_url = data.get('video_url')
#
#         if not video_url:
#             return jsonify({'error': 'No video URL provided'}), 400
#
#         # Analyze the form using HuggingFace API
#         result = form_analyzer.analyze_form(video_url)
#
#         if result['success']:
#             return jsonify(result)
#         else:
#             return jsonify({'error': result['error']}), 500
#
#     except Exception as e:
#         print(f"Error in analyze-form endpoint: {str(e)}")
#         return jsonify({'error': 'Failed to analyze form'}), 500

@app.route('/analyze-form', methods=['POST'])
@login_required
def analyze_form():
    data = request.get_json()
    fvs = data.get('feature_vectors')
    if not fvs:
        return jsonify({'success': False, 'error': 'No feature vectors received'}), 400

    analyzer = FormAnalyzer(provider='gemini')
    feedback = analyzer.analyze(fvs)
    return jsonify({'success': True, 'feedback': feedback})

@app.route('/library')
@login_required
def library():
    videos = LibraryItem.query.filter_by(
        user_id=current_user.id,
        item_type='video'
    ).order_by(LibraryItem.created_at.desc()).all()

    rhythms = LibraryItem.query.filter_by(
        user_id=current_user.id,
        item_type='rhythm'
    ).order_by(LibraryItem.created_at.desc()).all()

    return render_template('library.html', videos=videos, rhythms=rhythms)

@app.route('/library/save', methods=['POST'])
@login_required
def save_to_library():
    try:
        data = request.json
        item_type = data.get('type')
        title = data.get('title')
        description = data.get('description', '')
        file_path = data.get('file_path')

        print(f"Saving to library - Type: {item_type}, Title: {title}, File: {file_path}")  # Debug log

        if not all([item_type, title]):
            return jsonify({'success': False, 'error': 'Missing required fields'})

        # Convert the file path to a URL
        if file_path.startswith('blob:') or file_path.startswith('http'):
            # Handle blob URLs (from recordings)
            file_path = file_path
        else:
            # Convert relative path to URL
            filename = os.path.basename(file_path)
            file_path = url_for('serve_upload', filename=filename, _external=True)
            print(f"Converted file path to URL: {file_path}")  # Debug log
        # Create new library item
        item = LibraryItem(
            user_id=current_user.id,
            item_type=item_type,
            title=title,
            description=description,
            file_path=file_path
        )

        # Add type-specific data
        if item_type == 'video':
            item.form_type = data.get('form_type')
        elif item_type == 'rhythm':
            item.markers = data.get('markers')

        db.session.add(item)
        db.session.commit()

        print(f"Successfully saved item to library with ID: {item.id}")  # Debug log
        return jsonify({'success': True, 'id': item.id})
    except Exception as e:
        print(f"Error saving to library: {str(e)}")  # Debug log
        return jsonify({'success': False, 'error': str(e)})

@app.route('/library/delete/<int:item_id>', methods=['DELETE'])
@login_required
def delete_library_item(item_id):
    try:
        item = LibraryItem.query.get_or_404(item_id)

        # Verify ownership
        if item.user_id != current_user.id:
            return jsonify({'success': False, 'error': 'Unauthorized'})

        # Delete file if it exists
        if os.path.exists(item.file_path):
            os.remove(item.file_path)

        db.session.delete(item)
        db.session.commit()

        return jsonify({'success': True})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})

@app.route('/get_user_activity')
@login_required
def get_user_activity():
    try:
        # Get all login activities for the current user
        activities = UserActivity.query.filter_by(
            user_id=current_user.id,
            activity_type='login'
        ).all()

        # Format activities for FullCalendar
        events = []
        for activity in activities:
            events.append({
                'title': 'Logged in',
                'start': activity.activity_date.isoformat(),
                'allDay': True
            })

        return jsonify(events)
    except Exception as e:
        print(f"Error fetching user activity: {str(e)}")
        return jsonify([])

@app.route('/static/uploads/<path:filename>')
@login_required
def serve_upload(filename):
    try:
        # Ensure the file is within the uploads directory
        upload_dir = app.config['UPLOAD_FOLDER']
        file_path = os.path.join(upload_dir, filename)
        print(upload_dir)
        print(filename)

        print(f"Attempting to serve file: {file_path}")  # Debug log

        # Check if file exists and is within the uploads directory
        if not os.path.exists(file_path):
            print(f"File not found: {file_path}")  # Debug log
            return "File not found", 404

        if not os.path.abspath(file_path).startswith(os.path.abspath(upload_dir)):
            print(f"Access denied: {file_path}")  # Debug log
            return "Access denied", 403

        # Determine the correct mimetype based on file extension
        ext = os.path.splitext(filename)[1].lower()
        mimetype = {
            '.mp4': 'video/mp4',
            '.webm': 'video/webm',
            '.mov': 'video/quicktime',
            '.avi': 'video/x-msvideo'
        }.get(ext, 'application/octet-stream')

        print(f"Serving file: {file_path} with mimetype: {mimetype}")  # Debug log

        response = send_file(
            file_path,
            mimetype=mimetype,
            as_attachment=False,
            conditional=True
        )

        # Add CORS headers
        response.headers['Access-Control-Allow-Origin'] = '*'
        response.headers['Access-Control-Allow-Methods'] = 'GET, OPTIONS'
        response.headers['Access-Control-Allow-Headers'] = 'Content-Type'

        # Add cache control headers
        response.headers['Cache-Control'] = 'no-cache, no-store, must-revalidate'
        response.headers['Pragma'] = 'no-cache'
        response.headers['Expires'] = '0'

        return response
    except Exception as e:
        print(f"Error serving file: {str(e)}")  # Debug log
        return str(e), 500

# Add admin required decorator
def admin_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not current_user.is_authenticated or not current_user.is_administrator():
            flash('You do not have permission to access this page.')
            return redirect(url_for('dashboard'))
        return f(*args, **kwargs)
    return decorated_function

# Add admin routes
@app.route('/admin')
@login_required
@admin_required
def admin_dashboard():
    # Get all users except admins
    users = User.query.filter_by(is_admin=False).all()
    return render_template('admin/dashboard.html', users=users)

@app.route('/admin/users')
@login_required
@admin_required
def admin_users():
    users = User.query.filter_by(is_admin=False).all()
    return render_template('admin/users.html', users=users)

@app.route('/admin/user/<int:user_id>')
@login_required
@admin_required
def admin_user_detail(user_id):
    user = User.query.get_or_404(user_id)
    if user.is_admin:
        flash('Cannot view admin user details.')
        return redirect(url_for('admin_users'))

    # Get message history between admin and student
    messages = Message.query.filter(
        ((Message.sender_id == current_user.id) & (Message.receiver_id == user.id)) |
        ((Message.sender_id == user.id) & (Message.receiver_id == current_user.id))
    ).order_by(Message.created_at.desc()).all()

    return render_template('admin/user_detail.html', user=user, messages=messages)

@app.route('/admin/user/<int:user_id>/progress')
@login_required
@admin_required
def admin_user_progress(user_id):
    user = User.query.get_or_404(user_id)
    if user.is_admin:
        flash('Cannot view admin user progress.')
        return redirect(url_for('admin_users'))
    progress_data = Progress.query.filter_by(user_id=user.id).all()
    return render_template('admin/user_progress.html', user=user, progress_data=progress_data)

@app.route('/admin/user/<int:user_id>/update-belt', methods=['POST'])
@login_required
@admin_required
def admin_update_belt(user_id):
    user = User.query.get_or_404(user_id)
    if user.is_admin:
        flash('Cannot modify admin user.')
        return redirect(url_for('admin_users'))

    new_belt = request.form.get('belt_rank')
    if new_belt in ['White', 'Yellow', 'Green', 'Blue', 'Red', 'Black']:
        user.belt_rank = new_belt
        db.session.commit()
        flash('Belt rank updated successfully.')
    else:
        flash('Invalid belt rank.')

    return redirect(url_for('admin_user_detail', user_id=user_id))

@app.route('/admin/user/<int:user_id>/send-message', methods=['POST'])
@login_required
@admin_required
def admin_send_message(user_id):
    user = User.query.get_or_404(user_id)
    if user.is_admin:
        flash('Cannot send message to admin user.')
        return redirect(url_for('admin_users'))

    content = request.form.get('message')
    if not content:
        flash('Message cannot be empty.')
        return redirect(url_for('admin_dashboard'))

    # Create new message
    message = Message(
        sender_id=current_user.id,
        receiver_id=user.id,
        content=content
    )

    db.session.add(message)
    db.session.commit()

    flash('Message sent successfully.')
    return redirect(url_for('admin_dashboard'))

@app.route('/admin/user/<int:user_id>/download-csv')
@login_required
@admin_required
def admin_download_csv(user_id):
    user = User.query.get_or_404(user_id)
    if user.is_admin:
        flash('Cannot download admin data.')
        return redirect(url_for('admin_users'))

    # Create CSV data
    import csv
    import io

    output = io.StringIO()
    writer = csv.writer(output)

    # Write header
    writer.writerow(['Date', 'Activity Type', 'Details'])

    # Write activity data
    for activity in user.activities:
        writer.writerow([
            activity.activity_date.strftime('%Y-%m-%d'),
            activity.activity_type,
            activity.details if activity.details else ''
        ])

    # Create the response
    output.seek(0)
    return Response(
        output,
        mimetype='text/csv',
        headers={
            'Content-Disposition': f'attachment; filename={user.username}_activity.csv'
        }
    )

# Add route to create first admin user
@app.route('/create-admin', methods=['GET', 'POST'])
def create_admin():
    # Check if any admin exists
    if User.query.filter_by(is_admin=True).first():
        flash('Admin user already exists.')
        return redirect(url_for('login'))

    if request.method == 'POST':
        username = request.form.get('username')
        email = request.form.get('email')
        password = request.form.get('password')

        print(f"Attempting to create admin account for username: {username}")  # Debug log

        if User.query.filter_by(username=username).first():
            print(f"Username {username} already exists")  # Debug log
            flash('Username already exists.')
            return render_template('create_admin.html')

        if User.query.filter_by(email=email).first():
            print(f"Email {email} already registered")  # Debug log
            flash('Email already registered.')
            return render_template('create_admin.html')

        try:
            # Create admin user first
            admin_user = User(
                username=username,
                email=email,
                password_hash=generate_password_hash(password),
                is_admin=True,
                created_at=datetime.now()
            )

            # Generate and set class code
            class_code = admin_user.generate_class_code()
            print(f"Generated class code: {class_code}")  # Debug log

            # Add to session and commit
            db.session.add(admin_user)
            db.session.commit()

            print(f"Successfully created admin account for {username} with class code {class_code}")  # Debug log
            flash('Admin account created successfully! Please login.')
            return redirect(url_for('login'))
        except Exception as e:
            print(f"Error creating admin account: {str(e)}")  # Debug log
            db.session.rollback()
            flash('An error occurred while creating the admin account.')
            return render_template('create_admin.html')

    return render_template('create_admin.html')

@app.route('/messages')
@login_required
def messages():
    # Get all messages for the current user
    received_messages = Message.query.filter_by(receiver_id=current_user.id).order_by(Message.created_at.desc()).all()
    sent_messages = Message.query.filter_by(sender_id=current_user.id).order_by(Message.created_at.desc()).all()

    # Mark unread messages as read
    for message in received_messages:
        if not message.is_read:
            message.is_read = True
    db.session.commit()

    return render_template('messages.html',
                         received_messages=received_messages,
                         sent_messages=sent_messages)

@app.route('/send-message', methods=['POST'])
@login_required
def send_message():
    content = request.form.get('message')
    if not content:
        flash('Message cannot be empty.')
        return redirect(url_for('messages'))

    # Find the instructor (admin) for this user
    instructor = User.query.filter_by(is_admin=True).first()
    if not instructor:
        flash('No instructor found.')
        return redirect(url_for('messages'))

    # Create new message
    message = Message(
        sender_id=current_user.id,
        receiver_id=instructor.id,
        content=content
    )

    db.session.add(message)
    db.session.commit()

    flash('Message sent successfully.')
    return redirect(url_for('messages'))

@app.context_processor
def inject_unread_messages():
    if current_user.is_authenticated:
        unread_count = Message.query.filter_by(
            receiver_id=current_user.id,
            is_read=False
        ).count()
        return {'unread_messages': unread_count}
    return {'unread_messages': 0}

@app.route('/admin/messages')
@app.route('/admin/messages/<int:user_id>')
@login_required
@admin_required
def admin_messages(user_id=None):
    # Debug: Print current user info
    print(f"Current user: {current_user.username}, is_admin: {current_user.is_admin}")

    # Get all non-admin users
    users = User.query.filter_by(is_admin=False).order_by(User.username).all()
    print(f"Found {len(users)} non-admin users")
    for user in users:
        print(f"User: {user.username}, is_admin: {user.is_admin}")

    selected_user = None
    messages = []

    if user_id:
        selected_user = User.query.get_or_404(user_id)
        print(f"Selected user: {selected_user.username}, is_admin: {selected_user.is_admin}")

        if selected_user.is_admin:
            flash('Cannot view admin user messages.')
            return redirect(url_for('admin_messages'))

        # Get message history between admin and selected user
        messages = Message.query.filter(
            ((Message.sender_id == current_user.id) & (Message.receiver_id == user_id)) |
            ((Message.sender_id == user_id) & (Message.receiver_id == current_user.id))
        ).order_by(Message.created_at.desc()).all()
        print(f"Found {len(messages)} messages for user {user_id}")

        # Mark unread messages as read
        for message in messages:
            if not message.is_read and message.receiver_id == current_user.id:
                message.is_read = True
        db.session.commit()

    return render_template('admin/messages.html',
                         users=users,
                         selected_user=selected_user,
                         messages=messages)

@app.route('/admin/send-announcement', methods=['POST'])
@login_required
@admin_required
def admin_send_announcement():
    content = request.form.get('message')
    if not content:
        flash('Announcement cannot be empty.')
        return redirect(url_for('admin_messages'))

    # Get all non-admin users
    students = User.query.filter_by(is_admin=False).all()

    # Create a message for each student
    for student in students:
        message = Message(
            sender_id=current_user.id,
            receiver_id=student.id,
            content=content
        )
        db.session.add(message)

    db.session.commit()
    flash('Announcement sent to all students.')
    return redirect(url_for('admin_messages'))

if __name__ == '__main__':
    with app.app_context():
        db.create_all()
    app.run(debug=True, port=5002)
