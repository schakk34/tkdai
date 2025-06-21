import os
import os.path
import subprocess
import math
from datetime import datetime
from functools import wraps

import cv2
from flask import Flask, render_template, Response, jsonify, request, redirect, url_for, flash, send_file, abort
from flask_login import LoginManager, login_user, logout_user, login_required, current_user
from werkzeug.security import generate_password_hash, check_password_hash
import numpy as np
import requests
from bs4 import BeautifulSoup

from PracticeStudio import PracticeStudio
from capture import Capture
from utils.form_utils.form_comparison import FormComparison
from utils.form_utils.form_analyzer import FormAnalyzer
from models import db, LibraryItem, User, Progress, UserActivity, Message, VideoComment, CustomEvent, Role, PracticeVideo, VideoFavorite
from white_belt_form import WhiteBeltForm
from config import config

# Determine the configuration to use
config_name = os.environ.get('FLASK_ENV', 'development')
if config_name == 'production':
    config_name = 'docker'  # Use Docker config for production

app = Flask(__name__)
app.config.from_object(config[config_name])
config[config_name].init_app(app)

# Initialize database
db.init_app(app)

# Create database tables
with app.app_context():
    # Only create tables if they don't exist
    db.create_all()
    # Ensure upload folder exists
    os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)

# Initialize Flask-Login
login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'login'

@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))

camera: Capture
practice_studio: PracticeStudio
white_belt_form: WhiteBeltForm

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
        master = User.query.filter_by(
            class_code=class_code,
            role=Role.MASTER
        ).first()
        if not master:
            flash('Invalid class code. Please check with your instructor.')
            return render_template('signup.html')

        try:
            hashed_password = generate_password_hash(request.form['password'])
            new_user = User(
                username=request.form['username'],
                email=request.form['email'],
                password_hash=hashed_password,
                belt_rank=request.form.get('belt_rank', 'White'),
                teacher_id=master.id,
                role=Role.STUDENT  # Explicitly set role as student
            )
            db.session.add(new_user)
            db.session.commit()
            flash('Account created successfully! Please login.')
            return redirect(url_for('login'))
        except Exception as e:
            db.session.rollback()
            print(e)
            flash('An error occurred while creating your account. Please try again.')
            return render_template('signup.html')

    return render_template('signup.html')

@app.route('/login', methods=['GET', 'POST'])
def login():
    # Debug: Print all users in database
    print("\n=== Current Users in Database ===")
    all_users = User.query.all()
    for user in all_users:
        print(f"Username: {user.username}, Email: {user.email}, Is Master: {user.is_master()}, Is Admin: {user.is_admin()}")
    print("===============================\n")

    # If user is already logged in, redirect to appropriate dashboard
    if current_user.is_authenticated:
        if current_user.is_master():
            return redirect(url_for('master_dashboard'))
        return redirect(url_for('dashboard'))

    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')

        print(f"Login attempt for username: {username}")  # Debug log

        # Check if user exists
        user = User.query.filter_by(username=username).first()

        if user:
            print(f"User found: {user.username}, is_admin: {user.is_admin()}")  # Debug log
            print(f"User found: {user.username}, is_master: {user.is_master()}")  # Debug log

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
                print(next_page)
                if not next_page or not next_page.startswith('/'):
                    if user.is_master():
                        print(f"Redirecting master user {username} to master dashboard")  # Debug log
                        next_page = url_for('master_dashboard')
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


def admin_required(f: object) -> object:
    @wraps(f)
    def decorated(*args, **kwargs):
        if not (current_user.is_authenticated and current_user.is_admin()):
            abort(403)
        return f(*args, **kwargs)
    return decorated

@app.route('/create_master', methods=['GET','POST'])
@login_required
@admin_required
def create_master():
    if not current_user.is_admin():
        flash("Only administrators may create master accounts.")
        return redirect(url_for('dashboard'))


    if request.method == 'POST':
        # validate form…
        user = User(
            username=request.form.get('username'),
            email=request.form.get('email'),
            class_code=request.form.get('class_code'),
            role=Role.MASTER
        )
        user.set_password(request.form.get('password'))
        # generate that master's class_code
        db.session.add(user)
        db.session.commit()
        flash("Master account created!")

    return render_template('admin/create_master.html')

