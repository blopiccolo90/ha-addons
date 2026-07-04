#!/usr/bin/with-contenv bashio

export MQTT_HOST=$(bashio::config 'mqtt_host')
export MQTT_PORT=$(bashio::config 'mqtt_port')
export MQTT_USER=$(bashio::config 'mqtt_user')
export MQTT_PASSWORD=$(bashio::config 'mqtt_password')
export SLEEP_TIME=$(bashio::config 'sleep_time')
export T_MIN_RANGE=$(bashio::config 't_min_range')
export T_MAX_RANGE=$(bashio::config 't_max_range')
export UPS_NAME=$(bashio::config 'ups_name')
export OLED_ENABLED=$(bashio::config 'oled_enabled')

bashio::log.info "Avvio RGB Hat Monitor..."
bashio::log.info "MQTT broker: ${MQTT_HOST}:${MQTT_PORT}"

exec python3 /monitor.py
