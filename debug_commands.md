# Debug Commands for Render Shell

## 0. Find the Correct Project Path
```bash
# First, let's find where we are and what's available
pwd
ls -la

# Look for the project directory
find / -name "app.py" 2>/dev/null | head -10
find / -name "requirements.txt" 2>/dev/null | head -10

# Check common Render paths
ls -la /opt/render/ 2>/dev/null || echo "No /opt/render directory"
ls -la /app/ 2>/dev/null || echo "No /app directory"
ls -la /workspace/ 2>/dev/null || echo "No /workspace directory"
ls -la /home/ 2>/dev/null || echo "No /home directory"

# Check if we're already in the project directory
ls -la *.py 2>/dev/null || echo "No Python files in current directory"
```

## 1. Check Application Logs
```bash
# Once you find the correct path, check logs
# Common log locations:
find / -name "*.log" 2>/dev/null | head -10

# Check if there are any log files in the current directory
find . -name "*.log" 2>/dev/null || echo "No log files found"

# Check system logs
tail -f /var/log/syslog 2>/dev/null || echo "No syslog access"
dmesg | tail -20 2>/dev/null || echo "No dmesg access"

# Check Render logs
journalctl -u render 2>/dev/null || echo "No journalctl access"
```

## 2. Check Database Connection
```python
# In Python shell - run this after finding the correct path
import os
import sys

# Add the current directory to Python path
sys.path.append('/app')

# Check environment variables
print("Database URL:", os.environ.get('DATABASE_URL'))
print("FLASK_ENV:", os.environ.get('FLASK_ENV'))
print("Current working directory:", os.getcwd())

# Test database connection
try:
    from app import app
    with app.app_context():
        from models import User
        # Test basic query
        user_count = User.query.count()
        print(f"Database connection successful. User count: {user_count}")
        
        # Check if admin user exists
        admin_users = User.query.filter_by(role='admin').all()
        print(f"Admin users: {[u.username for u in admin_users]}")
        
except Exception as e:
    print(f"Database connection failed: {e}")
    import traceback
    traceback.print_exc()
```

## 3. Check File Permissions and Structure
```bash
# After finding the correct path, check structure
# We're in /app directory

# Check if upload directory exists and has proper permissions
ls -la static/uploads/ 2>/dev/null || echo "No uploads directory"

# Check if static folder exists
ls -la static/ 2>/dev/null || echo "No static directory"

# Check if templates exist
ls -la templates/ 2>/dev/null || echo "No templates directory"

# Check if all required files are present
ls -la *.py
ls -la requirements.txt
```

## 4. Test Flask Application
```python
# Test basic Flask app import
import os
import sys

# Add the current directory to Python path
sys.path.append('/app')

try:
    from app import app
    print("Flask app imported successfully")
    
    # Test app configuration
    print("App config:", app.config.get('DATABASE_URL', 'Not set'))
    print("Upload folder:", app.config.get('UPLOAD_FOLDER', 'Not set'))
    
except Exception as e:
    print(f"Flask app import failed: {e}")
    import traceback
    traceback.print_exc()
```

## 5. Check External API Calls
```python
# Test the WT calendar fetching function
import requests
from datetime import datetime

def test_wt_calendar():
    try:
        current_date = datetime.now()
        year = current_date.year
        month = current_date.month
        url = f"https://m.worldtaekwondo.org/calendar/cld_list.html?cym={year}-{month}"
        
        headers = {
            'User-Agent': 'Mozilla/5.0 (iPhone; CPU iPhone OS 14_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/14.0 Mobile/15E148 Safari/604.1'
        }
        
        print(f"Testing URL: {url}")
        response = requests.get(url, headers=headers, timeout=10)
        print(f"Response status: {response.status_code}")
        print(f"Response length: {len(response.text)}")
        
        if response.status_code == 200:
            print("WT calendar fetch successful")
        else:
            print(f"WT calendar fetch failed: {response.status_code}")
            
    except Exception as e:
        print(f"WT calendar test failed: {e}")

# Run the test
test_wt_calendar()
```