@app.route('/logout')
@login_required
def logout():
    logout_user()
    flash('You have been logged out.')
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

    # Get both WT calendar events and custom events relevant to this user
    wt_events = get_wt_calendar_events()
    
    # Fix PostgreSQL JSON field query - use a simpler approach
    custom_events = CustomEvent.query.filter(
        CustomEvent.send_to_all == True
    ).order_by(CustomEvent.event_date).all()
    
    # Filter target_students in Python instead of SQL to avoid JSON operator issues
    filtered_custom_events = []
    for event in custom_events:
        if event.send_to_all or (event.target_students and current_user.id in event.target_students):
            filtered_custom_events.append(event)

    # Get videos with comments for notifications
    videos_with_comments = []
    user_videos = LibraryItem.query.filter_by(
        user_id=current_user.id,
        item_type='video'
    ).all()
    
    for video in user_videos:
        comments = VideoComment.query.filter_by(video_id=video.id).all()
        if comments:
            video.comments = comments
            videos_with_comments.append(video)

    return render_template('dashboard.html',
                         user=current_user,
                         wt_events=wt_events,
                         custom_events=filtered_custom_events,
                         videos_with_comments=videos_with_comments)

@app.route('/practice')
@login_required
def practice():
    # Get all videos organized by tags
    all_videos = PracticeVideo.query.all()

    # Get user's favorite videos
    user_favorites = VideoFavorite.query.filter_by(user_id=current_user.id).all()
    favorite_video_ids = [fav.video_id for fav in user_favorites]

    # Organize videos by tags - be more inclusive
    sparring_videos = []
    poomsae_videos = []
    demo_videos = []

    for video in all_videos:
        # Check if video is favorited by current user
        video.is_favorited = video.id in favorite_video_ids

        if video.tags:
            if 'sparring' in video.tags:
                sparring_videos.append(video)
            elif 'poomsae' in video.tags:
                poomsae_videos.append(video)
            elif 'demo' in video.tags:
                demo_videos.append(video)
            else:
                # If no specific category, add to sparring as default
                sparring_videos.append(video)
        else:
            # If no tags, add to sparring as default
            sparring_videos.append(video)

    # Get favorite videos for display
    favorite_videos = [video for video in all_videos if video.id in favorite_video_ids]

    # Get unique creators and their video counts
    creator_counts = {}
    for video in all_videos:
        if video.creators:
            for creator in video.creators:
                if creator not in creator_counts:
                    creator_counts[creator] = 0
                creator_counts[creator] += 1

    # Debug output
    print(f"Debug - Total videos: {len(all_videos)}")
    print(f"Debug - Creator counts: {creator_counts}")
    print(f"Debug - User favorites: {len(favorite_videos)}")

    return render_template('practice.html',
                         sparring_videos=sparring_videos,
                         poomsae_videos=poomsae_videos,
                         demo_videos=demo_videos,
                         creators=list(creator_counts.keys()),
                         creator_counts=creator_counts,
                         all_videos=all_videos,
                         favorite_videos=favorite_videos)  # Pass favorite videos for display

@app.route('/practice/creator/<creator_name>')
@login_required
def practice_creator(creator_name):
    # Get all videos by this creator
    # Use JSON_CONTAINS for SQLite JSON field query
    creator_videos = PracticeVideo.query.filter(
        PracticeVideo.creators.contains(creator_name)
    ).all()

    return render_template('practice_creator.html',
                         creator_name=creator_name,
                         videos=creator_videos)

