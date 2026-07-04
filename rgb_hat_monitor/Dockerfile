FROM ghcr.io/hassio-addons/base:15.0.4

# Pacchetti di sistema: python3, accesso i2c, font per l'OLED
# apk update + upgrade evita conflitti di versione tra musl (gia' nell'immagine
# base) e musl-dev (scaricato dal repository) durante la build.
RUN apk add --no-cache \
        python3 \
        py3-pip \
        i2c-tools \
        ttf-dejavu \
        jpeg-dev \
        zlib-dev \
        gcc \
        musl-dev \
        python3-dev \
        linux-headers

COPY requirements.txt /
RUN pip3 install --no-cache-dir --break-system-packages -r /requirements.txt

COPY monitor.py /monitor.py
COPY run.sh /
RUN chmod a+x /run.sh

ARG BUILD_VERSION
LABEL \
    io.hass.version="${BUILD_VERSION}" \
    io.hass.type="addon" \
    io.hass.arch="armhf|armv7|aarch64"

CMD [ "/run.sh" ]