## 6. Check User Authentication
```python
# Test user authentication flow
import sys
sys.path.append('/app')

from app import app
from models import User
from werkzeug.security import check_password_hash, generate_password_hash

with app.app_context():
    # Check if any users exist
    users = User.query.all()
    print(f"Total users: {len(users)}")
    
    for user in users:
        print(f"User: {user.username}, Role: {user.role}, Email: {user.email}")
    
    # Test password hashing
    test_password = "test123"
    hashed = generate_password_hash(test_password)
    print(f"Password hash test: {check_password_hash(hashed, test_password)}")
```

## 7. Check Template Rendering
```python
# Test template rendering
import sys
sys.path.append('/app')

from app import app
from flask import render_template

with app.app_context():
    try:
        # Test basic template
        result = render_template('error.html', error="Test error")
        print("Template rendering successful")
        print(f"Template length: {len(result)}")
    except Exception as e:
        print(f"Template rendering failed: {e}")
        import traceback
        traceback.print_exc()
```

## 8. Check Environment and Dependencies
```bash
# Check Python version and packages
python --version
pip list | grep -E "(Flask|SQLAlchemy|Werkzeug)"

# Check environment variables
env | grep -E "(FLASK|DATABASE|RENDER)"

# Check if all required files are in the right place
ls -la
```

## 9. Test Specific Routes
```python
# Test dashboard route specifically
import sys
sys.path.append('/app')

from app import app
from flask.testing import FlaskClient

with app.test_client() as client:
    try:
        # Test landing page (should work without auth)
        response = client.get('/')
        print(f"Landing page status: {response.status_code}")
        
        # Test login page
        response = client.get('/login')
        print(f"Login page status: {response.status_code}")
        
    except Exception as e:
        print(f"Route testing failed: {e}")
```

## 10. Check for Missing Dependencies
```bash
# Check if all required files exist
ls -la models.py
ls -la config.py
ls -la requirements.txt

# Check if static files are accessible
curl -I http://localhost:5000/static/css/style.css 2>/dev/null || echo "Static files not accessible"
```

## 11. Test Dashboard Route Specifically
```python
# Test the dashboard route that's causing the error
import sys
sys.path.append('/app')

from app import app
from flask.testing import FlaskClient

with app.test_client() as client:
    try:
        # Test dashboard route (this is where the error occurs)
        response = client.get('/dashboard')
        print(f"Dashboard status: {response.status_code}")
        print(f"Dashboard response length: {len(response.data)}")
        
        if response.status_code != 200:
            print(f"Dashboard error: {response.data}")
            
    except Exception as e:
        print(f"Dashboard route test failed: {e}")
        import traceback
        traceback.print_exc()
```

## 12. Test WT Calendar Function Directly
```python
# Test the WT calendar function that might be causing issues
import sys
sys.path.append('/app')

from app import get_wt_calendar_events

try:
    print("Testing WT calendar function...")
    events = get_wt_calendar_events()
    print(f"WT calendar function returned {len(events)} events")
    for event in events[:3]:  # Show first 3 events
        print(f"Event: {event}")
except Exception as e:
    print(f"WT calendar function failed: {e}")
    import traceback
    traceback.print_exc()
```

## 13. Test Dashboard Route with Authentication
```python
# Test dashboard route with a logged-in user to reproduce the actual error
import sys
sys.path.append('/app')

from app import app
from models import User
from flask.testing import FlaskClient
from flask_login import login_user

with app.app_context():
    # Get the admin user
    admin_user = User.query.filter_by(role='admin').first()
    if admin_user:
        print(f"Found admin user: {admin_user.username}")
        
        with app.test_client() as client:
            with client.session_transaction() as sess:
                # Simulate login
                sess['_user_id'] = str(admin_user.id)
                sess['_fresh'] = True
            
            try:
                # Test dashboard route with authenticated user
                response = client.get('/dashboard')
                print(f"Dashboard status (authenticated): {response.status_code}")
                
                if response.status_code == 200:
                    print("Dashboard works with authentication!")
                else:
                    print(f"Dashboard error: {response.data}")
                    
            except Exception as e:
                print(f"Dashboard route test failed: {e}")
                import traceback
                traceback.print_exc()
    else:
        print("No admin user found")
```

