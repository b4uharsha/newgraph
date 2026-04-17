# Wrapper Proxy Dockerfile
# HSBC Standard Build

FROM nexus3.systems.uk.hsbc:18080/com/hsbc/fcr/gcp/dra/core_engineering/nginx:latest

LABEL noSecretInContainerImageMetadata="confirmed"

USER root

COPY entrypoint.sh /docker-entrypoint.sh
COPY nginx.conf /etc/nginx/nginx.conf

RUN chown -R nginx:nginx /etc/nginx && \
    chmod -R 777 /etc/nginx && \
    mkdir -p /var/lib/nginx \
             /var/cache/nginx/client_temp \
             /var/cache/nginx/fastcgi_temp \
             /var/cache/nginx/proxy_temp \
             /var/cache/nginx/uwsgi_temp \
             /var/cache/nginx/scgi_temp && \
    chmod -R 777 /var/lib/nginx && \
    chmod -R 777 /var/cache/nginx && \
    chmod -R 777 /var/log/nginx && \
    chmod 755 /docker-entrypoint.sh

USER nginx

EXPOSE 8080

ENTRYPOINT ["/docker-entrypoint.sh"]
