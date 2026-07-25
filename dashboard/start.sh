#!/bin/sh
set -e
NS=$(awk '/^nameserver/{print $2; exit}' /etc/resolv.conf 2>/dev/null)
[ -z "$NS" ] && NS="8.8.8.8"
# nginx requires IPv6 resolver addresses wrapped in brackets
case "$NS" in *:*) NS="[$NS]" ;; esac
export NGINX_LOCAL_RESOLVERS="$NS"
envsubst '${NGINX_LOCAL_RESOLVERS} ${BACKEND_HOST}' \
    < /etc/nginx/templates/default.conf.template \
    > /etc/nginx/conf.d/default.conf
exec nginx -g 'daemon off;'
