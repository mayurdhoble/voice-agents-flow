FROM node:20-alpine AS builder

WORKDIR /app
COPY package*.json ./
RUN npm install
COPY . .
RUN npm run build

FROM nginx:alpine
COPY --from=builder /app/dist /usr/share/nginx/html
# Rendered by the nginx image's envsubst entrypoint (fills NGINX_LOCAL_RESOLVERS
# + BACKEND_HOST) into /etc/nginx/conf.d/default.conf at startup.
COPY nginx.conf.template /etc/nginx/templates/default.conf.template

# Default backend host — override in Railway → Variables to the real private name.
ENV BACKEND_HOST=dashboard-backend.railway.internal:8002

EXPOSE 80
# Keep the base image's entrypoint (runs envsubst on templates) + its default CMD.
