# Docker Setup for Full-Stack Project

This directory contains Docker configuration files for running your Django backend and Angular frontend in both development and production environments.

## Files Overview

### Backend Docker Configuration

- `backend/myproject/Dockerfile` - Development Dockerfile using Django's runserver
- `backend/myproject/Dockerfile.prod` - Production Dockerfile using Gunicorn
- `backend/myproject/.dockerignore` - Files to exclude from Docker build context

### Frontend Docker Configuration

- `frontend/Dockerfile` - Production Dockerfile for Angular application
- `frontend/.dockerignore` - Files to exclude from Docker build context
- `frontend/nginx.conf` - Nginx configuration for serving Angular app

### Docker Compose Files

- `docker-compose.yml` - Development setup with MySQL database, Django backend, and Angular frontend
- `docker-compose.prod.yml` - Production setup with MySQL, Gunicorn, Nginx, and Angular

### Nginx Configuration

- `nginx/nginx.conf` - Main Nginx configuration
- `nginx/default.conf` - Site-specific configuration for serving both frontend and backend

### Environment

- `.env.example` - Template for production environment variables

## Development Setup

1. **Start the development environment:**

   ```bash
   docker-compose up --build
   ```

2. **Run migrations (first time only):**

   ```bash
   docker-compose exec backend python manage.py migrate
   ```

3. **Create a superuser (first time only):**

   ```bash
   docker-compose exec backend python manage.py createsuperuser
   ```

4. **Access the application:**
   - Frontend (Angular): http://localhost:4200
   - Backend API: http://localhost:8000
   - Admin panel: http://localhost:8000/admin

## Production Setup

1. **Prepare environment variables:**

   ```bash
   cp .env.example .env
   # Edit .env with your production values
   ```

2. **Start the production environment:**

   ```bash
   docker-compose -f docker-compose.prod.yml up --build -d
   ```

3. **Run migrations (first time only):**

   ```bash
   docker-compose -f docker-compose.prod.yml exec backend python manage.py migrate
   ```

4. **Create a superuser (first time only):**

   ```bash
   docker-compose -f docker-compose.prod.yml exec backend python manage.py createsuperuser
   ```

5. **Collect static files:**

   ```bash
   docker-compose -f docker-compose.prod.yml exec backend python manage.py collectstatic --noinput
   ```

6. **Access the application:**
   - Full application: http://localhost (served by Nginx)
   - Frontend and backend are served through the same port

## Useful Commands

### Development

- View logs: `docker-compose logs -f backend`
- Stop services: `docker-compose down`
- Rebuild without cache: `docker-compose build --no-cache`

### Production

- View logs: `docker-compose -f docker-compose.prod.yml logs -f`
- View specific service logs: `docker-compose -f docker-compose.prod.yml logs -f frontend`
- Stop services: `docker-compose -f docker-compose.prod.yml down`
- Update code: `docker-compose -f docker-compose.prod.yml up --build -d`

## Database Management

### Backup Database

```bash
docker-compose exec db mysqldump -u root -p myproject > backup.sql
```

### Restore Database

```bash
docker-compose exec -T db mysql -u root -p myproject < backup.sql
```

## SSL Configuration (Production)

1. Create SSL certificates in `nginx/ssl/` directory:

   - `nginx/ssl/cert.pem`
   - `nginx/ssl/key.pem`

2. Update `nginx/default.conf` to include SSL configuration

## Troubleshooting

### Database Connection Issues

- Ensure MySQL container is running: `docker-compose ps`
- Check database logs: `docker-compose logs db`

### Static Files Not Loading

- Run collectstatic command: `docker-compose exec backend python manage.py collectstatic --noinput`
- Check Nginx configuration

### Frontend Not Loading

- Check frontend build: `docker-compose logs frontend`
- Verify nginx configuration for serving Angular app
- Ensure API endpoints are correctly configured in Angular

### Permission Issues

- Ensure proper file permissions for media and static directories
- Check Docker volume mounts

## Security Notes

1. Change default passwords in `.env` file
2. Use strong Django secret key
3. Keep all dependencies updated
4. Enable HTTPS in production
5. Configure firewall rules appropriately
6. Set proper CORS settings for API communication
7. Use environment-specific API endpoints in Angular
