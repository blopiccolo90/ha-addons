#!/usr/bin/env python3
"""
RGB Hat Monitor -> MQTT bridge per Home Assistant (HAOS add-on).

Riprende la logica dello script originale (OLED SSD1306 128x32, fan e RGB
pilotati via I2C su un "hat" tipo Waveshare) e la espone come entita'
Home Assistant tramite MQTT Discovery:

  - sensor.rgb_hat_cpu_load
  - sensor.rgb_hat_cpu_temp
  - sensor.rgb_hat_ram_usage
  - sensor.rgb_hat_ups_battery
  - sensor.rgb_hat_uptime
  - fan.rgb_hat_fan                (percentuale 0-100)
  - switch.rgb_hat_auto_fan        (controllo automatico per temperatura, default ON)
  - light.rgb_hat_rgb              (on/off + effetti)
  - switch.rgb_hat_rgb_auto_cycle  (riproduce il ciclo automatico di colori originale)

NOTE: i valori di registro per gli effetti RGB (0x01-0x04) dipendono dal
firmware dell'hat: verifica/adatta i nomi in EFFECTS se il tuo hat si
comporta diversamente.
"""

import json
import logging
import os
import subprocess
import threading
import time

import paho.mqtt.client as mqtt
from smbus2 import SMBus

OLED_AVAILABLE = False

# --------------------------------------------------------------------------
# Configurazione da variabili d'ambiente (impostate da run.sh dalle opzioni
# dell'add-on)
# --------------------------------------------------------------------------
MQTT_HOST = os.environ.get("MQTT_HOST", "core-mosquitto")
MQTT_PORT = int(os.environ.get("MQTT_PORT", "1883"))
MQTT_USER = os.environ.get("MQTT_USER", "") or None
MQTT_PASSWORD = os.environ.get("MQTT_PASSWORD", "") or None
SLEEP_TIME = int(os.environ.get("SLEEP_TIME", "60"))
T_MIN_RANGE = float(os.environ.get("T_MIN_RANGE", "35"))
T_MAX_RANGE = float(os.environ.get("T_MAX_RANGE", "65"))
OLED_ENABLED = os.environ.get("OLED_ENABLED", "true").lower() == "true"

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
)
log = logging.getLogger("rgb_hat_monitor")

# --------------------------------------------------------------------------
# I2C / hat registers (stessi indirizzi dello script originale)
# --------------------------------------------------------------------------
HAT_ADDR = 0x0D
RGB_EFFECT_REG = 0x04
FAN_REG = 0x08
RGB_OFF_REG = 0x07

#bus = SMBus(1)

from smbus2 import SMBus
import os

for bus_id in (1, 20, 21):
    try:
        if os.path.exists(f"/dev/i2c-{bus_id}"):
            print(f"Uso I2C bus {bus_id}")
            bus = SMBus(bus_id)
            break
    except Exception:
        pass
else:
    raise RuntimeError("Nessun bus I2C disponibile")

i2c_lock = threading.Lock()

EFFECTS = {
    "Flash": 0x01,
    "Comet": 0x02,
    "Breathing": 0x03,
    "Rainbow": 0x04,
}
EFFECTS_REVERSE = {v: k for k, v in EFFECTS.items()}


def set_fan_speed(byte_value: int):
    with i2c_lock:
        try:
            bus.write_byte_data(HAT_ADDR, FAN_REG, byte_value & 0xFF)
        except Exception as e:
            log.error("Errore scrittura fan: %s", e)


def set_rgb_effect(byte_value: int):
    with i2c_lock:
        try:
            bus.write_byte_data(HAT_ADDR, RGB_EFFECT_REG, byte_value & 0xFF)
        except Exception as e:
            log.error("Errore scrittura effetto RGB: %s", e)


def spegni_led():
    with i2c_lock:
        try:
            bus.write_byte_data(HAT_ADDR, RGB_OFF_REG, 0x00)
        except Exception as e:
            log.error("Errore spegnimento LED: %s", e)


