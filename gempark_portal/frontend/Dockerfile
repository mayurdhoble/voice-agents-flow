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
RUN sed -i 's/\r//' /start.sh && chmod +x /start.sh

# Public URL of the Gem Park portal backend — set in Railway → Variables.
ENV BACKEND_URL=https://gempark-portal-backend.up.railway.app

EXPOSE 80

ENTRYPOINT []
CMD ["/start.sh"]
