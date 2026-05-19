const int ledPins[] = {8, 9, 10, 11, 12, 13};
const int ledCount = 6;

void setup() {
  Serial.begin(9600);

  for (int i = 0; i < ledCount; i++) {
    pinMode(ledPins[i], OUTPUT);
    digitalWrite(ledPins[i], LOW);
  }
}

void loop() {
  if (Serial.available() > 0) {
    String comando = Serial.readStringUntil('\n');
    comando.trim();

    if (comando == "LANDING") {
      landingSequence();
    } 
    else if (comando == "TAKEOFF") {
      takeoffSequence();
    }
  }
}

void landingSequence() {
  spegniTutti();

  // dal verde al rosso
  for (int j = 0; j < 3; j++) {
    for (int i = 0; i < ledCount; i++) {
      digitalWrite(ledPins[i], HIGH);
      delay(500);
    }
    delay(500);
    spegniTutti();
  }
}

void takeoffSequence() {
  spegniTutti();

  // dal rosso al verde
  for (int j = 0; j < 3; j++) {
    for (int i = ledCount - 1; i >= 0; i--) {
      digitalWrite(ledPins[i], HIGH);
      delay(500);
    }
    delay(500);
    spegniTutti();
  }
}

void spegniTutti() {
  for (int i = 0; i < ledCount; i++) {
    digitalWrite(ledPins[i], LOW);
  }
}