# --------------------------------------------------------------------------
# Lettura sensori (stessa logica dello script originale)
# --------------------------------------------------------------------------
def get_cpu_load_rate() -> int:
    def read_stat():
        with open("/proc/stat") as f:
            parts = f.readline().split()
        values = [int(x) for x in parts[1:11]]
        return values

    d1 = read_stat()
    time.sleep(1)
    d2 = read_stat()

    total1, idle1 = sum(d1), d1[3]
    total2, idle2 = sum(d2), d2[3]

    total = total2 - total1
    idle = idle2 - idle1
    if total <= 0:
        return 0
    usage = total - idle
    return int(usage * 100 / total)


def get_cpu_temp() -> float:
    try:
        out = subprocess.check_output(["/usr/bin/vcgencmd", "measure_temp"]).decode()
        # formato: temp=45.6'C
        return float(out.replace("temp=", "").replace("'C\n", "").strip())
    except Exception:
        try:
            with open("/sys/class/thermal/thermal_zone0/temp") as f:
                return round(int(f.read().strip()) / 1000, 1)
        except Exception as e:
            log.error("Errore lettura temperatura CPU: %s", e)
            return 0.0


def get_ram_usage() -> float:
    try:
        cmd = (
            "free -m | grep -i Mem | awk '{printf \"%d %d\", $3, $2}'"
        )
        out = subprocess.check_output(cmd, shell=True).decode().split()
        used, total = int(out[0]), int(out[1])
        return round(used * 100 / total, 2)
    except Exception as e:
        log.error("Errore lettura RAM: %s", e)
        return 0.0
      
def update_oled(cpu_load, cpu_temp, ram_usage):
    pass

def update_oled(cpu_load, cpu_temp, ram_usage):
    try:
        draw.rectangle((0, 0, disp.width, disp.height), outline=0, fill=0)
        draw.text((0, -2), f"CPU:{cpu_load}%", font=font, fill=255)
        draw.text((56, -2), f"Temp:{cpu_temp}C", font=font, fill=255)
        draw.text((0, 12), f"RAM:{ram_usage}%", font=font, fill=255)
        oled.image(image)
        oled.show()
    except Exception as e:
        log.error("Errore aggiornamento OLED: %s", e)

# --------------------------------------------------------------------------
# Stato condiviso
# --------------------------------------------------------------------------
state = {
    "fan_on": False,
    "fan_percentage": 0,
    "auto_fan": True,
    "rgb_on": False,
    "rgb_effect": "Breathing",
    "rgb_auto_cycle": False,
}
state_lock = threading.Lock()

# --------------------------------------------------------------------------
# MQTT setup
# --------------------------------------------------------------------------
BASE = "rgb_hat"
AVAILABILITY_TOPIC = f"{BASE}/status"

DEVICE_INFO = {
    "identifiers": ["rgb_hat_monitor"],
    "name": "RGB Hat Monitor",
    "manufacturer": "DIY",
    "model": "Raspberry Pi Fan/RGB/OLED Hat",
}

client = mqtt.Client(client_id="rgb_hat_monitor")
if MQTT_USER:
    client.username_pw_set(MQTT_USER, MQTT_PASSWORD)
client.will_set(AVAILABILITY_TOPIC, payload="offline", retain=True)