@app.route('/practice/video/<int:video_id>')
@login_required
def practice_video_detail(video_id):
    video = PracticeVideo.query.get_or_404(video_id)

    # Check if video is favorited by current user
    video.is_favorited = VideoFavorite.query.filter_by(
        user_id=current_user.id,
        video_id=video_id
    ).first() is not None

    # Increment view count
    video.views += 1
    db.session.commit()

    # Get related videos (same tags or creators)
    # Use a simpler approach for SQLite JSON fields
    related_videos = []
    if video.tags or video.creators:
        # Get all videos except the current one
        all_videos = PracticeVideo.query.filter(PracticeVideo.id != video_id).all()

        for other_video in all_videos:
            # Check for tag overlap
            tag_overlap = False
            if video.tags and other_video.tags:
                for tag in video.tags:
                    if tag in other_video.tags:
                        tag_overlap = True
                        break

            # Check for creator overlap
            creator_overlap = False
            if video.creators and other_video.creators:
                for creator in video.creators:
                    if creator in other_video.creators:
                        creator_overlap = True
                        break

            if tag_overlap or creator_overlap:
                related_videos.append(other_video)
                if len(related_videos) >= 6:  # Limit to 6 related videos
                    break

    return render_template('practice_video_detail.html',
                         video=video,
                         related_videos=related_videos)

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
        # Debug: Print current user id
        print(f"Current user id: {current_user.id}")
        # Create user-specific upload directory
        user_upload_dir = os.path.join(app.config['UPLOAD_FOLDER'], str(current_user.id))
        print(f"User upload dir: {user_upload_dir}")
        os.makedirs(user_upload_dir, exist_ok=True)

        # Save the uploaded video
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        video_filename = f"{form_type}_{timestamp}.webm"
        video_path = os.path.join(user_upload_dir, video_filename)
        print(f"Saving video to: {os.path.abspath(video_path)}")  # Debug log
        try:
            video_file.save(video_path)
            print(f"File exists after save? {os.path.exists(video_path)}")
        except Exception as save_exc:
            print(f"Exception during video_file.save: {save_exc}")
            return jsonify({'error': f'Failed to save video: {save_exc}'}), 500

        # Convert webm to mp4 with optimized settings for memory-constrained environments
        mp4_filename = f"{form_type}_{timestamp}.mp4"
        mp4_path = os.path.join(user_upload_dir, mp4_filename)
        
        try:
            # Use more memory-efficient ffmpeg settings
            ffmpeg_cmd = [
                'ffmpeg', '-i', video_path,
                '-c:v', 'libx264', 
                '-preset', 'ultrafast',  # Faster encoding, less memory
                '-crf', '28',  # Higher CRF = smaller file, less memory
                '-maxrate', '1M',  # Limit bitrate to reduce memory usage
                '-bufsize', '2M',
                '-threads', '1',  # Single thread to reduce memory usage
                '-c:a', 'aac', 
                '-b:a', '64k',  # Lower audio bitrate
                '-y',  # Overwrite output file
                mp4_path
            ]
            
            print(f"Running ffmpeg command: {' '.join(ffmpeg_cmd)}")
            
            # Run with timeout and memory monitoring
            result = subprocess.run(
                ffmpeg_cmd,
                capture_output=True,
                text=True,
                timeout=300  # 5 minute timeout
            )
            
            if result.returncode != 0:
                print(f"FFmpeg error output: {result.stderr}")
                raise subprocess.CalledProcessError(result.returncode, ffmpeg_cmd, result.stdout, result.stderr)
                
            print(f"FFmpeg conversion successful: {mp4_path}")
            
        except subprocess.TimeoutExpired:
            print("FFmpeg conversion timed out")
            return jsonify({'error': 'Video processing timed out. Please try with a shorter video.'}), 500
        except subprocess.CalledProcessError as e:
            print(f"FFmpeg conversion failed: {e}")
            return jsonify({'error': f'Video conversion failed: {e.stderr}'}), 500
        except Exception as e:
            print(f"Unexpected error during ffmpeg conversion: {e}")
            return jsonify({'error': f'Video processing error: {str(e)}'}), 500

        # Process rhythm file if provided
        rhythm_path = None
        if 'rhythm' in request.files and request.files['rhythm'].filename:
            rhythm_file = request.files['rhythm']
            rhythm_filename = f"{form_type}_rhythm_{timestamp}.mp3"
            rhythm_path = os.path.join(user_upload_dir, rhythm_filename)
            rhythm_file.save(rhythm_path)

        # If this is a recording (not a form comparison), just return the converted video
        if form_type == 'recording':
            print(f"Recording conversion successful - mp4_path: {mp4_path}")  # Debug log
            return jsonify({
                'success': True,
                'video_url': url_for('static', filename=f'uploads/{current_user.id}/{mp4_filename}'),
                'mp4_path': mp4_path
            })

        # Check if ideal data exists for this form
        # Map form types to their actual file names
        form_type_map = {
            'koryo': 'koryo',
            'chiljang': 'wt_chiljang'
        }
        
        file_name = form_type_map.get(form_type, form_type)
        ideal_data_path = os.path.join(app.static_folder, 'data', 'forms', 'pose_data', f'{file_name}_ideal_data.json')
        if not os.path.exists(ideal_data_path):
            return jsonify({'error': f'No ideal data found for {form_type}'}), 400

        # Process the video with error handling
        try:
            form_comparison = FormComparison(ideal_data_path=ideal_data_path)
            
            # Add timeout and memory optimization for form comparison
            try:
                result = form_comparison.process_user_video(
                    user_video_path=mp4_path,
                    output_path=os.path.join(user_upload_dir, f"{form_type}_comparison_{timestamp}.mp4"),
                    audio_path=rhythm_path)
                if result is None or result[0] is None:
                    return jsonify({
                        'success': False,
                        'error': 'Video processing failed; see server logs for details.'
                    }), 500

                result_video_path, feature_vectors = result
            except Exception as e:
                print(f"Form comparison processing error: {e}")
                # Return a basic response if form comparison fails
                return jsonify({
                    'success': True,
                    'video_url': url_for('static', filename=f'uploads/{current_user.id}/{mp4_filename}'),
                    'score': 0.0,
                    'stars_earned': 1,
                    'total_stars': current_user.star_count,
                    'all_feature_vectors': [],
                    'mp4_path': mp4_path,
                    'message': 'Video processed but form comparison failed. You can still save to library.'
                })
        except Exception as e:
            print(f"Form comparison processing error: {e}")
            # Return a basic response if form comparison fails
            return jsonify({
                'success': True,
                'video_url': url_for('static', filename=f'uploads/{current_user.id}/{mp4_filename}'),
                'score': 0.0,
                'stars_earned': 1,
                'total_stars': current_user.star_count,
                'all_feature_vectors': [],
                'mp4_path': mp4_path,
                'message': 'Video processed but form comparison failed. You can still save to library.'
            })

        # Calculate average score and convert to percentage
        if not feature_vectors:
            # No valid poses detected
            score_percentage = 0.0
            stars_earned = 1  # Minimum 1 star for attempting
        else:
            avg_score = np.mean([fv['overall_score'] for fv in feature_vectors])
            # Check for NaN or invalid scores
            if np.isnan(avg_score) or avg_score < 0:
                score_percentage = 0.0
                stars_earned = 1  # Minimum 1 star for attempting
            else:
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
            'all_feature_vectors': feature_vectors,
            'mp4_path': result_video_path  # Use the comparison video path here
        })

    except Exception as e:
        import traceback
        print(f"Error processing form comparison: {str(e)}")
        print(f"Full traceback: {traceback.format_exc()}")
        return jsonify({'error': f'Error processing video: {str(e)}'}), 500

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in {'mp4', 'mov', 'avi', 'mp3', 'wav'}