## 14. Test Dashboard Function Directly
```python
# Test the dashboard function directly to isolate the issue
import sys
sys.path.append('/app')

from app import app, dashboard
from models import User
from flask import request

with app.app_context():
    # Get the admin user
    admin_user = User.query.filter_by(role='admin').first()
    if admin_user:
        print(f"Testing dashboard function with user: {admin_user.username}")
        
        try:
            # Create a mock request context
            with app.test_request_context('/dashboard'):
                # Simulate authenticated user
                from flask_login import login_user
                login_user(admin_user)
                
                # Call dashboard function directly
                result = dashboard()
                print("Dashboard function executed successfully!")
                print(f"Result type: {type(result)}")
                
        except Exception as e:
            print(f"Dashboard function failed: {e}")
            import traceback
            traceback.print_exc()
    else:
        print("No admin user found")
```

## 15. Simple Dashboard Test (Guaranteed Output)
```python
# Simple test that will definitely show output
import sys
sys.path.append('/app')

print("Starting dashboard test...")

try:
    from app import app
    print("App imported successfully")
    
    from models import User
    print("Models imported successfully")
    
    with app.app_context():
        print("App context created")
        
        # Get admin user
        admin_user = User.query.filter_by(role='admin').first()
        if admin_user:
            print(f"Found admin user: {admin_user.username}")
            
            # Test dashboard function directly
            from app import dashboard
            print("Dashboard function imported")
            
            # Create request context
            with app.test_request_context('/dashboard'):
                print("Request context created")
                
                # Login user
                from flask_login import login_user
                login_user(admin_user)
                print("User logged in")
                
                # Call dashboard
                print("Calling dashboard function...")
                result = dashboard()
                print("Dashboard function completed successfully!")
                
        else:
            print("No admin user found")
            
except Exception as e:
    print(f"Error occurred: {e}")
    import traceback
    traceback.print_exc()
```

## 16. Test Individual Dashboard Components
```python
# Test each component of the dashboard separately
import sys
sys.path.append('/app')

print("Testing dashboard components...")

try:
    from app import app, get_wt_calendar_events
    from models import User, CustomEvent, LibraryItem, VideoComment
    
    with app.app_context():
        print("1. Testing WT calendar...")
        wt_events = get_wt_calendar_events()
        print(f"   WT events: {len(wt_events)}")
        
        print("2. Testing custom events...")
        custom_events = CustomEvent.query.all()
        print(f"   Custom events: {len(custom_events)}")
        
        print("3. Testing user videos...")
        admin_user = User.query.filter_by(role='admin').first()
        if admin_user:
            user_videos = LibraryItem.query.filter_by(
                user_id=admin_user.id,
                item_type='video'
            ).all()
            print(f"   User videos: {len(user_videos)}")
            
            print("4. Testing video comments...")
            videos_with_comments = []
            for video in user_videos:
                comments = VideoComment.query.filter_by(video_id=video.id).all()
                if comments:
                    videos_with_comments.append(video)
            print(f"   Videos with comments: {len(videos_with_comments)}")
        
        print("All components tested successfully!")
        
except Exception as e:
    print(f"Component test failed: {e}")
    import traceback
    traceback.print_exc()
```

## 17. Check What Users Exist
```python
# Check what users exist in the database
import sys
sys.path.append('/app')

from app import app
from models import User, Role

with app.app_context():
    print("=== Checking Users in Database ===")
    
    # Get all users
    all_users = User.query.all()
    print(f"Total users: {len(all_users)}")
    
    if all_users:
        print("\nAll users:")
        for user in all_users:
            print(f"  - Username: {user.username}")
            print(f"    Email: {user.email}")
            print(f"    Role: {user.role}")
            print(f"    Belt: {user.belt_rank}")
            print(f"    ID: {user.id}")
            print()
    else:
        print("No users found in database")
    
    # Check by role
    admin_users = User.query.filter_by(role=Role.ADMIN).all()
    master_users = User.query.filter_by(role=Role.MASTER).all()
    student_users = User.query.filter_by(role=Role.STUDENT).all()
    
    print(f"Admin users: {len(admin_users)}")
    print(f"Master users: {len(master_users)}")
    print(f"Student users: {len(student_users)}")
```