def publish_discovery():
    sensors = [
        ("cpu_load", "CPU Load", "%", None),
        ("cpu_temp", "CPU Temperature", "°C", "temperature"),
        ("ram_usage", "RAM Usage", "%", None),
    ]
    for object_id, name, unit, device_class in sensors:
        payload = {
            "name": name,
            "unique_id": f"rgb_hat_{object_id}",
            "state_topic": f"{BASE}/sensor/{object_id}/state",
            "availability_topic": AVAILABILITY_TOPIC,
            "device": DEVICE_INFO,
        }
        if unit:
            payload["unit_of_measurement"] = unit
        if device_class:
            payload["device_class"] = device_class
        client.publish(
            f"homeassistant/sensor/rgb_hat_{object_id}/config",
            json.dumps(payload),
            retain=True,
        )

    # Fan
    fan_payload = {
        "name": "RGB Hat Fan",
        "unique_id": "rgb_hat_fan",
        "availability_topic": AVAILABILITY_TOPIC,
        "command_topic": f"{BASE}/fan/set",
        "state_topic": f"{BASE}/fan/state",
        "percentage_command_topic": f"{BASE}/fan/speed/set",
        "percentage_state_topic": f"{BASE}/fan/speed/state",
        "device": DEVICE_INFO,
    }
    client.publish("homeassistant/fan/rgb_hat_fan/config", json.dumps(fan_payload), retain=True)

    # Switch: controllo automatico ventola
    auto_fan_payload = {
        "name": "RGB Hat Auto Fan Control",
        "unique_id": "rgb_hat_auto_fan",
        "availability_topic": AVAILABILITY_TOPIC,
        "command_topic": f"{BASE}/switch/auto_fan/set",
        "state_topic": f"{BASE}/switch/auto_fan/state",
        "device": DEVICE_INFO,
    }
    client.publish(
        "homeassistant/switch/rgb_hat_auto_fan/config",
        json.dumps(auto_fan_payload),
        retain=True,
    )

    # Light RGB
    light_payload = {
        "name": "RGB Hat LED",
        "unique_id": "rgb_hat_rgb",
        "availability_topic": AVAILABILITY_TOPIC,
        "command_topic": f"{BASE}/light/set",
        "state_topic": f"{BASE}/light/state",
        "effect_command_topic": f"{BASE}/light/effect/set",
        "effect_state_topic": f"{BASE}/light/effect/state",
        "effect_list": list(EFFECTS.keys()),
        "device": DEVICE_INFO,
    }
    client.publish("homeassistant/light/rgb_hat_rgb/config", json.dumps(light_payload), retain=True)

    # Switch: ciclo automatico colori (replica comportamento script originale)
    cycle_payload = {
        "name": "RGB Hat Auto Color Cycle",
        "unique_id": "rgb_hat_rgb_auto_cycle",
        "availability_topic": AVAILABILITY_TOPIC,
        "command_topic": f"{BASE}/switch/rgb_auto_cycle/set",
        "state_topic": f"{BASE}/switch/rgb_auto_cycle/state",
        "device": DEVICE_INFO,
    }
    client.publish(
        "homeassistant/switch/rgb_hat_rgb_auto_cycle/config",
        json.dumps(cycle_payload),
        retain=True,
    )


def publish_fan_state():
    with state_lock:
        on = state["fan_on"]
        pct = state["fan_percentage"]
    client.publish(f"{BASE}/fan/state", "ON" if on else "OFF", retain=True)
    client.publish(f"{BASE}/fan/speed/state", str(pct), retain=True)
    client.publish(f"{BASE}/switch/auto_fan/state", "ON" if state["auto_fan"] else "OFF", retain=True)


def publish_light_state():
    with state_lock:
        on = state["rgb_on"]
        effect = state["rgb_effect"]
        cycle = state["rgb_auto_cycle"]
    client.publish(f"{BASE}/light/state", "ON" if on else "OFF", retain=True)
    client.publish(f"{BASE}/light/effect/state", effect, retain=True)
    client.publish(f"{BASE}/switch/rgb_auto_cycle/state", "ON" if cycle else "OFF", retain=True)


def apply_fan(on: bool, percentage: int):
    byte_value = round(percentage * 255 / 100) if on else 0x00
    set_fan_speed(byte_value)
    with state_lock:
        state["fan_on"] = on
        state["fan_percentage"] = percentage if on else 0
    publish_fan_state()


def apply_light(on: bool, effect_name: str):
    if on:
        set_rgb_effect(EFFECTS.get(effect_name, EFFECTS["Breathing"]))
    else:
        spegni_led()
    with state_lock:
        state["rgb_on"] = on
        if on:
            state["rgb_effect"] = effect_name
    publish_light_state()


def on_connect(c, userdata, flags, rc):
    log.info("Connesso a MQTT (rc=%s)", rc)
    c.publish(AVAILABILITY_TOPIC, "online", retain=True)
    publish_discovery()
    c.subscribe(f"{BASE}/fan/set")
    c.subscribe(f"{BASE}/fan/speed/set")
    c.subscribe(f"{BASE}/switch/auto_fan/set")
    c.subscribe(f"{BASE}/light/set")
    c.subscribe(f"{BASE}/light/effect/set")
    c.subscribe(f"{BASE}/switch/rgb_auto_cycle/set")
    publish_fan_state()
    publish_light_state()


