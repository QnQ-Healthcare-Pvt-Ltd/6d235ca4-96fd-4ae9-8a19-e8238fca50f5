# Frontend Build Stage
FROM node:18-alpine AS frontend-build
WORKDIR /app/frontend
COPY ./frontend/package*.json ./
RUN npm install --production=false
COPY ./frontend/ ./
RUN npm run build

# Final Stage
FROM python:3.11-alpine
WORKDIR /app

# Install Node.js and other requirements including SQLite
RUN apk add --no-cache \
    nginx \
    supervisor \
    nodejs \
    npm \
    curl \
    bash \
    git \
    # Add SQLite dependencies
    sqlite \
    sqlite-dev \
    sqlite-libs \
    # Add build dependencies
    build-base \
    python3-dev \
    libffi-dev

# Copy frontend with its dependencies
COPY --from=frontend-build /app/frontend /app/frontend
COPY --from=frontend-build /app/frontend/.next /app/frontend/.next
COPY --from=frontend-build /app/frontend/node_modules /app/frontend/node_modules
COPY --from=frontend-build /app/frontend/package*.json /app/frontend/

# Copy backend
COPY backend /app/backend
# Install Python dependencies with pip upgrade
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r /app/backend/requirements.txt

# Create necessary directories
RUN mkdir -p /var/log/supervisor /var/log/nginx /run/nginx

# Copy configs
COPY config/nginx.conf /etc/nginx/nginx.conf
COPY config/supervisord.conf /etc/supervisor/conf.d/supervisord.conf

# Set permissions
RUN chmod -R 755 /app/frontend/.next && \
    chmod -R 755 /var/log/nginx && \
    chmod -R 755 /var/log/supervisor

# Health check
HEALTHCHECK --interval=30s --timeout=30s --start-period=5s --retries=3 \
    CMD curl -f http://localhost:3001/ || exit 1

EXPOSE 3000 3001 8001
CMD ["/usr/bin/supervisord", "-c", "/etc/supervisor/conf.d/supervisord.conf"]
