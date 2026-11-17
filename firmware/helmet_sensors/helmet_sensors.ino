/*
 * Intelligent Helmet - sensor acquisition and LoRaWAN uplink
 * Board: Arduino MKR WAN 1310
 *
 * Sensors:
 *   - LSM6DS3 IMU (I2C, address 0x6A)  -> fall detection
 *   - LTR390 light sensor (I2C)        -> avalanche (burial) detection
 *   - u-blox NEO-6M GNSS (Serial1)     -> position and speed
 *
 * Uplink frame (18 bytes), see docs/payload-format.md:
 *   [0]      message type (0x01 periodic, 0x02 fall, 0x03 avalanche)
 *   [1..4]   latitude  at T      (int32, degrees * 1e6, big-endian)
 *   [5..8]   longitude at T      (int32, degrees * 1e6, big-endian)
 *   [9..12]  delta lat/lon T -> T-6s   (int16 each)
 *   [13..16] delta lat/lon T-6s -> T-12s (int16 each)
 *   [17]     speed (uint8, km/h)
 */

#include <MKRWAN.h>
#include <TinyGPSPlus.h>
#include <Adafruit_LTR390.h>
#include <LSM6DS3.h>
#include <Wire.h>

#include "arduino_secrets.h"  // copy arduino_secrets.example.h and fill in your TTN keys

// ==========================================================
// LORAWAN KEYS (TTN, OTAA)
// ==========================================================

const char *appEui = SECRET_APP_EUI;
const char *appKey = SECRET_APP_KEY;

// --- HARDWARE ---

LoRaModem modem;
LSM6DS3 imu(I2C_MODE, 0x6A);
TinyGPSPlus gps;
Adafruit_LTR390 ltr = Adafruit_LTR390();

// --- GPS HISTORY (positions at T, T-6s, T-12s) ---

struct Coordinates {
  int32_t latScaled;
  int32_t lonScaled;
};

// Default position used until the first valid GPS fix (INSA Lyon, La Doua campus)
Coordinates gpsHistory[3] = {
  {45783100, 4877400},
  {45783100, 4877400},
  {45783100, 4877400}
};

// --- DETECTION STATE ---

bool fallDetected = false;
bool avalancheDetected = false;
// Future work: head impact detection with a FlexiForce pressure sensor (not implemented)
bool headImpactDetected = false;

const float    FALL_THRESHOLD_G   = 3.0;    // acceleration norm threshold (g)
const uint32_t LIGHT_THRESHOLD    = 200;    // ambient light threshold (ALS counts)
const unsigned long AVALANCHE_DURATION = 15000;  // darkness duration before alert (ms)
unsigned long darknessStart = 0;
bool inDarkness = false;

// --- TIMERS ---

unsigned long lastLoRaSend = 0;
const unsigned long PERIODIC_INTERVAL = 18000;   // periodic uplink every 18 s (3 x 6 s snapshots)

unsigned long lastSensorCheck = 0;
const unsigned long SENSOR_INTERVAL = 100;       // IMU and light sensor polling (ms)

unsigned long lastGpsSnapshot = 0;
const unsigned long GPS_SNAPSHOT_INTERVAL = 6000; // GPS position stored every 6 s

void setup() {
  Serial.begin(115200);
  Serial1.begin(9600);  // NEO-6M: GPS TX -> pin 13 (RX1), GPS RX -> pin 14 (TX1)

  if (!modem.begin(EU868)) {
    Serial.println("Error: LoRa module not reachable");
    while (1);
  }

  Serial.print("Device EUI: ");
  Serial.println(modem.deviceEUI());

  Serial.println("Joining TTN...");
  while (!modem.joinOTAA(appEui, appKey)) {
    Serial.println("Join failed. Retrying in 15 s...");
    delay(15000);
  }
  Serial.println("--> Joined TTN");

  if (imu.begin() != 0) Serial.println("Error: IMU not detected");
  if (!ltr.begin())     Serial.println("Error: LTR390 not found");
  else                  ltr.setMode(LTR390_MODE_ALS);
}