# Initialize the form analyzer
form_analyzer = FormAnalyzer()

@app.route('/analyze-form', methods=['POST'])
@login_required
def analyze_form():
    data = request.get_json()
    video_url = data.get('video_url')
    feature_vectors = data.get('feature_vectors', [])
    
    if not video_url:
        return jsonify({'success': False, 'error': 'No video URL provided'}), 400
    
    if not feature_vectors:
        return jsonify({'success': False, 'error': 'No feature vectors received'}), 400

    # analyzer = FormAnalyzer(provider='gemini')
    feedback = "Form analysis feedback will be generated here"
    return jsonify({'success': True, 'feedback': feedback})

@app.route('/library')
@login_required
def library():
    videos = LibraryItem.query.filter_by(
        user_id=current_user.id,
        item_type='video'
    ).order_by(LibraryItem.created_at.desc()).all()

    # Add comments to each video
    for video in videos:
        video.comments = VideoComment.query.filter_by(video_id=video.id).all()

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
        print(f"Received data: {data}")  # Debug: print the entire request data
        
        item_type = data.get('type')
        title = data.get('title')
        description = data.get('description', '')
        file_path = data.get('file_path')

        print(f"Saving to library - Type: {item_type}, Title: {title}, File: {file_path}")  # Debug log

        if not all([item_type, title]):
            print(f"Missing required fields - item_type: {item_type}, title: {title}")  # Debug
            return jsonify({'success': False, 'error': 'Missing required fields'})

        # Convert the file path to a URL
        if file_path.startswith('blob:') or file_path.startswith('http'):
            # Handle blob URLs (from recordings)
            print(f"Using blob/http URL: {file_path}")  # Debug
            file_path = file_path
        else:
            # Handle full paths from mp4_path
            print(f"Processing file path: {file_path}")  # Debug
            if os.path.isabs(file_path):
                # It's an absolute path, get the relative path from uploads folder
                print(f"File path is absolute: {file_path}")  # Debug
                relative_path = os.path.relpath(file_path, app.config['UPLOAD_FOLDER'])
                print(f"Relative path: {relative_path}")  # Debug
            else:
                # It's already a relative path
                print(f"File path is relative: {file_path}")  # Debug
                relative_path = file_path
            
            file_path = url_for('serve_upload', filename=relative_path, _external=True)
            print(f"Converted file path to URL: {file_path}")  # Debug log

        # Create new library item
        print(f"Creating LibraryItem with file_path: {file_path}")  # Debug
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
            print(f"Added form_type: {item.form_type}")  # Debug
        elif item_type == 'rhythm':
            item.markers = data.get('markers')
            print(f"Added markers: {item.markers}")  # Debug

        print(f"About to add item to database")  # Debug
        db.session.add(item)
        print(f"About to commit to database")  # Debug
        db.session.commit()

        print(f"Successfully saved item to library with ID: {item.id}")  # Debug log
        return jsonify({'success': True, 'id': item.id})
    except Exception as e:
        import traceback
        print(f"Error saving to library: {str(e)}")  # Debug log
        print(f"Full traceback: {traceback.format_exc()}")  # Debug: print full traceback
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
        # Get custom events that are relevant to the current user
        # Events sent to all students OR events specifically targeting this user
        # Fix PostgreSQL JSON field query - use a simpler approach
        custom_events = CustomEvent.query.filter(
            CustomEvent.send_to_all == True
        ).order_by(CustomEvent.event_date).all()
        
        # Filter target_students in Python instead of SQL to avoid JSON operator issues
        filtered_custom_events = []
        for event in custom_events:
            if event.send_to_all or (event.target_students and current_user.id in event.target_students):
                filtered_custom_events.append(event)
        
        events = []
        for event in filtered_custom_events:
            event_data = {
                'id': f'custom_{event.id}',
                'title': event.title,
                'start': event.event_date.isoformat(),
                'allDay': event.is_all_day,
                'description': event.description,
                'location': event.location,
                'event_type': event.event_type,
                'color': '#28a745'  # Green for custom events
            }
            
            # Add time if not all-day event
            if not event.is_all_day and event.event_time:
                event_data['start'] = f"{event.event_date.isoformat()}T{event.event_time.isoformat()}"
            
            events.append(event_data)

        return jsonify(events)
    except Exception as e:
        print(f"Error fetching custom events: {str(e)}")
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

