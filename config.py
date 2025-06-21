import os
from datetime import timedelta

class Config:
    """Base configuration class"""
    SECRET_KEY = os.environ.get('SECRET_KEY') or os.urandom(24)
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    MAX_CONTENT_LENGTH = 256 * 1024 * 1024  # 256MB max file size
    
    # File upload settings
    UPLOAD_FOLDER = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'static', 'uploads')
    
    # Session settings
    PERMANENT_SESSION_LIFETIME = timedelta(hours=24)
    
    @staticmethod
    def init_app(app):
        pass

class DevelopmentConfig(Config):
    """Development configuration"""
    DEBUG = True
    SQLALCHEMY_DATABASE_URI = 'sqlite:///tkdai.db'
    
    # Ensure upload directory exists
    @staticmethod
    def init_app(app):
        Config.init_app(app)
        os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)

class ProductionConfig(Config):
    """Production configuration"""
    DEBUG = False
    # Use Supabase Transaction Pooler for better IPv4 compatibility
    SQLALCHEMY_DATABASE_URI = os.environ.get('DATABASE_URL') or 'postgresql://postgres.imvteekyazlzrtvooknh:Sc123034!@aws-0-us-east-1.pooler.supabase.com:6543/postgres'
    
    # Production-specific settings
    SESSION_COOKIE_SECURE = True
    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = 'Lax'
    
    @staticmethod
    def init_app(app):
        Config.init_app(app)
        os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)

class DockerConfig(ProductionConfig):
    """Docker-specific configuration"""
    # Use Supabase Transaction Pooler for Docker deployment
    SQLALCHEMY_DATABASE_URI = os.environ.get('DATABASE_URL') or 'postgresql://postgres.imvteekyazlzrtvooknh:Sc123034!@aws-0-us-east-1.pooler.supabase.com:6543/postgres'
    
    @staticmethod
    def init_app(app):
        ProductionConfig.init_app(app)
        # Ensure all necessary directories exist
        os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)
        os.makedirs(os.path.join(app.root_path, 'static', 'thumbnails'), exist_ok=True)

config = {
    'development': DevelopmentConfig,
    'production': ProductionConfig,
    'docker': DockerConfig,
    'default': DevelopmentConfig
} 