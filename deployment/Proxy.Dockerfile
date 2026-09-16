FROM caddy:2-alpine
RUN setcap -r /usr/bin/caddy && mkdir -p /data /config /system && chown -R 10001:10001 /data /config /system
USER 10001:10001