# Add master required decorator
def master_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not current_user.is_authenticated or not current_user.is_master():
            flash('You do not have permission to access this page.')
            return redirect(url_for('dashboard'))
        return f(*args, **kwargs)
    return decorated_function

# Add master routes
@app.route('/master')
@login_required
@master_required
def master_dashboard():
    # Get all master's students
    students = User.query.filter_by(
        teacher_id=current_user.id,
        role=Role.STUDENT
    ).all()
    return render_template('master/dashboard.html', students=students)

@app.route('/master/users')
@login_required
@master_required
def master_users():
    students = User.query.filter_by(
        teacher_id=current_user.id,
        role=Role.STUDENT
    ).all()
    return render_template('master/users.html', students=students)

@app.route('/master/user/<int:user_id>')
@login_required
@master_required
def master_user_detail(user_id):
    user = User.query.get_or_404(user_id)
    if user.is_master():
        flash('Cannot view master user details.')
        return redirect(url_for('master_users'))

    # Get message history between master and student
    messages = Message.query.filter(
        ((Message.sender_id == current_user.id) & (Message.receiver_id == user.id)) |
        ((Message.sender_id == user.id) & (Message.receiver_id == current_user.id))
    ).order_by(Message.created_at.desc()).all()

    return render_template('master/user_detail.html', user=user, messages=messages)

@app.route('/master/user/<int:user_id>/progress')
@login_required
@master_required
def master_user_progress(user_id):
    user = User.query.get_or_404(user_id)
    if user.is_master():
        flash('Cannot view master user progress.')
        return redirect(url_for('master_users'))
    progress_data = Progress.query.filter_by(user_id=user.id).all()
    return render_template('master/user_progress.html', user=user, progress_data=progress_data)

@app.route('/master/user/<int:user_id>/update-belt', methods=['POST'])
@login_required
@master_required
def master_update_belt(user_id):
    user = User.query.get_or_404(user_id)
    if user.is_master():
        flash('Cannot modify master user.')
        return redirect(url_for('master_users'))

    new_belt = request.form.get('belt_rank')
    if new_belt in ['White', 'Yellow', 'Green', 'Blue', 'Red', 'Black']:
        user.belt_rank = new_belt
        db.session.commit()
        flash('Belt rank updated successfully.')
    else:
        flash('Invalid belt rank.')

    return redirect(url_for('master_user_detail', user_id=user_id))

@app.route('/master/user/<int:user_id>/send-message', methods=['POST'])
@login_required
@master_required
def master_send_message(user_id):
    user = User.query.get_or_404(user_id)
    if user.is_master():
        flash('Cannot send message to master user.')
        return redirect(url_for('master_users'))

    content = request.form.get('message')
    if not content:
        flash('Message cannot be empty.')
        return redirect(url_for('master_dashboard'))

    # Create new message
    message = Message(
        sender_id=current_user.id,
        receiver_id=user.id,
        content=content
    )

    db.session.add(message)
    db.session.commit()

    flash('Message sent successfully.')
    return redirect(url_for('master_dashboard'))

@app.route('/master/user/<int:user_id>/download-csv')
@login_required
@master_required
def master_download_csv(user_id):
    user = User.query.get_or_404(user_id)
    if user.is_master():
        flash('Cannot download master data.')
        return redirect(url_for('master_users'))

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

