import paho.mqtt.client as mqtt
import json
import sqlite3
from datetime import datetime

# Configurazione MQTT
MQTT_BROKER = 'localhost'
MQTT_PORT = 1883
MQTT_TOPIC = 'arduino/sensors'

# Configurazione Database
DB_NAME = 'sensor_data.db'

# Inizializza database
def init_db():
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS sensor_readings (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            light_value INTEGER,
            led_state TEXT,
            recorded_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    conn.commit()
    conn.close()

# Callback quando si connette al broker
def on_connect(client, userdata, flags, rc):
    print(f"Connesso al broker MQTT con codice: {rc}")
    client.subscribe(MQTT_TOPIC)
    print(f"Iscritto al topic: {MQTT_TOPIC}")

# Callback quando arriva un messaggio
def on_message(client, userdata, msg):
    try:
        payload = json.loads(msg.payload.decode())
        print(f"Messaggio ricevuto: {payload}")
        
        # Salva nel database
        conn = sqlite3.connect(DB_NAME)
        cursor = conn.cursor()
        cursor.execute('''
            INSERT INTO sensor_readings (light_value, led_state)
            VALUES (?, ?)
        ''', (payload['light_value'], payload['led_state']))
        conn.commit()
        conn.close()
        
        print("Dati salvati nel database")
        
    except Exception as e:
        print(f"Errore: {e}")

# Inizializza database
# Inizializza database
init_db()
print("Database inizializzato")

# Inizializza client MQTT
client = mqtt.Client()
client.on_connect = on_connect
client.on_message = on_message

print(f"Connessione al broker {MQTT_BROKER}:{MQTT_PORT}...")
client.connect(MQTT_BROKER, MQTT_PORT, 60)

print("Parser MQTT→DB avviato...")
client.loop_forever()