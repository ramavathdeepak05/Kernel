# ALIS Frontend — Production multi-stage build
# Stage 1: Build the React app
FROM node:20-alpine AS builder

WORKDIR /app

COPY package.json package-lock.json ./
RUN npm ci --ignore-scripts

COPY . .
RUN npm run build

# Stage 2: Serve with nginx
FROM nginx:1.27-alpine

# Security: non-root nginx
RUN addgroup -S alis && adduser -S -G alis alis

COPY --from=builder /app/dist /usr/share/nginx/html
COPY nginx.conf /etc/nginx/conf.d/default.conf

# nginx needs to write to these dirs
RUN chown -R alis:alis /var/cache/nginx /var/log/nginx /etc/nginx/conf.d \
    && touch /var/run/nginx.pid && chown alis:alis /var/run/nginx.pid

USER alis

EXPOSE 3000

HEALTHCHECK --interval=30s --timeout=3s --retries=3 \
    CMD wget -q --spider http://localhost:3000/ || exit 1

CMD ["nginx", "-g", "daemon off;"]
