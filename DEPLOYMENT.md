# TKD AI Deployment Guide

## Prerequisites

- Docker and Docker Compose installed
- At least 4GB of available RAM
- Stable internet connection for initial build

## Quick Deployment

1. **Clone and navigate to the project directory:**
   ```bash
   cd tkdai
   ```

2. **Run the deployment script:**
   ```bash
   ./deploy.sh
   ```

3. **Access the application:**
   - Open your browser and go to `http://localhost:5002`
   - The application should be running and ready to use

## Manual Deployment

If you prefer to deploy manually:

1. **Build the Docker image:**
   ```bash
   docker-compose build --no-cache
   ```

2. **Start the application:**
   ```bash
   docker-compose up -d
   ```

3. **Check the logs:**
   ```bash
   docker-compose logs -f
   ```

## Troubleshooting Common Issues

### 1. Video Upload/Processing Issues

**Problem:** Videos not saving or processing correctly

**Solutions:**
- Check if the `static/uploads` directory exists and has proper permissions
- Ensure ffmpeg is properly installed in the container
- Check Docker logs for specific error messages:
  ```bash
  docker-compose logs tkdai-app
  ```

### 2. Database Issues

**Problem:** Database not persisting or connection errors

**Solutions:**
- The database is stored in a Docker volume (`tkdai-data`)
- To reset the database, remove the volume:
  ```bash
  docker-compose down
  docker volume rm tkdai_tkdai-data
  docker-compose up -d
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

You can customize the deployment by setting environment variables:

```bash
# In docker-compose.yml or as environment variables
FLASK_ENV=production
FLASK_APP=app.py
SECRET_KEY=your-secret-key-here
DATABASE_URL=sqlite:///instance/tkdai.db
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

3. **Using a production database (PostgreSQL/MySQL)**

4. **Setting up monitoring and logging**

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

### Backup and Restore

**Backup:**
```bash
# Backup database
docker-compose exec tkdai-app sqlite3 instance/tkdai.db ".backup backup.db"

# Backup uploads
tar -czf uploads-backup.tar.gz static/uploads/
```

**Restore:**
```bash
# Restore database
docker-compose exec tkdai-app sqlite3 instance/tkdai.db ".restore backup.db"

# Restore uploads
tar -xzf uploads-backup.tar.gz
```

## Support

If you encounter issues not covered in this guide:

1. Check the Docker logs: `docker-compose logs tkdai-app`
2. Verify all prerequisites are met
3. Ensure sufficient system resources
4. Check the application logs for specific error messages

## Security Notes

- The application runs as a non-root user in the container
- File uploads are restricted to 256MB maximum
- Session cookies are configured for security in production
- Database is stored in a Docker volume for persistence 