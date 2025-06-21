# TKD AI Deployment Guide

## Prerequisites

- Docker and Docker Compose installed
- At least 4GB of available RAM
- Stable internet connection for initial build
- Supabase PostgreSQL database (already configured)

## Database Setup

The application is configured to use Supabase PostgreSQL for persistent data storage.

### 1. Run Database Migration

Before deploying, set up your database tables:

```bash
# Run the migration script
python migrate_db.py
```

This will:
- Test the connection to your Supabase database
- Create all necessary tables
- Verify the setup

### 2. Create Admin User (After First Deployment)

After the application is running, create an admin user:

```bash
# Using Flask CLI
flask create-admin <username> <email> <password>

# Example:
flask create-admin admin admin@example.com mypassword123
```

## Quick Deployment

1. **Clone and navigate to the project directory:**
   ```bash
   cd tkdai
   ```

2. **Set up the database:**
   ```bash
   python migrate_db.py
   ```

3. **Run the deployment script:**
   ```bash
   ./deploy.sh
   ```

4. **Access the application:**
   - Open your browser and go to `http://localhost:5002`
   - The application should be running and ready to use

## Manual Deployment

If you prefer to deploy manually:

1. **Set up the database:**
   ```bash
   python migrate_db.py
   ```

2. **Build the Docker image:**
   ```bash
   docker-compose build --no-cache
   ```

3. **Start the application:**
   ```bash
   docker-compose up -d
   ```

4. **Check the logs:**
   ```bash
   docker-compose logs -f
   ```

## Troubleshooting Common Issues

### 1. Database Connection Issues

**Problem:** Cannot connect to Supabase database

**Solutions:**
- Verify your Supabase connection string is correct
- Check if your IP is whitelisted in Supabase
- Ensure the database is active and not paused
- Test connection manually:
  ```bash
  python migrate_db.py
  ```

### 2. Video Upload/Processing Issues

**Problem:** Videos not saving or processing correctly

**Solutions:**
- Check if the `static/uploads` directory exists and has proper permissions
- Ensure ffmpeg is properly installed in the container
- Check Docker logs for specific error messages:
  ```bash
  docker-compose logs tkdai-app
  ```

### 3. Port Issues

**Problem:** Application not accessible on expected port

**Solutions:**
- Ensure port 5002 is not being used by another application
- Check if the container is running:
  ```bash
  docker-compose ps
  ```
- Verify port mapping in docker-compose.yml

### 4. File Permission Issues

**Problem:** Cannot write to uploads directory

**Solutions:**
- The Docker container runs as a non-root user for security
- Ensure the static directory is properly mounted
- Check file permissions on the host:
  ```bash
  ls -la static/uploads/
  ```

### 5. Memory Issues

**Problem:** Application crashes or runs slowly

**Solutions:**
- Increase Docker memory allocation (recommended: 4GB+)
- Check system resources:
  ```bash
  docker stats
  ```

## Environment Variables

The application is configured with the following environment variables:

```bash
# Database (already configured)
DATABASE_URL=postgresql://postgres:Sc123034!@db.imvteekyazlzrtvooknh.supabase.co:5432/postgres

# Flask settings
FLASK_ENV=production
FLASK_APP=app.py

# Optional: Custom secret key
SECRET_KEY=your-custom-secret-key-here
```

## Production Deployment

For production deployment, consider:

1. **Using a reverse proxy (nginx):**
   ```yaml
   # Add to docker-compose.yml
   nginx:
     image: nginx:alpine
     ports:
       - "80:80"
       - "443:443"
     volumes:
       - ./nginx.conf:/etc/nginx/nginx.conf
     depends_on:
       - tkdai-app
   ```

2. **Setting up SSL certificates**

3. **Setting up monitoring and logging**

## Maintenance

### Updating the Application

1. **Pull latest changes:**
   ```bash
   git pull origin main
   ```

2. **Rebuild and restart:**
   ```bash
   ./deploy.sh
   ```

### Database Backup

Since you're using Supabase, backups are handled automatically. However, you can export data:

```bash
# Export specific tables (if needed)
docker-compose exec tkdai-app python -c "
from app import app, db
from models import User, LibraryItem
import json

with app.app_context():
    users = User.query.all()
    data = [{'id': u.id, 'username': u.username, 'email': u.email} for u in users]
    with open('users_backup.json', 'w') as f:
        json.dump(data, f)
"
```

### File Backup

```bash
# Backup uploads
tar -czf uploads-backup.tar.gz static/uploads/
```

## Support

If you encounter issues not covered in this guide:

1. Check the Docker logs: `docker-compose logs tkdai-app`
2. Verify database connection: `python migrate_db.py`
3. Ensure all prerequisites are met
4. Check the application logs for specific error messages

## Security Notes

- The application runs as a non-root user in the container
- File uploads are restricted to 256MB maximum
- Session cookies are configured for security in production
- Database is stored in Supabase with automatic backups
- Connection string includes credentials (consider using environment variables for production) 