FROM node:20-alpine AS builder

WORKDIR /app
COPY package*.json ./
RUN npm install
COPY . .
RUN npm run build

FROM nginx:alpine
COPY --from=builder /app/dist /usr/share/nginx/html
COPY nginx.conf.template /etc/nginx/templates/default.conf.template
COPY start.sh /start.sh
RUN chmod +x /start.sh

# Default backend host — override in Railway → Variables to the real private name.
ENV BACKEND_HOST=dashboard-backend.railway.internal:8002

EXPOSE 80

# Bypass the nginx image's envsubst entrypoint (it doesn't reliably pass
# NGINX_LOCAL_RESOLVERS to envsubst on Railway). start.sh extracts the
# nameserver from /etc/resolv.conf directly and runs envsubst itself.
ENTRYPOINT []
CMD ["/start.sh"]
