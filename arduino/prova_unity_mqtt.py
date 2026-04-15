import paho.mqtt.client as mqtt
import json
from datetime import datetime
from flask import Flask, jsonify
import threading

print("Inizializzazione parser MQTT→HTTP...")

# Configurazione MQTT
MQTT_BROKER = 'localhost'
MQTT_PORT = 1883
MQTT_TOPIC = 'arduino/sensors'

# Dati correnti
current_data = {
    'light_value': 0,
    'led_state': 'OFF',
    'datetime': ''
}

# Flask app
app = Flask(__name__)

@app.route('/sensor')
def get_sensor_data():
    return jsonify(current_data)

# Callback MQTT
def on_connect(client, userdata, flags, rc, properties=None):
    print(f"Connesso al broker MQTT con codice: {rc}")
    client.subscribe(MQTT_TOPIC)
    print(f"Iscritto al topic: {MQTT_TOPIC}")

def on_message(client, userdata, msg):
    global current_data
    try:
        payload = json.loads(msg.payload.decode())
        current_data = payload
        current_data['datetime'] = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        print(f"Dati aggiornati: {current_data}")
    except Exception as e:
        print(f"Errore: {e}")

# Thread MQTT
def mqtt_thread():
    client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2)
    client.on_connect = on_connect
    client.on_message = on_message
    client.connect(MQTT_BROKER, MQTT_PORT, 60)
    client.loop_forever()

if __name__ == '__main__':
    # Avvia MQTT in un thread separato
    threading.Thread(target=mqtt_thread, daemon=True).start()
    
    # Avvia server HTTP
    print("Server HTTP avviato su http://0.0.0.0:5000/sensor")
    app.run(host='0.0.0.0', port=5000)