import json
import time
import serial
import paho.mqtt.client as mqtt

SERIAL_PORT = "/dev/ttyACM0"   # oppure /dev/ttyUSB0
BAUD_RATE = 9600

MQTT_BROKER = "10.0.20.192"
MQTT_PORT = 1883
MQTT_TOPIC = "pwairport/sensors/led"

arduino = serial.Serial(SERIAL_PORT, BAUD_RATE, timeout=1)
time.sleep(2)

def on_connect(client, userdata, flags, rc):
    print("Connesso MQTT")
    client.subscribe(MQTT_TOPIC)

def on_message(client, userdata, msg):
    try:
        payload = msg.payload.decode()
        data = json.loads(payload)

        status = data.get("status")

        print("Ricevuto:", status)

        if status == "landing":
            arduino.write(b"LANDING\n")

        elif status == "takeoff":
            arduino.write(b"TAKEOFF\n")

    except Exception as e:
        print("Errore:", e)

client = mqtt.Client()
client.on_connect = on_connect
client.on_message = on_message

client.connect(MQTT_BROKER, MQTT_PORT, 60)
client.loop_forever()