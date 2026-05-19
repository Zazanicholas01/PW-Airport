const int analogInPin = A0;
const int photoLedPin = 7;

int lightValue = 0;
bool photoLedState = false;

const int ledPins[] = {8, 9, 10, 11, 12, 13};
const int ledCount = 6;

unsigned long lastLightRead = 0;
const unsigned long lightReadInterval = 1000;

enum SequenceType {
  NONE,
  LANDING,
  TAKEOFF
};

SequenceType currentSequence = NONE;

int currentLedIndex = 0;
int currentCycle = 0;
bool pauseAfterCycle = false;

unsigned long lastLedStep = 0;
const unsigned long ledStepInterval = 500;

void setup() {
  Serial.begin(9600);

  pinMode(analogInPin, INPUT);
  pinMode(photoLedPin, OUTPUT);

  for (int i = 0; i < ledCount; i++) {
    pinMode(ledPins[i], OUTPUT);
    digitalWrite(ledPins[i], LOW);
  }

  digitalWrite(photoLedPin, LOW);
}

void loop() {
  leggiFotoresistore();
  leggiComandoSeriale();
  aggiornaSequenzaLed();
}

void leggiFotoresistore() {
  unsigned long now = millis();

  if (now - lastLightRead >= lightReadInterval) {
    lastLightRead = now;

    lightValue = analogRead(analogInPin);

    if (lightValue > 400) {
      digitalWrite(photoLedPin, LOW);
      photoLedState = false;
    } else {
      digitalWrite(photoLedPin, HIGH);
      photoLedState = true;
    }

    Serial.print("LIGHT:");
    Serial.print(lightValue);
    Serial.print(",LED:");
    Serial.println(photoLedState ? "ON" : "OFF");
  }
}

void leggiComandoSeriale() {
  if (Serial.available() > 0) {
    String comando = Serial.readStringUntil('\n');
    comando.trim();

    if (comando == "LANDING") {
      avviaLanding();
    } 
    else if (comando == "TAKEOFF") {
      avviaTakeoff();
    }
  }
}

void avviaLanding() {
  spegniTutti();

  currentSequence = LANDING;
  currentLedIndex = 0;
  currentCycle = 0;
  pauseAfterCycle = false;
  lastLedStep = millis();
}

void avviaTakeoff() {
  spegniTutti();

  currentSequence = TAKEOFF;
  currentLedIndex = ledCount - 1;
  currentCycle = 0;
  pauseAfterCycle = false;
  lastLedStep = millis();
}

void aggiornaSequenzaLed() {
  if (currentSequence == NONE) {
    return;
  }

  unsigned long now = millis();

  if (now - lastLedStep < ledStepInterval) {
    return;
  }

  lastLedStep = now;

  if (pauseAfterCycle) {
    spegniTutti();
    pauseAfterCycle = false;
    currentCycle++;

    if (currentCycle >= 3) {
      currentSequence = NONE;
      return;
    }

    if (currentSequence == LANDING) {
      currentLedIndex = 0;
    } else if (currentSequence == TAKEOFF) {
      currentLedIndex = ledCount - 1;
    }

    return;
  }

  digitalWrite(ledPins[currentLedIndex], HIGH);

  if (currentSequence == LANDING) {
    currentLedIndex++;

    if (currentLedIndex >= ledCount) {
      pauseAfterCycle = true;
    }
  } 
  else if (currentSequence == TAKEOFF) {
    currentLedIndex--;

    if (currentLedIndex < 0) {
      pauseAfterCycle = true;
    }
  }
}

void spegniTutti() {
  for (int i = 0; i < ledCount; i++) {
    digitalWrite(ledPins[i], LOW);
  }
}