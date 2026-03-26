# SSL Certificate Setup — ALIS

## Development (self-signed)

```bash
cd nginx/certs

openssl req -x509 -newkey rsa:4096 \
  -keyout key.pem -out cert.pem \
  -days 365 -nodes \
  -subj "/C=IN/ST=Telangana/L=Hyderabad/O=ALIS Dev/CN=localhost"
```

Certificates land in `nginx/certs/` which is bind-mounted into the nginx container.
The `nginx/nginx.conf` already references `key.pem` / `cert.pem`.

Start the stack:

```bash
docker compose up -d
```

## Production (Let's Encrypt via Certbot)

### One-time certificate issuance

```bash
# Stop nginx temporarily so port 80 is free for the ACME challenge
docker compose stop nginx

sudo certbot certonly --standalone \
  -d alis.yourinstitution.edu \
  --agree-tos \
  --email devops@yourinstitution.edu

# Copy to nginx/certs/
sudo cp /etc/letsencrypt/live/alis.yourinstitution.edu/fullchain.pem nginx/certs/cert.pem
sudo cp /etc/letsencrypt/live/alis.yourinstitution.edu/privkey.pem  nginx/certs/key.pem
sudo chown $USER:$USER nginx/certs/*.pem

docker compose start nginx
```

### Automated renewal (cron)

```bash
sudo crontab -e
# Add:
0 3 * * * certbot renew --quiet && \
  cp /etc/letsencrypt/live/alis.yourinstitution.edu/fullchain.pem /path/to/nginx/certs/cert.pem && \
  cp /etc/letsencrypt/live/alis.yourinstitution.edu/privkey.pem  /path/to/nginx/certs/key.pem && \
  docker exec alis_nginx nginx -s reload
```

Certbot auto-renews 30 days before expiry. The cron runs at 03:00 daily — if renewal
happened, nginx is reloaded without downtime.

### Verify certificate

```bash
openssl s_client -connect alis.yourinstitution.edu:443 -servername alis.yourinstitution.edu < /dev/null \
  | openssl x509 -noout -dates
```

## nginx.conf SSL block (already configured)

`nginx/nginx.conf` listens on 443 with:

```nginx
ssl_certificate     /etc/nginx/certs/cert.pem;
ssl_certificate_key /etc/nginx/certs/key.pem;
ssl_protocols       TLSv1.2 TLSv1.3;
ssl_ciphers         HIGH:!aNULL:!MD5;
```

HTTP → HTTPS redirect is already active on port 80.

## Multi-SAN (multiple campuses on one cert)

For a GROUP org with multiple campus domains:

```bash
sudo certbot certonly --standalone \
  -d alis.woxsen.edu.in \
  -d alis.campus2.edu.in \
  -d alis.campus3.edu.in \
  --agree-tos --email devops@woxsen.edu.in
```

## Wildcard certificate (optional)

```bash
sudo certbot certonly --manual \
  --preferred-challenges dns \
  -d "*.yourinstitution.edu" \
  --agree-tos --email devops@yourinstitution.edu
# Follow DNS TXT record challenge instructions
```

## Troubleshooting

| Symptom | Fix |
|---|---|
| `NET::ERR_CERT_AUTHORITY_INVALID` | Self-signed cert in browser — add to trusted store or use prod cert |
| `certbot: port 80 in use` | Stop nginx before running standalone certbot |
| `nginx: [warn] "ssl_stapling" ignored` | OCSP stapling needs a full chain cert — use `fullchain.pem` not `cert.pem` |
| Cert expired in prod | Check cron job ran: `sudo crontab -l` and `journalctl -u cron` |
