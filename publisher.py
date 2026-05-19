import serial
import paho.mqtt.client as mqtt
import time
import json

# Configurazione seriale
SERIAL_PORT = '/dev/ttyACM0'  # Su Linux, oppure 'COM3' su Windows
BAUD_RATE = 9600

# Configurazione MQTT
MQTT_BROKER = '10.0.20.192'  # Host IP
MQTT_PORT = 1883
MQTT_TOPIC = 'pwairport/sensors/light'

# Inizializza connessione seriale
ser = serial.Serial(SERIAL_PORT, BAUD_RATE, timeout=1)
time.sleep(2)  # Aspetta che Arduino si resetti

# Inizializza client MQTT
client = mqtt.Client()
client.connect(MQTT_BROKER, MQTT_PORT, 60)

print("Parser avviato. In attesa di dati da Arduino...")

try:
    while True:
        if ser.in_waiting > 0:
            line = ser.readline().decode('utf-8').strip()
            print(f"Ricevuto: {line}")
            
            # Parse della stringa: "LIGHT:350,LED:ON"
            if line.startswith("LIGHT:"):
                try:
                    parts = line.split(',')
                    light_value = int(parts[0].split(':')[1])
                    led_state = parts[1].split(':')[1]
                    
                    # Crea payload JSON
                    payload = {
                        'value': light_value                    
                    }
                    
                    # Pubblica su MQTT
                    client.publish(MQTT_TOPIC, json.dumps(payload))
                    print(f"Pubblicato su MQTT: {payload}")
                    
                except Exception as e:
                    print(f"Errore nel parsing: {e}")
        
        time.sleep(0.1)

except KeyboardInterrupt:
    print("\nChiusura programma...")
    ser.close()
    client.disconnect()