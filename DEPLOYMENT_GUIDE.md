# Production Deployment Guide
**Vanish Compute (VNC) v2.0**
**Last Updated:** 2026-03-03

---

## Table of Contents

1. [Prerequisites](#prerequisites)
2. [Quick Start](#quick-start)
3. [Production Deployment](#production-deployment)
4. [Configuration](#configuration)
5. [Security Hardening](#security-hardening)
6. [Monitoring & Observability](#monitoring--observability)
7. [Scaling](#scaling)
8. [Troubleshooting](#troubleshooting)

---

## Prerequisites

### System Requirements

| Component | Minimum | Recommended |
|-----------|---------|-------------|
| **CPU** | 4 cores | 8+ cores |
| **Memory** | 8 GB | 16+ GB |
| **Storage** | 50 GB SSD | 100+ GB NVMe |
| **Network** | 1 Gbps | 10 Gbps |

### Software Requirements

- Docker 20.10+
- Docker Compose 2.0+
- PostgreSQL 15+
- Redis 7+
- Python 3.10+

### Optional (for full features)

- NVIDIA GPU with drivers (for GPU workloads)
- libvirt (for VM support)
- Kubernetes cluster (for scaling)

---

## Quick Start

### 1. Clone Repository

```bash
git clone https://github.com/your-org/disposable-compute-platform.git
cd disposable-compute-platform
```

### 2. Set Environment Variables

```bash
# Copy example env file
cp .env.example .env

# Edit with your values
vim .env
```

### 3. Start Services

```bash
# Development
docker-compose up --build

# Production
docker-compose -f docker-compose.prod.yml up -d
```

### 4. Verify Deployment

```bash
# Check health
curl http://localhost:8000/health

# Expected response:
# {"status": "healthy", "checks": {...}}
```

---

## Production Deployment

### Step 1: Infrastructure Setup

#### Option A: Single Server (Small Scale)

```yaml
# docker-compose.prod.yml
version: '3.8'

services:
  api:
    image: disposable-compute-platform:latest
    restart: unless-stopped
    ports:
      - "8000:8000"
    environment:
      - AUTH_SECRET_KEY=${AUTH_SECRET_KEY}
      - DB_HOST=db
      - REDIS_HOST=redis
    volumes:
      - /var/run/docker.sock:/var/run/docker.sock
      - disposable-storage:/tmp/disposable-storage
    depends_on:
      - db
      - redis
    deploy:
      resources:
        limits:
          cpus: '4'
          memory: 8G

  db:
    image: postgres:15-alpine
    restart: unless-stopped
    volumes:
      - postgres-data:/var/lib/postgresql/data
    environment:
      - POSTGRES_PASSWORD=${DB_PASSWORD}
      - POSTGRES_DB=disposable_compute
    deploy:
      resources:
        limits:
          cpus: '2'
          memory: 4G

  redis:
    image: redis:7-alpine
    restart: unless-stopped
    command: redis-server --appendonly yes
    volumes:
      - redis-data:/data
    deploy:
      resources:
        limits:
          cpus: '1'
          memory: 2G

volumes:
  postgres-data:
  redis-data:
  disposable-storage:
```

#### Option B: Kubernetes (Large Scale)

```yaml
# k8s/deployment.yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: dcp-api
  labels:
    app: disposable-compute-platform
spec:
  replicas: 3
  selector:
    matchLabels:
      app: dcp-api
  template:
    metadata:
      labels:
        app: dcp-api
    spec:
      containers:
      - name: api
        image: disposable-compute-platform:latest
        ports:
        - containerPort: 8000
        env:
        - name: AUTH_SECRET_KEY
          valueFrom:
            secretKeyRef:
              name: dcp-secrets
              key: auth-secret
        - name: DB_HOST
          value: "dcp-db"
        - name: REDIS_HOST
          value: "dcp-redis"
        resources:
          requests:
            cpu: "1"
            memory: "2Gi"
          limits:
            cpu: "4"
            memory: "8Gi"
        volumeMounts:
        - name: docker-socket
          mountPath: /var/run/docker.sock
        - name: storage
          mountPath: /tmp/disposable-storage
      volumes:
      - name: docker-socket
        hostPath:
          path: /var/run/docker.sock
      - name: storage
        persistentVolumeClaim:
          claimName: dcp-storage-pvc
```

### Step 2: Database Initialization

```bash
# Create database
psql -U postgres -h localhost << EOF
CREATE DATABASE disposable_compute;
CREATE USER dcp_user WITH PASSWORD '${DB_PASSWORD}';
GRANT ALL PRIVILEGES ON DATABASE disposable_compute TO dcp_user;
EOF

# Run migrations (if any)
python scripts/migrate.py
```

### Step 3: SSL/TLS Configuration

#### Using Nginx Reverse Proxy

```nginx
# /etc/nginx/sites-available/dcp
server {
    listen 80;
    server_name preview.yourcompany.com;
    return 301 https://$server_name$request_uri;
}

server {
    listen 443 ssl http2;
    server_name preview.yourcompany.com;

    ssl_certificate /etc/letsencrypt/live/preview.yourcompany.com/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/preview.yourcompany.com/privkey.pem;
    
    ssl_protocols TLSv1.2 TLSv1.3;
    ssl_ciphers HIGH:!aNULL:!MD5;
    ssl_prefer_server_ciphers on;

    location / {
        proxy_pass http://localhost:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        
        # WebSocket support
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
        
        # Timeouts
        proxy_connect_timeout 60s;
        proxy_send_timeout 60s;
        proxy_read_timeout 60s;
    }
}
```

#### Install SSL Certificate

```bash
# Install certbot
apt-get install certbot python3-certbot-nginx

# Get certificate
certbot --nginx -d preview.yourcompany.com

# Auto-renewal
certbot renew --dry-run
```

### Step 4: Firewall Configuration

```bash
# Allow HTTP/HTTPS
ufw allow 80/tcp
ufw allow 443/tcp

# Allow SSH (change port in production)
ufw allow 22/tcp

# Enable firewall
ufw enable

# Verify
ufw status
```

---

## Configuration

### Environment Variables

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `AUTH_SECRET_KEY` | ✅ | - | JWT signing key (32+ chars) |
| `DB_HOST` | ✅ | localhost | PostgreSQL host |
| `DB_PORT` | ✅ | 5432 | PostgreSQL port |
| `DB_NAME` | ✅ | disposable_compute | Database name |
| `DB_USER` | ✅ | postgres | Database user |
| `DB_PASSWORD` | ✅ | - | Database password |
| `REDIS_HOST` | ✅ | localhost | Redis host |
| `REDIS_PORT` | ✅ | 6379 | Redis port |
| `DOMAIN` | ✅ | preview.yourapp.dev | Base domain |
| `DEFAULT_TTL` | ✅ | 30 | Default session TTL (minutes) |
| `MAX_TTL` | ✅ | 1440 | Maximum session TTL (minutes) |
| `STORAGE_PATH` | ✅ | /tmp/disposable-storage | Storage directory |
| `MAX_CONCURRENT_SESSIONS` | ✅ | 50 | Max concurrent sessions |
| `ALLOWED_ORIGINS` | ❌ | * | CORS allowed origins |

### Generate Secure Keys

```bash
# Generate AUTH_SECRET_KEY
python -c "import secrets; print(secrets.token_urlsafe(32))"

# Generate DB_PASSWORD
openssl rand -base64 32

# Generate JWT signing key
openssl rand -hex 32
```

---

## Security Hardening

### 1. Container Security

```yaml
# Add to docker-compose.yml
services:
  api:
    security_opt:
      - no-new-privileges:true
    read_only: true
    tmpfs:
      - /tmp:noexec,nosuid,size=512m
    cap_drop:
      - ALL
    cap_add:
      - NET_BIND_SERVICE
    user: "1000:1000"
```

### 2. Network Policies (Kubernetes)

```yaml
# k8s/network-policy.yaml
apiVersion: networking.k8s.io/v1
kind: NetworkPolicy
metadata:
  name: dcp-network-policy
spec:
  podSelector:
    matchLabels:
      app: dcp-api
  policyTypes:
  - Ingress
  - Egress
  ingress:
  - from:
    - namespaceSelector:
        matchLabels:
          name: ingress
    ports:
    - protocol: TCP
      port: 8000
  egress:
  - to:
    - namespaceSelector:
        matchLabels:
          name: database
    ports:
    - protocol: TCP
      port: 5432
  - to:
    - namespaceSelector:
        matchLabels:
          name: cache
    ports:
    - protocol: TCP
      port: 6379
```

### 3. Secrets Management

```bash
# Create Kubernetes secrets
kubectl create secret generic dcp-secrets \
  --from-literal=auth-secret=$(python -c "import secrets; print(secrets.token_urlsafe(32))") \
  --from-literal=db-password=$(openssl rand -base64 32) \
  --from-literal=redis-password=$(openssl rand -base64 32)
```

### 4. Rate Limiting

Already configured in the application. Adjust limits in:
- `src/api/middleware/rate_limit.py`

### 5. Audit Logging

Enable audit logging:
```bash
# In .env
LOG_LEVEL=INFO
AUDIT_LOG_PATH=/var/log/dcp/audit.log
```

---

## Monitoring & Observability

### 1. Prometheus Metrics

```yaml
# Add to docker-compose.yml
services:
  prometheus:
    image: prom/prometheus:latest
    ports:
      - "9090:9090"
    volumes:
      - ./monitoring/prometheus.yml:/etc/prometheus/prometheus.yml
      - prometheus-data:/prometheus
    command:
      - '--config.file=/etc/prometheus/prometheus.yml'
      - '--storage.tsdb.path=/prometheus'

  grafana:
    image: grafana/grafana:latest
    ports:
      - "3000:3000"
    environment:
      - GF_SECURITY_ADMIN_PASSWORD=${GRAFANA_PASSWORD}
    volumes:
      - grafana-data:/var/lib/grafana
    depends_on:
      - prometheus

volumes:
  prometheus-data:
  grafana-data:
```

### 2. Health Check Endpoints

```bash
# Basic health
GET /health

# Detailed health
GET /healthz

# Metrics
GET /metrics
```

### 3. Log Aggregation

```yaml
# Using Loki
services:
  loki:
    image: grafana/loki:latest
    ports:
      - "3100:3100"
    command: -config.file=/etc/loki/local-config.yaml

  promtail:
    image: grafana/promtail:latest
    volumes:
      - /var/log:/var/log
      - ./promtail-config.yml:/etc/promtail/config.yml
    command: -config.file=/etc/promtail/config.yml
```

---

## Scaling

### Horizontal Scaling

```bash
# Docker Swarm
docker service scale disposable-compute-platform_api=5

# Kubernetes
kubectl scale deployment dcp-api --replicas=5
```

### Vertical Scaling

Increase resource limits:
```yaml
# In docker-compose.yml or k8s deployment
resources:
  limits:
    cpus: '8'
    memory: 16G
```

### Database Scaling

```sql
-- Add read replicas
SELECT * FROM pg_create_physical_replication_slot('replica_1');

-- Configure connection pooling
-- In pgbouncer.ini
[pgbouncer]
pool_mode = transaction
max_client_conn = 1000
default_pool_size = 20
```

---

## Troubleshooting

### Common Issues

#### 1. Database Connection Failed

```bash
# Check PostgreSQL is running
docker-compose ps db

# Check connection
psql -U postgres -h localhost -d disposable_compute

# Check logs
docker-compose logs db
```

#### 2. Redis Connection Failed

```bash
# Check Redis is running
docker-compose ps redis

# Test connection
redis-cli -h localhost ping

# Check logs
docker-compose logs redis
```

#### 3. Container Creation Failed

```bash
# Check Docker socket permissions
ls -la /var/run/docker.sock

# Should be: srw-rw----  root docker

# Add user to docker group
usermod -aG docker $USER
```

#### 4. High Memory Usage

```bash
# Check session count
curl http://localhost:8000/stats | jq '.platform.active_sessions'

# Cleanup expired sessions
# (Automatic, but can force)
docker-compose restart api
```

#### 5. GPU Not Detected

```bash
# Check NVIDIA drivers
nvidia-smi

# Check Docker NVIDIA runtime
docker run --rm --gpus all nvidia/cuda:11.0-base nvidia-smi
```

### Logs

```bash
# View all logs
docker-compose logs -f

# View specific service
docker-compose logs -f api

# View last 100 lines
docker-compose logs --tail=100 api

# Export logs
docker-compose logs api > api-logs.txt
```

### Debug Mode

```bash
# Enable debug logging
# In .env
LOG_LEVEL=DEBUG

# Restart
docker-compose restart api
```

---

## Backup & Recovery

### Database Backup

```bash
# Backup
pg_dump -U postgres -h localhost disposable_compute > backup-$(date +%Y%m%d).sql

# Restore
psql -U postgres -h localhost disposable_compute < backup-20260303.sql
```

### Redis Backup

```bash
# Trigger BGSAVE
redis-cli BGSAVE

# Copy RDB file
cp /var/lib/redis/dump.rdb backup-redis-$(date +%Y%m%d).rdb
```

### Volume Backup

```bash
# Backup storage volume
tar -czf storage-backup-$(date +%Y%m%d).tar.gz /var/lib/disposable-storage

# Restore
tar -xzf storage-backup-20260303.tar.gz -C /var/lib/
```

---

## Performance Tuning

### Database

```sql
-- Add indexes
CREATE INDEX CONCURRENTLY idx_sessions_created_at ON sessions(created_at);
CREATE INDEX CONCURRENTLY idx_sessions_user_status ON sessions(user_id, status);

-- Analyze tables
ANALYZE sessions;
ANALYZE pods;
```

### Redis

```conf
# In redis.conf
maxmemory 2gb
maxmemory-policy allkeys-lru
appendonly yes
appendfsync everysec
```

### Application

```python
# In src/services/platform.py
# Adjust cache TTL
config.redis_cache_ttl = 300  # 5 minutes

# Adjust cleanup interval
config.cleanup_interval = 300  # 5 minutes
```

---

## Support

For issues and questions:
- GitHub Issues: https://github.com/your-org/disposable-compute-platform/issues
- Documentation: https://docs.yourcompany.com/dcp
- Email: support@yourcompany.com

---

*Last Updated: 2026-03-03*
*Version: 2.0.0*
