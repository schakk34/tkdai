#!/usr/bin/env python3
"""
Database migration script for TKD AI application
This script will create all necessary tables in your Supabase PostgreSQL database
"""

import os
import sys
from flask import Flask
from models import db, User, Role, LibraryItem, Progress, UserActivity, Message, VideoComment, CustomEvent, PracticeVideo, VideoFavorite

# Create a minimal Flask app for database operations
app = Flask(__name__)
app.config['SQLALCHEMY_DATABASE_URI'] = 'postgresql://postgres.imvteekyazlzrtvooknh:Sc123034!@aws-0-us-east-1.pooler.supabase.com:6543/postgres'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

db.init_app(app)

def migrate_database():
    """Create all database tables"""
    with app.app_context():
        print("🔄 Creating database tables...")
        
        try:
            # Create all tables
            db.create_all()
            print("✅ All tables created successfully!")
            
            # Check if admin user exists
            admin = User.query.filter_by(role=Role.ADMIN).first()
            if not admin:
                print("⚠️  No admin user found. You'll need to create one after deployment.")
                print("   Use: flask create-admin <username> <email> <password>")
            else:
                print(f"✅ Admin user found: {admin.username}")
                
        except Exception as e:
            print(f"❌ Error creating tables: {str(e)}")
            return False
            
        return True

def check_connection():
    """Test database connection"""
    with app.app_context():
        try:
            # Try to execute a simple query
            db.session.execute('SELECT 1')
            print("✅ Database connection successful!")
            return True
        except Exception as e:
            print(f"❌ Database connection failed: {str(e)}")
            return False

if __name__ == '__main__':
    print("🚀 TKD AI Database Migration")
    print("=" * 40)
    
    # Test connection first
    if not check_connection():
        print("❌ Cannot proceed without database connection")
        sys.exit(1)
    
    # Run migration
    if migrate_database():
        print("\n🎉 Database migration completed successfully!")
        print("You can now deploy your application.")
    else:
        print("\n❌ Database migration failed!")
        sys.exit(1) 