def on_message(c, userdata, msg):
    topic = msg.topic
    payload = msg.payload.decode().strip()
    log.info("MQTT msg: %s -> %s", topic, payload)

    if topic == f"{BASE}/fan/set":
        with state_lock:
            pct = state["fan_percentage"] or 50
        apply_fan(payload.upper() == "ON", pct)

    elif topic == f"{BASE}/fan/speed/set":
        try:
            pct = max(0, min(100, int(payload)))
        except ValueError:
            return
        apply_fan(pct > 0, pct)

    elif topic == f"{BASE}/switch/auto_fan/set":
        with state_lock:
            state["auto_fan"] = payload.upper() == "ON"
        publish_fan_state()

    elif topic == f"{BASE}/light/set":
        with state_lock:
            effect = state["rgb_effect"]
        apply_light(payload.upper() == "ON", effect)

    elif topic == f"{BASE}/light/effect/set":
        if payload in EFFECTS:
            apply_light(True, payload)

    elif topic == f"{BASE}/switch/rgb_auto_cycle/set":
        with state_lock:
            state["rgb_auto_cycle"] = payload.upper() == "ON"
        publish_light_state()


client.on_connect = on_connect
client.on_message = on_message


# --------------------------------------------------------------------------
# Loop principale: sensori, sicurezza termica, ciclo colori automatico
# --------------------------------------------------------------------------
def main_loop():
    cycle_sequence = ["Rainbow", "Comet", "Flash", "Breathing"]
    cycle_index = 0

    while True:
        cpu_load = get_cpu_load_rate()
        cpu_temp = get_cpu_temp()
        ram_usage = get_ram_usage()

        client.publish(f"{BASE}/sensor/cpu_load/state", cpu_load)
        client.publish(f"{BASE}/sensor/cpu_temp/state", cpu_temp)
        client.publish(f"{BASE}/sensor/ram_usage/state", ram_usage)
        update_oled(cpu_load, cpu_temp, ram_usage)

        # Sicurezza termica: se auto_fan e' attivo, gestisce la ventola
        # in base alle soglie configurate (indipendentemente dal comando manuale).
        # Se auto_fan e' spento, la ventola resta sotto controllo manuale, ma
        # sopra la soglia massima viene comunque forzata al 100% per sicurezza.
        with state_lock:
            auto_fan = state["auto_fan"]
        if auto_fan:
            if cpu_temp >= T_MAX_RANGE:
                apply_fan(True, 100)
            elif cpu_temp <= T_MIN_RANGE:
                apply_fan(False, 0)
        else:
            if cpu_temp >= T_MAX_RANGE:
                with state_lock:
                    already_full = state["fan_on"] and state["fan_percentage"] == 100
                if not already_full:
                    apply_fan(True, 100)

        # Ciclo colori automatico (replica lo script originale): mentre la
        # ventola gira, cambia effetto RGB periodicamente.
        with state_lock:
            do_cycle = state["rgb_auto_cycle"] and state["fan_on"]
        if do_cycle:
            effect = cycle_sequence[cycle_index % len(cycle_sequence)]
            cycle_index += 1
            apply_light(True, effect)

        logging.info(
            "CPU:%s%% Temp:%.1fC RAM:%s%% FanOn:%s FanPct:%s RGB:%s",
            cpu_load, cpu_temp, ram_usage,
            state["fan_on"], state["fan_percentage"], state["rgb_effect"],
        )

        time.sleep(max(0, SLEEP_TIME - 1))  # -1 perche' get_cpu_load_rate dorme gia' 1s


def main():
    log.info("Avvio RGB Hat Monitor -> MQTT (%s:%s)", MQTT_HOST, MQTT_PORT)
    client.connect(MQTT_HOST, MQTT_PORT, keepalive=60)
    client.loop_start()

    # Stato iniziale sicuro: fan spenta, led spento, auto_fan attivo
    set_fan_speed(0x00)
    spegni_led()

    try:
        main_loop()
    except KeyboardInterrupt:
        pass
    finally:
        client.publish(AVAILABILITY_TOPIC, "offline", retain=True)
        client.loop_stop()
        client.disconnect()


if __name__ == "__main__":
    main()
