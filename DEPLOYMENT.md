# CardFlow — Production Deployment Guide

This guide describes the complete, end-to-end production deployment process for the **CardFlow Enterprise Platform** (`v5.7.0+`).

---

## 🏗️ 1. Architecture Overview

In production, CardFlow runs as a decoupled, multi-service topology:

- **Reverse Proxy & SSL**: Nginx (terminates SSL, serves frontend static SPA files, proxies REST to Gunicorn and WebSockets to Daphne).
- **REST API Backend**: Django 5.2 running under Gunicorn (WSGI) or Daphne (ASGI).
- **Real-Time WebSockets**: Daphne (ASGI) on port 8001 / Unix socket.
- **Async Task Workers**: Celery worker pool connected to Redis broker.
- **Task Scheduler**: Celery Beat for scheduled maintenance and pool flushes.
- **Relational Database**: PostgreSQL 14+ with connection pooling.
- **Cache & Message Broker**: Redis 6+.
- **Biometric Face Cropper**: OpenCV FastAPI microservice (port 4765).
- **Frontend SPA**: Vite-compiled static bundle (`frontend/dist/`) served directly by Nginx.

---

## 📋 2. Prerequisites & Server Requirements

### Minimum Hardware
- **CPU**: 4 Cores (8 Cores recommended for high-volume face cropping & PDF generation)
- **RAM**: 8 GB (16 GB recommended)
- **Storage**: 50 GB+ SSD for database + scalable block storage / S3 for media files

### Required Software Packages (Ubuntu / Debian)
```bash
sudo apt update && sudo apt install -y \
    python3.11 python3.11-venv python3.11-dev \
    postgresql postgresql-contrib \
    redis-server \
    nginx \
    certbot python3-certbot-nginx \
    libpq-dev libjpeg-dev zlib1g-dev \
    libgl1-mesa-glx libglib2.0-0 \
    supervisor git curl
```

### Node.js (for frontend build)
```bash
curl -fsSL https://deb.nodesource.com/setup_20.x | sudo -E bash -
sudo apt install -y nodejs
```

---

## ⚙️ 3. Environment Configuration

### Backend `.env` Setup
Create `/opt/cardflow/backend/.env` with strict permissions (`chmod 600`):

```ini
# =============================================================================
# CardFlow Production Environment Configuration
# =============================================================================

# Security
DEBUG=False
SECRET_KEY=generate-a-strong-random-50-char-secret-key-do-not-share
ALLOWED_HOSTS=panel.yourdomain.com,api.yourdomain.com

# Database (PostgreSQL)
DATABASE_URL=postgres://cardflow_user:YOUR_STRONG_DB_PASSWORD@127.0.0.1:5432/cardflow_prod

# Redis Cache & Celery
REDIS_URL=redis://127.0.0.1:6379/0
CELERY_BROKER_URL=redis://127.0.0.1:6379/1
CELERY_RESULT_BACKEND=redis://127.0.0.1:6379/2

# Domain & CORS / CSRF
CORS_ALLOWED_ORIGINS=https://panel.yourdomain.com,https://yourdomain.com
CSRF_TRUSTED_ORIGINS=https://panel.yourdomain.com,https://yourdomain.com

# Landing Website API Integration Key (REQUIRED)
WEB_APP_API_KEY=generate-a-cryptographically-secure-key-here
LANDING_WEBSITE_URL=https://yourdomain.com

# SSL / HTTPS Security Headers (Set to True in production with SSL)
SECURE_SSL_REDIRECT=True
SESSION_COOKIE_SECURE=True
CSRF_COOKIE_SECURE=True
SECURE_HSTS_SECONDS=31536000
SECURE_HSTS_INCLUDE_SUBDOMAINS=True
SECURE_HSTS_PRELOAD=True

# Sentry Monitoring (Optional)
SENTRY_DSN=
SENTRY_ENVIRONMENT=production
SENTRY_TRACES_SAMPLE_RATE=0.1
SENTRY_PROFILES_SAMPLE_RATE=0.0
SENTRY_SEND_PII=False

# Storage (Local SSD or S3)
USE_S3=False
```