@app.route('/master/user/<int:user_id>/delete', methods=['POST'])
@login_required
@master_required
def master_delete_student(user_id):
    user = User.query.get_or_404(user_id)
    # Only allow deleting students in this master's school
    if user.role != Role.STUDENT or user.teacher_id != current_user.id:
        flash('You can only delete your own students.')
        return redirect(url_for('master_users'))
    # Optionally: delete related data (progress, library, etc.)
    db.session.delete(user)
    db.session.commit()
    flash(f'Student {user.username} has been deleted.')
    return redirect(url_for('master_users'))

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

    # Find the instructor (master) for this user
    instructor = User.query.filter_by(
        role=Role.MASTER,
        class_code=current_user.class_code
    ).first()
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

@app.route('/master/messages')
@app.route('/master/messages/<int:user_id>')
@login_required
@master_required
def master_messages(user_id=None):
    # Debug: Print current user info
    print(f"Current user: {current_user.username}, is_master: {current_user.is_master()}")

    # Get all non-master users
    students = User.query.filter_by(
        role=Role.STUDENT,
        teacher_id=current_user.id
    ).order_by(User.username).all()
    print(f"Found {len(students)} non-master users")
    for student in students:
        print(f"User: {student.username}, is_master: {student.is_master()}")

    selected_user = None
    messages = []

    if user_id:
        selected_user = User.query.get_or_404(user_id)
        print(f"Selected user: {selected_user.username}, is_master: {selected_user.is_master()}")

        if selected_user.is_master():
            flash('Cannot view master user messages.')
            return redirect(url_for('master_messages'))

        # Get message history between master and selected user
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

    return render_template('master/messages.html',
                           users=students,
                           selected_user=selected_user,
                           messages=messages)

@app.route('/master/send-announcement', methods=['POST'])
@login_required
@master_required
def master_send_announcement():
    content = request.form.get('message')
    if not content:
        flash('Announcement cannot be empty.')
        return redirect(url_for('master_messages'))

    # Get master's students
    students = User.query.filter_by(
        role=Role.STUDENT,
        teacher_id=current_user.id
    ).order_by(User.username).all()

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
    return redirect(url_for('master_messages'))

@app.route('/master/user/<int:user_id>/video/<int:video_id>')
@login_required
@master_required
def master_view_student_video(user_id, video_id):
    user = User.query.get_or_404(user_id)
    if user.is_master():
        flash('Cannot view master user videos.')
        return redirect(url_for('master_users'))
    
    video = LibraryItem.query.get_or_404(video_id)
    if video.item_type != 'video':
        flash('This item is not a video.')
        return redirect(url_for('master_users'))
    
    # Get existing comments for this video
    comments = VideoComment.query.filter_by(video_id=video_id).order_by(VideoComment.timestamp).all()
    
    return render_template('master/view_student_video.html',
                           user=user,
                           video=video,
                           comments=comments)

@app.route('/api/video/<int:video_id>/comments', methods=['GET'])
@login_required
def get_video_comments_student(video_id):
    """Get all comments for a video (student access)"""
    # Verify the video belongs to the current user
    video = LibraryItem.query.get_or_404(video_id)
    if video.user_id != current_user.id:
        return jsonify({'error': 'Unauthorized'}), 403
    
    comments = VideoComment.query.filter_by(video_id=video_id).order_by(VideoComment.timestamp).all()
    return jsonify([{
        'id': comment.id,
        'timestamp': comment.timestamp,
        'comment': comment.comment,
        'created_at': comment.created_at.isoformat(),
        'master_name': comment.master.username,
        'has_annotation': comment.has_annotation,
        'annotation': {
            'x': comment.annotation_x,
            'y': comment.annotation_y,
            'radius': comment.annotation_radius,
            'color': comment.annotation_color
        } if comment.has_annotation else None
    } for comment in comments])

@app.route('/api/video/<int:video_id>/comments/master', methods=['GET'])
@login_required
@master_required
def get_video_comments(video_id):
    """Get all comments for a video (master access)"""
    # Verify the video belongs to the current user
    video = LibraryItem.query.get_or_404(video_id)
    if video.user_id != current_user.id:
        return jsonify({'error': 'Unauthorized'}), 403
    
    comments = VideoComment.query.filter_by(video_id=video_id).order_by(VideoComment.timestamp).all()
    return jsonify([{
        'id': comment.id,
        'timestamp': comment.timestamp,
        'comment': comment.comment,
        'created_at': comment.created_at.isoformat(),
        'master_name': comment.master.username,
        'has_annotation': comment.has_annotation,
        'annotation': {
            'x': comment.annotation_x,
            'y': comment.annotation_y,
            'radius': comment.annotation_radius,
            'color': comment.annotation_color
        } if comment.has_annotation else None
    } for comment in comments])

