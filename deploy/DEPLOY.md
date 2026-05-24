# Deploying AI Discuss Room to why-server

## Prerequisites on why-server
- Python 3.11+
- MySQL 8 with database `discuss` and user `discuss` (charset utf8mb4)
- nginx
- systemd

## Steps

1. Clone and install:
   ```
   sudo mkdir -p /opt/discuss-room && sudo chown discuss:discuss /opt/discuss-room
   cd /opt/discuss-room
   git clone <repo-url> .
   python3.11 -m venv .venv
   .venv/bin/pip install -e ".[dev]"
   ```
2. Create DB & user (one-time):
   ```
   mysql -u root -p
   > CREATE DATABASE discuss CHARACTER SET utf8mb4;
   > CREATE USER 'discuss'@'localhost' IDENTIFIED BY 'somepass';
   > GRANT ALL ON discuss.* TO 'discuss'@'localhost';
   > FLUSH PRIVILEGES;
   ```
3. Migrate:
   ```
   DATABASE_URL="mysql+pymysql://discuss:somepass@127.0.0.1/discuss?charset=utf8mb4" \
     .venv/bin/alembic upgrade head
   ```
4. Install systemd unit:
   ```
   sudo cp deploy/discuss-room.service /etc/systemd/system/
   # edit /etc/systemd/system/discuss-room.service to set real DATABASE_URL + admin pass
   sudo systemctl daemon-reload
   sudo systemctl enable --now discuss-room
   sudo systemctl status discuss-room
   ```
5. Configure nginx:
   ```
   sudo cp deploy/nginx.conf.example /etc/nginx/sites-available/discuss-room
   sudo ln -s /etc/nginx/sites-available/discuss-room /etc/nginx/sites-enabled/
   sudo nginx -t && sudo systemctl reload nginx
   ```
6. Verify:
   ```
   curl http://discuss.why-server.internal/health
   ```

## v2 upgrades
- TLS (Let's Encrypt or internal CA)
- DB backups
- Log rotation
