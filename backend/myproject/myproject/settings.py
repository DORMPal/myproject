"""
Django settings for myproject project.
"""

import os
from pathlib import Path
from dotenv import load_dotenv

# Build paths inside the project like this: BASE_DIR / 'subdir'.
BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BASE_DIR / '.env')


# SECURITY WARNING: keep the secret key used in production secret!
SECRET_KEY = os.getenv('DJANGO_SECRET_KEY', 'django-insecure-default-key')

# SECURITY WARNING: don't run with debug turned on in production!
DEBUG = True

ALLOWED_HOSTS = ['localhost', '127.0.0.1', 'backend'] # เพิ่ม 'backend' เผื่อ container คุยกันเอง

CSRF_TRUSTED_ORIGINS = [
    "http://localhost:4200",
    "http://127.0.0.1:4200",
]

# Application definition
INSTALLED_APPS = [
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    'django.contrib.sites',
    
    # 3rd Party Apps
    'allauth',
    'allauth.account',
    'allauth.socialaccount',
    'allauth.socialaccount.providers.google',
    'rest_framework',
    "corsheaders",
    
    # ✅ Scheduler App (ต้องมีบรรทัดนี้ ไม่งั้น Error)
    "django_apscheduler", 
    
    # My Apps
    'recipes',
]

MIDDLEWARE = [
    "corsheaders.middleware.CorsMiddleware", # CORS ควรอยู่อันแรกๆ
    "django.middleware.common.CommonMiddleware",
    'django.middleware.security.SecurityMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
    'allauth.account.middleware.AccountMiddleware',
]

ROOT_URLCONF = 'myproject.urls'

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [BASE_DIR / 'templates'],
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
            ],
        },
    },
]

WSGI_APPLICATION = 'myproject.wsgi.application'

# Database
DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.mysql",
        "NAME": "myproject",
        "USER": "django_user",
        "PASSWORD": "strongpassword",
        # Config นี้รองรับทั้ง Docker และ Local
        "HOST": os.getenv("DB_HOST", "127.0.0.1"), 
        "PORT": os.getenv("DB_PORT", "3307"),
        "OPTIONS": {
            "charset": "utf8mb4",
        },
    },
    # สำรองเผื่ออยากใช้
    "sqlite": {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": BASE_DIR / "db.sqlite3",
    },
}

# Password validation
AUTH_PASSWORD_VALIDATORS = [
    { 'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator', },
    { 'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator', },
    { 'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator', },
    { 'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator', },
]

# --- Internationalization & Timezone ---
LANGUAGE_CODE = 'en-us'

# 🔥 แก้ไข: ลบบรรทัด TIME_ZONE = 'UTC' ด้านล่างทิ้ง ให้เหลือแค่อันนี้
TIME_ZONE = 'Asia/Bangkok' 

USE_I18N = True
USE_TZ = True

# --- Scheduler Settings ---
# กำหนด Format เวลาให้ดูง่าย
APSCHEDULER_DATETIME_FORMAT = "N j, Y, f:s a"
APSCHEDULER_RUN_NOW_TIMEOUT = 25  # Seconds

# --- Static files ---
STATIC_URL = 'static/'
STATIC_ROOT = BASE_DIR / 'staticfiles'

# --- CORS & CSRF ---
CORS_ALLOWED_ORIGINS = [
    "http://localhost:4200",
]
CORS_ALLOW_CREDENTIALS = True
SESSION_COOKIE_SAMESITE = "Lax"
CSRF_COOKIE_SAMESITE = "Lax"
SESSION_COOKIE_SECURE = False
CSRF_COOKIE_SECURE = False
SESSION_COOKIE_AGE = 1800
SESSION_SAVE_EVERY_REQUEST = True

# --- REST Framework ---
REST_FRAMEWORK = {
    'DEFAULT_RENDERER_CLASSES': [
        'rest_framework.renderers.JSONRenderer',
    ],
    'DEFAULT_PARSER_CLASSES': [
        'rest_framework.parsers.JSONParser',
    ],
}

# --- Authentication & Frontend ---
SITE_ID = 1
AUTHENTICATION_BACKENDS = [
    'django.contrib.auth.backends.ModelBackend',
    'allauth.account.auth_backends.AuthenticationBackend',
]

FRONTEND_URL = os.getenv('FRONTEND_URL', 'http://localhost:4200/')
LOGIN_REDIRECT_URL = FRONTEND_URL
LOGOUT_REDIRECT_URL = FRONTEND_URL

ACCOUNT_EMAIL_REQUIRED = True
ACCOUNT_EMAIL_VERIFICATION = 'none'
ACCOUNT_AUTHENTICATION_METHOD = 'email'
SOCIALACCOUNT_QUERY_EMAIL = True
SOCIALACCOUNT_PROVIDERS = {
    'google': {
        'SCOPE': ['profile', 'email'],
        'OAUTH_PKCE_ENABLED': True,
        'APP': {
            'client_id': os.getenv('GOOGLE_CLIENT_ID', ''),
            'secret': os.getenv('GOOGLE_CLIENT_SECRET', ''),
            'key': '',
        },
    }
}

DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'

# --- AI Configuration (Ollama) ---
# เพิ่มไว้เพื่อให้ views.py เรียกใช้ได้ (ค่า Default คือ docker service name)
OLLAMA_URL = os.getenv('OLLAMA_URL', 'http://ollama:11434/api/generate')