# RGB Hat Monitor — Add-on Home Assistant (HAOS)

Converte lo script originale (OLED + fan + RGB su hat I2C) in un add-on
HAOS che parla con Home Assistant via **MQTT Discovery**: niente
integrazione custom da mantenere, tutte le entità appaiono in automatico.

## Prerequisiti

1. **Add-on Mosquitto broker** installato e avviato in HAOS
   (Impostazioni → Add-on → Store → cerca "Mosquitto broker").
2. **Integrazione MQTT** configurata in Home Assistant
   (di solito si auto-configura appena installi Mosquitto; se no:
   Impostazioni → Dispositivi e servizi → Aggiungi integrazione → MQTT →
   host `core-mosquitto`).
3. Il tuo utente NUT (`upsc`) deve essere raggiungibile dal container se vuoi
   la percentuale UPS: se il tuo UPS non è gestito da NUT sullo stesso host,
   lascia perdere quel sensore (non genera errori, resta assente).

## Installazione dell'add-on

1. Copia l'intera cartella `rgb_hat_monitor/` dentro
   `/addons/rgb_hat_monitor/` sul tuo Home Assistant (via Samba, SSH o
   l'add-on "Studio Code Server").
   - Se usi la repository locale: Impostazioni → Add-on → Store → menu
     in alto a destra → "Repository" → aggiungi `/addons` come repository
     locale (di solito è già lì di default in HAOS).
2. Impostazioni → Add-on → Store → in fondo troverai "RGB Hat Monitor"
   sotto "Local add-ons" (o Add-on locali). Aprilo e clicca **Installa**
   (la build la prima volta impiega qualche minuto sul Pi).
3. Vai nella scheda **Configurazione** dell'add-on e imposta:
   - `mqtt_host`: di solito `core-mosquitto`
   - `mqtt_user` / `mqtt_password`: le credenziali dell'utente MQTT
     (Impostazioni → Persone → aggiungi un utente dedicato tipo `mqtt_hat`)
   - `sleep_time`, `t_min_range`, `t_max_range`: come nello script originale
   - `ups_name`: nome del dispositivo NUT (default `tecnoware`)
   - `oled_enabled`: `true`/`false`
4. Avvia l'add-on e abilita "Avvia all'avvio" + "Watchdog".
5. Guarda i log dell'add-on: dovresti vedere "Connesso a MQTT" e i valori
   pubblicati ogni `sleep_time` secondi.

Entro pochi secondi, in **Impostazioni → Dispositivi e servizi → MQTT**
comparirà il dispositivo "RGB Hat Monitor" con tutte le entità.

## Entità create

| Entità | Tipo | Note |
|---|---|---|
| `sensor.rgb_hat_cpu_load` | sensore | % CPU |
| `sensor.rgb_hat_cpu_temp` | sensore | °C, device_class temperature |
| `sensor.rgb_hat_ram_usage` | sensore | % RAM |
| `sensor.rgb_hat_ups_battery` | sensore | % batteria UPS (se NUT disponibile) |
| `sensor.rgb_hat_uptime` | sensore | testo, es. "up 3 days" |
| `fan.rgb_hat_fan` | fan | ON/OFF + percentuale (0–100) |
| `switch.rgb_hat_auto_fan` | switch | se ON, la ventola è gestita in automatico dalle soglie `t_min_range`/`t_max_range` (comportamento originale) |
| `light.rgb_hat_rgb` | light | ON/OFF + effetto (`Flash`, `Comet`, `Breathing`, `Rainbow`) |
| `switch.rgb_hat_rgb_auto_cycle` | switch | se ON, mentre la ventola gira il colore cambia ciclicamente ogni `sleep_time`, come nello script originale |

> ⚠️ I nomi degli effetti (`Flash`/`Comet`/`Breathing`/`Rainbow`) sono
> etichette scelte da me sui valori di registro `0x01`-`0x04`: verifica
> col tuo hat quale valore corrisponde a quale effetto reale e rinomina
> il dizionario `EFFECTS` in `monitor.py` se serve.

## Sicurezza termica

Anche a switch `auto_fan` spento (controllo manuale), se la temperatura
raggiunge `t_max_range` la ventola viene comunque forzata al 100% per
sicurezza: non puoi disattivare del tutto la protezione termica.

## File del pacchetto

```
rgb_hat_monitor/
├── config.yaml      # manifest add-on (opzioni, device I2C, architetture)
├── build.yaml        # immagine base per la build multi-arch
├── Dockerfile
├── requirements.txt
├── run.sh             # legge le opzioni e lancia monitor.py
├── monitor.py         # logica sensori + I2C + MQTT
└── README.md
```
