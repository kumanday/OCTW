FROM nginx:1.27-alpine

RUN apk add --no-cache bash gettext openssl

COPY docker/proxy/entrypoint.sh /entrypoint.sh
COPY configs/nginx/default.conf.template /etc/nginx/templates/default.conf.template

RUN chmod +x /entrypoint.sh

ENTRYPOINT ["/entrypoint.sh"]
CMD ["nginx", "-g", "daemon off;"]