### Frontend Environment
Create `/opt/cardflow/frontend/.env.production`:

```ini
# If frontend is served on the same domain as API reverse proxy:
VITE_API_BASE_URL=

# If frontend is hosted on a separate CDN / subdomain:
# VITE_API_BASE_URL=https://api.yourdomain.com
```

---

## 🚀 4. Step-by-Step Installation & Build

### Step 1: Clone Repository
```bash
sudo mkdir -p /opt/cardflow
sudo chown -R $USER:$USER /opt/cardflow
cd /opt/cardflow
git clone -b main https://github.com/logicbyroshan/cardfloww-idcard-management.git .
```

### Step 2: Setup Python Virtual Environment
```bash
python3.11 -m venv venv
source venv/bin/activate
pip install --upgrade pip setuptools wheel
pip install -r backend/requirements.txt
```

### Step 3: Run Database Migrations
```bash
python manage.py migrate --noinput
```

### Step 4: Collect Static Files
```bash
python manage.py collectstatic --noinput
```

### Step 5: Create Initial Platform Super Admin
```bash
python manage.py createsuperuser
```
> [!IMPORTANT]
> Use a strong, unique passphrase (>12 characters) for the platform superuser. Never run `scripts/create_admin.py` in production as it contains hardcoded development passwords.

### Step 6: Build the Frontend SPA
```bash
cd /opt/cardflow/frontend
npm ci
npm run build
cd /opt/cardflow
```
This produces optimized production assets in `/opt/cardflow/frontend/dist/`.

---

## 🛠️ 5. Systemd Service Configurations

### 1. Gunicorn WSGI Service (`/etc/systemd/system/cardflow-api.service`)
```ini
[Unit]
Description=CardFlow Gunicorn REST API Server
After=network.target postgresql.service redis.service

[Service]
User=www-data
Group=www-data
WorkingDirectory=/opt/cardflow/backend
Environment="PATH=/opt/cardflow/venv/bin"
ExecStart=/opt/cardflow/venv/bin/gunicorn config.wsgi:application \
    --workers 4 \
    --worker-class gthread \
    --threads 2 \
    --bind 127.0.0.1:8000 \
    --timeout 120 \
    --access-logfile /var/log/cardflow/gunicorn-access.log \
    --error-logfile /var/log/cardflow/gunicorn-error.log

Restart=always
RestartSec=3

[Install]
WantedBy=multi-user.target
```

### 2. Daphne ASGI WebSockets Service (`/etc/systemd/system/cardflow-ws.service`)
```ini
[Unit]
Description=CardFlow Daphne ASGI WebSockets Server
After=network.target redis.service

[Service]
User=www-data
Group=www-data
WorkingDirectory=/opt/cardflow/backend
Environment="PATH=/opt/cardflow/venv/bin"
ExecStart=/opt/cardflow/venv/bin/daphne -b 127.0.0.1 -p 8001 config.asgi:application

Restart=always
RestartSec=3

[Install]
WantedBy=multi-user.target
```

### 3. Celery Worker Service (`/etc/systemd/system/cardflow-celery.service`)
```ini
[Unit]
Description=CardFlow Celery Async Task Worker
After=network.target redis.service

[Service]
User=www-data
Group=www-data
WorkingDirectory=/opt/cardflow/backend
Environment="PATH=/opt/cardflow/venv/bin"
ExecStart=/opt/cardflow/venv/bin/celery -A config worker -l INFO --concurrency=4

Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
```

---

## 🌐 6. Nginx Configuration

Create `/etc/nginx/sites-available/cardflow.conf`:

```nginx
upstream django_backend {
    server 127.0.0.1:8000;
}

upstream daphne_ws {
    server 127.0.0.1:8001;
}

server {
    listen 80;
    server_name panel.yourdomain.com;
    return 301 https://$host$request_uri;
}

server {
    listen 443 ssl http2;
    server_name panel.yourdomain.com;

    # SSL Certificate (Certbot will manage these paths)
    ssl_certificate /etc/letsencrypt/live/panel.yourdomain.com/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/panel.yourdomain.com/privkey.pem;
    include /etc/letsencrypt/options-ssl-nginx.conf;
    ssl_dhparam /etc/letsencrypt/ssl-dhparams.pem;

    # Security Headers
    add_header X-Content-Type-Options "nosniff" always;
    add_header X-Frame-Options "DENY" always;
    add_header X-XSS-Protection "1; mode=block" always;
    add_header Referrer-Policy "strict-origin-when-cross-origin" always;
    add_header Content-Security-Policy "default-src 'self'; img-src 'self' data: blob: https:; style-src 'self' 'unsafe-inline' https://fonts.googleapis.com; font-src 'self' https://fonts.gstatic.com; connect-src 'self' wss: ws: https:; script-src 'self';" always;

    client_max_body_size 100M;

    # Frontend SPA Root (Static build)
    root /opt/cardflow/frontend/dist;
    index index.html;

    # Frontend Route Handling (React SPA History Mode)
    location / {
        try_files $uri $uri/ /index.html;
    }

    # Django Static Files
    location /static/ {
        alias /opt/cardflow/backend/staticfiles/;
        expires 30d;
        add_header Cache-Control "public, no-transform";
    }

    # Protected Media Files
    location /media/ {
        alias /opt/cardflow/backend/media/;
        internal; # Protected via Django sendfile / custom views where applicable
    }

    # REST API Proxy
    location /api/ {
        proxy_pass http://django_backend;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_read_timeout 120s;
    }

    # WebSockets Proxy (Daphne)
    location /ws/ {
        proxy_pass http://daphne_ws;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_read_timeout 86400s;
        proxy_send_timeout 86400s;
    }
}
```

Enable the site and reload Nginx:
```bash
sudo ln -s /etc/nginx/sites-available/cardflow.conf /etc/nginx/sites-enabled/
sudo nginx -t
sudo systemctl reload nginx
```

---

## 🔍 7. Verification & Health Monitoring

### Test Health Endpoint
```bash
curl -i https://panel.yourdomain.com/api/health/
```
Expected response:
```json
HTTP/2 200
Content-Type: application/json

{"status": "healthy", "database": "connected", "cache": "connected"}
```

### Check Service Status
```bash
sudo systemctl status cardflow-api
sudo systemctl status cardflow-ws
sudo systemctl status cardflow-celery
sudo systemctl status redis
sudo systemctl status postgresql
```

---

## 🔒 8. Post-Deployment Security Checklist

- [ ] `DEBUG=False` in `/opt/cardflow/backend/.env`.
- [ ] `SECRET_KEY` is unique, random, and at least 50 characters.
- [ ] `WEB_APP_API_KEY` is set to a secure random string and updated in the landing website's config.
- [ ] `ALLOWED_HOSTS` matches only your valid domain names.
- [ ] `CORS_ALLOWED_ORIGINS` contains only your trusted frontends (no localhost origins).
- [ ] `CSRF_TRUSTED_ORIGINS` contains only your production domains.
- [ ] HTTPS is enforced with valid SSL certificate (`SECURE_SSL_REDIRECT=True`).
- [ ] Database user has least-privilege permissions on `cardflow_prod` database only.
- [ ] Server firewall (`ufw`) allows only ports 22, 80, and 443.

---

## 🔄 9. Updating the Production Deployment

When releasing a new version from `main`:

```bash
cd /opt/cardflow
git pull origin main
source venv/bin/activate
pip install -r backend/requirements.txt
python manage.py migrate --noinput
python manage.py collectstatic --noinput

cd frontend
npm ci
npm run build
cd ..

sudo systemctl restart cardflow-api cardflow-ws cardflow-celery
sudo systemctl reload nginx
```