void loop() {
  // Feed the NMEA parser continuously
  while (Serial1.available() > 0) {
    gps.encode(Serial1.read());
  }

  unsigned long now = millis();

  // 1. GPS snapshot every 6 s
  if (now - lastGpsSnapshot >= GPS_SNAPSHOT_INTERVAL) {
    lastGpsSnapshot = now;
    if (gps.location.isValid()) {
      gpsHistory[2] = gpsHistory[1];
      gpsHistory[1] = gpsHistory[0];
      gpsHistory[0].latScaled = gps.location.lat() * 1000000;
      gpsHistory[0].lonScaled = gps.location.lng() * 1000000;
      Serial.println("GPS snapshot updated.");
    }
  }

  // 2. Sensor polling every 100 ms
  if (now - lastSensorCheck >= SENSOR_INTERVAL) {
    lastSensorCheck = now;

    // A. IMU: fall detection on acceleration norm
    float ax = imu.readFloatAccelX();
    float ay = imu.readFloatAccelY();
    float az = imu.readFloatAccelZ();
    float norm = sqrt(ax * ax + ay * ay + az * az);

    if (norm > FALL_THRESHOLD_G) {
      fallDetected = true;
    }

    // B. Light sensor: avalanche detection on prolonged darkness
    uint32_t light = ltr.readALS();
    if (light < LIGHT_THRESHOLD) {
      if (!inDarkness) {
        inDarkness = true;
        darknessStart = now;
      } else if (now - darknessStart >= AVALANCHE_DURATION) {
        avalancheDetected = true;
        darknessStart = now;
      }
    } else {
      inDarkness = false;
      avalancheDetected = false;
    }
  }

  // ==========================================================
  // UPLINK PRIORITIES: fall > avalanche > periodic
  // ==========================================================

  if (fallDetected) {
    Serial.println("!!! ALERT 02: FALL (IMU) !!!");
    updateHistory();
    sendHistoryPacket(0x02);
    fallDetected = false;
    lastLoRaSend = now;
  }
  else if (avalancheDetected) {
    Serial.println("!!! ALERT 03: AVALANCHE (prolonged darkness) !!!");
    updateHistory();
    sendHistoryPacket(0x03);
    avalancheDetected = false;
    lastLoRaSend = now;
  }
  else if (now - lastLoRaSend >= PERIODIC_INTERVAL) {
    lastLoRaSend = now;
    Serial.println("Periodic uplink (01)...");
    sendHistoryPacket(0x01);
  }
}

// Shift the history and store the current position (used for alerts)
void updateHistory() {
  gpsHistory[2] = gpsHistory[1];
  gpsHistory[1] = gpsHistory[0];

  if (gps.location.isValid()) {
    gpsHistory[0].latScaled = gps.location.lat() * 1000000;
    gpsHistory[0].lonScaled = gps.location.lng() * 1000000;
  } else {
    gpsHistory[0] = gpsHistory[1];
    Serial.println("[Warn] Invalid GPS fix. Reusing previous position.");
  }
}

void sendHistoryPacket(uint8_t type) {
  uint8_t payload[18];

  payload[0] = type;

  // 1. Current position T (8 bytes)
  int32_t lat0 = gpsHistory[0].latScaled;
  int32_t lon0 = gpsHistory[0].lonScaled;

  payload[1] = (lat0 >> 24) & 0xFF;
  payload[2] = (lat0 >> 16) & 0xFF;
  payload[3] = (lat0 >> 8) & 0xFF;
  payload[4] = lat0 & 0xFF;

  payload[5] = (lon0 >> 24) & 0xFF;
  payload[6] = (lon0 >> 16) & 0xFF;
  payload[7] = (lon0 >> 8) & 0xFF;
  payload[8] = lon0 & 0xFF;

  // 2. Delta T -> T-6s (4 bytes)
  int16_t deltaLat1 = (int16_t)(lat0 - gpsHistory[1].latScaled);
  int16_t deltaLon1 = (int16_t)(lon0 - gpsHistory[1].lonScaled);

  payload[9]  = (deltaLat1 >> 8) & 0xFF;
  payload[10] = deltaLat1 & 0xFF;
  payload[11] = (deltaLon1 >> 8) & 0xFF;
  payload[12] = deltaLon1 & 0xFF;

  // 3. Delta T-6s -> T-12s (4 bytes)
  int16_t deltaLat2 = (int16_t)(gpsHistory[1].latScaled - gpsHistory[2].latScaled);
  int16_t deltaLon2 = (int16_t)(gpsHistory[1].lonScaled - gpsHistory[2].lonScaled);

  payload[13] = (deltaLat2 >> 8) & 0xFF;
  payload[14] = deltaLat2 & 0xFF;
  payload[15] = (deltaLon2 >> 8) & 0xFF;
  payload[16] = deltaLon2 & 0xFF;

  // 4. Current speed (1 byte), 0 when no valid fix
  uint8_t speedKmh = 0;
  if (gps.speed.isValid()) {
    speedKmh = (uint8_t)gps.speed.kmph();
  }
  payload[17] = speedKmh;

  // Unconfirmed uplink
  modem.beginPacket();
  modem.write(payload, sizeof(payload));
  int err = modem.endPacket(false);

  if (err > 0) {
    Serial.println("--> Packet sent");
  } else {
    Serial.println("--> LoRa send error");
  }
}