## 18. Create Admin User
```python
# Create an admin user if none exists
import sys
sys.path.append('/app')

from app import app
from models import User, Role
from werkzeug.security import generate_password_hash

with app.app_context():
    print("=== Creating Admin User ===")
    
    # Check if admin already exists
    existing_admin = User.query.filter_by(role=Role.ADMIN).first()
    if existing_admin:
        print(f"Admin user already exists: {existing_admin.username}")
    else:
        print("No admin user found. Creating one...")
        
        try:
            # Create admin user
            admin_user = User(
                username='admin',
                email='admin@tkdai.com',
                role=Role.ADMIN,
                belt_rank='Black'
            )
            admin_user.password_hash = generate_password_hash('admin123')
            
            # Add to database
            from app import db
            db.session.add(admin_user)
            db.session.commit()
            
            print("Admin user created successfully!")
            print(f"Username: admin")
            print(f"Password: admin123")
            print(f"Email: admin@tkdai.com")
            
        except Exception as e:
            print(f"Error creating admin user: {e}")
            import traceback
            traceback.print_exc()
```

## 19. Test Dashboard with Any User
```python
# Test dashboard with any existing user
import sys
sys.path.append('/app')

from app import app, dashboard
from models import User

with app.app_context():
    print("=== Testing Dashboard with Any User ===")
    
    # Get any user
    any_user = User.query.first()
    if any_user:
        print(f"Testing with user: {any_user.username} (role: {any_user.role})")
        
        try:
            with app.test_request_context('/dashboard'):
                from flask_login import login_user
                login_user(any_user)
                
                result = dashboard()
                print("Dashboard function completed successfully!")
                print(f"Result type: {type(result)}")
                
        except Exception as e:
            print(f"Dashboard function failed: {e}")
            import traceback
            traceback.print_exc()
    else:
        print("No users found in database")
```

## How to Run These Commands

1. **Access Render Shell:**
   - Go to your Render dashboard
   - Click on your service
   - Go to "Shell" tab
   - Click "Connect"

2. **Run Commands:**
   - For bash commands: Just paste them directly
   - For Python commands: Start with `python` or `python3` and paste the code

3. **Start with these in order:**
   ```bash
   # 1. Check what users exist
   python -c "
   import sys
   sys.path.append('/app')
   from app import app
   from models import User, Role
   with app.app_context():
       all_users = User.query.all()
       print(f'Total users: {len(all_users)}')
       for user in all_users:
           print(f'User: {user.username}, Role: {user.role}, Email: {user.email}')
   "
   
   # 2. Create admin user if needed
   python -c "
   import sys
   sys.path.append('/app')
   from app import app
   from models import User, Role
   from werkzeug.security import generate_password_hash
   with app.app_context():
       existing_admin = User.query.filter_by(role=Role.ADMIN).first()
       if existing_admin:
           print(f'Admin exists: {existing_admin.username}')
       else:
           admin_user = User(username='admin', email='admin@tkdai.com', role=Role.ADMIN, belt_rank='Black')
           admin_user.password_hash = generate_password_hash('admin123')
           from app import db
           db.session.add(admin_user)
           db.session.commit()
           print('Admin user created: admin/admin123')
   "
   
   # 3. Test dashboard with any user
   python -c "
   import sys
   sys.path.append('/app')
   from app import app, dashboard
   from models import User
   with app.app_context():
       any_user = User.query.first()
       if any_user:
           print(f'Testing with user: {any_user.username}')
           with app.test_request_context('/dashboard'):
               from flask_login import login_user
               login_user(any_user)
               result = dashboard()
               print('Dashboard function completed successfully!')
       else:
           print('No users found')
   "
   ```

## Common Issues to Look For

1. **Database Connection Issues:**
   - Wrong DATABASE_URL format
   - Network connectivity problems
   - Missing database credentials

2. **Missing Files:**
   - Templates not found
   - Static files missing
   - Configuration files not present

3. **Permission Issues:**
   - Upload directory not writable
   - File permissions too restrictive

4. **External API Issues:**
   - WT calendar website blocking requests
   - Network timeouts
   - DNS resolution problems

5. **Python Environment Issues:**
   - Missing dependencies
   - Wrong Python version
   - Import path problems

**First check what users exist, then create an admin user if needed, then test the dashboard!** 