@app.route('/api/video/<int:video_id>/comments/master', methods=['POST'])
@login_required
@master_required
def add_video_comment_master(video_id):
    """Add a new comment to a video (master access)"""
    data = request.get_json()
    timestamp = data.get('timestamp')
    comment_text = data.get('comment')
    annotation_data = data.get('annotation')  # New annotation data
    
    if not timestamp or not comment_text:
        return jsonify({'error': 'Timestamp and comment are required'}), 400
    
    # Verify the video exists and belongs to a student
    video = LibraryItem.query.get_or_404(video_id)
    if video.item_type != 'video':
        return jsonify({'error': 'Item is not a video'}), 400
    
    student = User.query.get(video.user_id)
    if student.is_master():
        return jsonify({'error': 'Cannot comment on master videos'}), 400
    
    # Create the comment
    new_comment = VideoComment(
        video_id=video_id,
        master_id=current_user.id,
        timestamp=timestamp,
        comment=comment_text
    )
    
    # Handle annotation data if provided
    if annotation_data:
        new_comment.has_annotation = True
        new_comment.annotation_x = annotation_data.get('x')
        new_comment.annotation_y = annotation_data.get('y')
        new_comment.annotation_radius = annotation_data.get('radius', 5.0)
        new_comment.annotation_color = annotation_data.get('color', '#ff0000')
    
    db.session.add(new_comment)
    db.session.commit()
    
    return jsonify({
        'id': new_comment.id,
        'timestamp': new_comment.timestamp,
        'comment': new_comment.comment,
        'created_at': new_comment.created_at.isoformat(),
        'master_name': current_user.username,
        'has_annotation': new_comment.has_annotation,
        'annotation': {
            'x': new_comment.annotation_x,
            'y': new_comment.annotation_y,
            'radius': new_comment.annotation_radius,
            'color': new_comment.annotation_color
        } if new_comment.has_annotation else None
    })

@app.route('/api/comment/<int:comment_id>', methods=['DELETE'])
@login_required
@master_required
def delete_video_comment(comment_id):
    """Delete a video comment (only by the master who created it)"""
    comment = VideoComment.query.get_or_404(comment_id)
    
    if comment.master_id != current_user.id:
        return jsonify({'error': 'Unauthorized'}), 403
    
    db.session.delete(comment)
    db.session.commit()
    
    return jsonify({'success': True})

@app.route('/library/video/<int:video_id>')
@login_required
def view_my_video(video_id):
    video = LibraryItem.query.get_or_404(video_id)
    
    # Check if the video belongs to the current user
    if video.user_id != current_user.id:
        flash('You can only view your own videos.')
        return redirect(url_for('library'))
    
    # Get comments for this video
    comments = VideoComment.query.filter_by(video_id=video_id).order_by(VideoComment.timestamp).all()
    
    return render_template('view_my_video.html', video=video, comments=comments)

# Calendar Management Routes
@app.route('/master/calendar')
@login_required
@master_required
def master_calendar():
    """master calendar management page"""
    events = CustomEvent.query.order_by(CustomEvent.event_date).all()
    students = User.query.filter_by(
        teacher_id=current_user.id,
        role=Role.STUDENT
    ).order_by(User.username).all()
    return render_template('master/calendar.html', events=events, students=students)

@app.route('/master/calendar/add', methods=['POST'])
@login_required
@master_required
def master_add_event():
    """Add a new calendar event"""
    try:
        title = request.form.get('title')
        description = request.form.get('description')
        event_date = datetime.strptime(request.form.get('event_date'), '%Y-%m-%d').date()
        event_time_str = request.form.get('event_time')
        location = request.form.get('location')
        event_type = request.form.get('event_type', 'general')
        is_all_day = request.form.get('is_all_day') == 'on'
        send_to_all = request.form.get('send_to_all') == 'on'
        target_students = request.form.getlist('target_students')
        
        # Parse time if provided
        event_time = None
        if event_time_str and not is_all_day:
            event_time = datetime.strptime(event_time_str, '%H:%M').time()
        
        # Convert target_students to list of integers
        target_student_ids = [int(sid) for sid in target_students] if target_students else []
        
        event = CustomEvent(
            title=title,
            description=description,
            event_date=event_date,
            event_time=event_time,
            location=location,
            event_type=event_type,
            created_by=current_user.id,
            is_all_day=is_all_day,
            send_to_all=send_to_all,
            target_students=target_student_ids if not send_to_all else None
        )
        
        db.session.add(event)
        db.session.commit()
        
        flash('Event added successfully!', 'success')
    except Exception as e:
        flash(f'Error adding event: {str(e)}', 'error')
        db.session.rollback()
    
    return redirect(url_for('master_calendar'))

