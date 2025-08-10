# Use official Python image
FROM python:3.11-slim

# Install system deps for Playwright and lxml if needed
RUN apt-get update && apt-get install -y \
    build-essential \
    libxml2-dev libxslt1-dev zlib1g-dev libffi-dev curl \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# copy files
COPY . /app

# install python deps
RUN pip install --upgrade pip
RUN pip install -r requirements.txt

# Optional: install playwright browsers if using playwright
ARG INSTALL_PLAYWRIGHT=false
RUN if [ "$INSTALL_PLAYWRIGHT" = "true" ]; then \
      playwright install --with-deps; \
    fi

# expose port
EXPOSE 5000

CMD ["gunicorn", "telegram_auth_backend:app", "-b", "0.0.0.0:5000", "--workers", "2", "--threads", "4"]
