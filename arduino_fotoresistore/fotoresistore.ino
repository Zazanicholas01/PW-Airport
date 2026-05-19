int analogInPin = A0;
int lightValue = 0;
int led = 11;

void setup() {
  Serial.begin(9600);
  pinMode(analogInPin, INPUT);
  pinMode(led, OUTPUT);
}
 
void loop() {
  lightValue = analogRead(analogInPin);  
  
  bool ledState;
  if (lightValue > 400) {
    digitalWrite(led, LOW);
    ledState = false;
  }
  else {
    digitalWrite(led, HIGH);
    ledState = true;
  }
  
  // Invia stringa formattata per il parser
  Serial.print("LIGHT:");
  Serial.print(lightValue);
  Serial.print(",LED:");
  Serial.println(ledState ? "ON" : "OFF");
  
  delay(1000);
}
