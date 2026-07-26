#!/bin/sh
set -e
NS=$(awk '/^nameserver/{print $2; exit}' /etc/resolv.conf 2>/dev/null)
[ -z "$NS" ] && NS="8.8.8.8"
case "$NS" in *:*) NS="[$NS]" ;; esac
# Always append a public DNS fallback so external domains resolve too
export NGINX_LOCAL_RESOLVERS="$NS 8.8.8.8"
export PORT="${PORT:-80}"
envsubst '${NGINX_LOCAL_RESOLVERS} ${BACKEND_HOST} ${PORT}' \
    < /etc/nginx/templates/default.conf.template \
    > /etc/nginx/conf.d/default.conf
exec nginx -g 'daemon off;'
