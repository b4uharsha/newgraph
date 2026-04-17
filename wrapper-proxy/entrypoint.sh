#!/bin/sh
set -eu

NGINX_CONF="/etc/nginx/nginx.conf"

# Fail fast with a clear error if config is invalid
nginx -t

# Run in foreground and make nginx the PID 1 process
exec nginx -g 'daemon off;'
