# Use Python 3.11 slim image as base
FROM python:3.14

# Set environment variables
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

# Set work directory
WORKDIR /app

# Install system dependencies
RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        default-libmysqlclient-dev \
        build-essential \
    && rm -rf /var/lib/apt/lists/*
# CMD ["python", "--version"]
# RUN pip install --upgrade pip 
# RUN python -m pip install --upgrade pip 
# CMD ["pip", "--version"]

# Install Python dependencies
COPY requirements.txt /app/
RUN pip install --no-cache-dir -r requirements.txt

# Copy project
COPY . /app/

# Create static files directory
RUN mkdir -p /app/staticfiles

# Collect static files
RUN python manage.py collectstatic --noinput

# Expose port
EXPOSE 8000

# Run the application
CMD ["python", "manage.py", "runserver", "0.0.0.0:8000"]
# ENTRYPOINT ["bash"]