@app.route('/master/calendar/edit/<int:event_id>', methods=['POST'])
@login_required
@master_required
def master_edit_event(event_id):
    """Edit an existing calendar event"""
    event = CustomEvent.query.get_or_404(event_id)
    
    try:
        event.title = request.form.get('title')
        event.description = request.form.get('description')
        event.event_date = datetime.strptime(request.form.get('event_date'), '%Y-%m-%d').date()
        event_time_str = request.form.get('event_time')
        event.location = request.form.get('location')
        event.event_type = request.form.get('event_type', 'general')
        event.is_all_day = request.form.get('is_all_day') == 'on'
        event.send_to_all = request.form.get('send_to_all') == 'on'
        target_students = request.form.getlist('target_students')
        
        # Parse time if provided
        event.event_time = None
        if event_time_str and not event.is_all_day:
            event.event_time = datetime.strptime(event_time_str, '%H:%M').time()
        
        # Update target students
        if event.send_to_all:
            event.target_students = None
        else:
            target_student_ids = [int(sid) for sid in target_students] if target_students else []
            event.target_students = target_student_ids
        
        db.session.commit()
        flash('Event updated successfully!', 'success')
    except Exception as e:
        flash(f'Error updating event: {str(e)}', 'error')
        db.session.rollback()
    
    return redirect(url_for('master_calendar'))

@app.route('/master/calendar/delete/<int:event_id>', methods=['POST'])
@login_required
@master_required
def master_delete_event(event_id):
    """Delete a calendar event"""
    event = CustomEvent.query.get_or_404(event_id)
    
    try:
        db.session.delete(event)
        db.session.commit()
        flash('Event deleted successfully!', 'success')
    except Exception as e:
        flash(f'Error deleting event: {str(e)}', 'error')
        db.session.rollback()
    
    return redirect(url_for('master_calendar'))

@app.route('/get_custom_events')
@login_required
def get_custom_events():
    """Get custom events for calendar display"""
    try:
        events = CustomEvent.query.order_by(CustomEvent.event_date).all()
        
        calendar_events = []
        for event in events:
            event_data = {
                'id': event.id,
                'title': event.title,
                'start': event.event_date.isoformat(),
                'allDay': event.is_all_day,
                'description': event.description,
                'location': event.location,
                'event_type': event.event_type,
                'created_by': event.creator.username
            }
            
            # Add time if not all-day event
            if not event.is_all_day and event.event_time:
                event_data['start'] = f"{event.event_date.isoformat()}T{event.event_time.isoformat()}"
            
            calendar_events.append(event_data)
        
        return jsonify(calendar_events)
    except Exception as e:
        print(f"Error fetching custom events: {str(e)}")
        return jsonify([])

@app.route('/api/video/<int:video_id>/favorite', methods=['POST'])
@login_required
def toggle_video_favorite(video_id):
    """Toggle favorite status for a video"""
    try:
        # Check if video exists
        video = PracticeVideo.query.get_or_404(video_id)

        # Check if already favorited
        existing_favorite = VideoFavorite.query.filter_by(
            user_id=current_user.id,
            video_id=video_id
        ).first()

        if existing_favorite:
            # Remove from favorites
            db.session.delete(existing_favorite)
            db.session.commit()
            return jsonify({
                'success': True,
                'favorited': False,
                'message': 'Removed from favorites'
            })
        else:
            # Add to favorites
            new_favorite = VideoFavorite(
                user_id=current_user.id,
                video_id=video_id
            )
            db.session.add(new_favorite)
            db.session.commit()
            return jsonify({
                'success': True,
                'favorited': True,
                'message': 'Added to favorites'
            })

    except Exception as e:
        db.session.rollback()
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

import click

@app.cli.command("create-admin")
@click.argument("username")
@click.argument("email")
@click.argument("password")
def create_admin(username, email, password):
    """Create an ADMIN user with a custom class code."""
    if User.query.filter_by(username=username).first():
        print(f"⚠️  username '{username}' already exists.")
        return

    admin = User(
        username=username,
        email=email,
        role=Role.ADMIN,
    )
    admin.set_password(password)
    db.session.add(admin)
    db.session.commit()
    print(f"✅ Created ADMIN {username!r}")


if __name__ == "__main__":
    import os
    port = int(os.environ.get("PORT", 5002))
    app.run(host="0.0.0.0", port=port)


