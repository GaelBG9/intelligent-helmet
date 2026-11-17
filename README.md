# Intelligent Helmet

An IoT safety helmet prototype for outdoor sports such as cycling, skiing and mountaineering. The helmet detects falls and avalanche burial, sends its GPS position over LoRaWAN, and feeds a real-time monitoring dashboard. The dashboard shows the user's medical record and the local emergency contact, sends WhatsApp alerts and produces a PDF report at the end of each session.

Built as a second-year P2I project in the FIMI program at INSA Lyon.

## How it works

```
+---------------------------+      LoRaWAN       +----------------------+
|  Helmet                   |   (EU868, OTAA)    |  The Things Network  |
|  Arduino MKR WAN 1310     | -----------------> |  payload formatter   |
|  LSM6DS3 IMU              |   18-byte frame    |  (payload_decoder.js)|
|  LTR390 light sensor      |                    +----------+-----------+
|  u-blox NEO-6M GNSS       |                               | MQTT (decoded JSON)
+---------------------------+                               v
                                                +----------------------+
                                                |  Python bridge       |
                                                |  ttn_to_mariadb_     |
                                                |  bridge.py           |
                                                +----------+-----------+
                                                           | SQL
                                                           v
+---------------------------+                   +----------------------+
|  Streamlit dashboard      | <---------------- |  MariaDB             |
|  map, speed, alerts, PDF  |       SQL         |  Projet_casque       |
|  WhatsApp (Twilio)        |                   +----------------------+
+---------------------------+
```

1. **Detection on the helmet.** The firmware samples the IMU and the light sensor every 100 ms.
   - **Fall:** an acceleration norm above 3 g triggers a fall alert.
   - **Avalanche:** ambient light below the threshold for 15 consecutive seconds is treated as burial under snow and triggers an avalanche alert.
   - **Position:** a GPS snapshot is stored every 6 s, and the last three positions (T, T-6 s, T-12 s) are kept.
2. **Transmission.** A compact 18-byte frame is sent every 18 s, or immediately when an alert is raised. Alerts take priority over periodic frames. The two older positions are sent as 16-bit deltas to save airtime. See [docs/payload-format.md](docs/payload-format.md).
3. **Decoding.** The TTN payload formatter turns the frame into JSON.
4. **Storage.** The Python bridge subscribes to the TTN MQTT broker and finds the active session of the helmet. It stores the three trajectory points and, for alert frames, an alert record.
5. **Monitoring.** The operator starts and closes sessions from the Streamlit dashboard, which refreshes every 20 s. The dashboard shows:
   - the live position on a map,
   - current and maximum speed,
   - the number of frames received,
   - the user's medical record (blood type, allergies),
   - the emergency services for the activity area.

   When an alert arrives, a single WhatsApp message is sent through Twilio. Closing a session generates a PDF report with the trajectory and speed plots.

## Repository structure

```
intelligent-helmet/
├── firmware/
│   ├── helmet_sensors/
│   │   ├── helmet_sensors.ino            Sensor acquisition, detection and LoRaWAN uplink
│   │   └── arduino_secrets.example.h     Template for the TTN keys
│   └── battery_charger/
│       └── battery_charger.ino           LiPo charger configuration (PMIC)
├── ttn/
│   └── payload_decoder.js                TTN uplink payload formatter
├── backend/
│   ├── ttn_client.py                     TTN MQTT client
│   └── ttn_to_mariadb_bridge.py          Stores decoded uplinks in MariaDB
├── dashboard/
│   └── app.py                            Streamlit control station
├── database/
│   ├── schema.sql                        MariaDB schema
│   └── sample_data.sql                   Example data for a first run
├── docs/
│   └── payload-format.md                 Frame layout and timing
├── .env.example                          Configuration template for the Python side
└── requirements.txt
```

## Hardware

| Component                 | Role                         | Connection                          |
|---------------------------|------------------------------|-------------------------------------|
| Arduino MKR WAN 1310      | MCU and LoRa radio (EU868)   |                                     |
| LSM6DS3 IMU               | Fall detection               | I2C, address 0x6A                   |
| Adafruit LTR390           | Ambient light (avalanche)    | I2C                                 |
| u-blox NEO-6M GNSS        | Position and speed           | UART, NMEA 0183, 9600 bps, 3.3 V    |
| Single-cell LiPo battery  | Power supply                 | MKR WAN 1310 battery connector      |

NEO-6M wiring on the MKR WAN 1310:

| NEO-6M | MKR WAN 1310          |
|--------|-----------------------|
| TX     | Pin 13 (RX1, Serial1) |
| RX     | Pin 14 (TX1, Serial1) |
| VCC    | 3.3 V                 |
| GND    | GND                   |

## Database

The `Projet_casque` database has seven tables:

| Table            | Content                                                         |
|------------------|-----------------------------------------------------------------|
| `utilisateur`    | User identity and medical record (blood type, allergies, emergency contact) |
| `casque`         | Helmet ID (equal to the TTN device ID) and its sensors          |
| `contactsecours` | Emergency service contacts                                      |
| `lieux`          | Activity areas, sport type and associated emergency service     |
| `sessions`       | Sessions linking a user, a helmet and an area; `DateFin IS NULL` means active |
| `infotrajet`     | Time-stamped GPS points and speed                               |
| `alerte`         | Fall and avalanche alerts with their position                   |

## Setup

### 1. Database

Install MariaDB, then create the schema and, optionally, the example data:

```bash
mysql -u root -p < database/schema.sql
mysql -u root -p < database/sample_data.sql
```

### 2. The Things Network

1. Create an application and register the MKR WAN 1310 as an end device (OTAA, EU868). The firmware prints the Device EUI on the serial monitor at startup.
2. In **Payload formatters > Uplink**, choose **Custom Javascript formatter** and paste the content of `ttn/payload_decoder.js`.
3. In **Integrations > MQTT**, generate an API key for the Python bridge.

### 3. Firmware

1. Install the Arduino IDE and the **Arduino SAMD Boards** core.
2. Install the libraries `MKRWAN`, `TinyGPSPlus`, `Adafruit LTR390`, `Seeed Arduino LSM6DS3` and `Arduino_PMIC`.
3. Copy `firmware/helmet_sensors/arduino_secrets.example.h` to `arduino_secrets.h` in the same folder and fill in the JoinEUI (AppEUI) and AppKey from TTN.
4. Upload `firmware/helmet_sensors/helmet_sensors.ino`.

`firmware/battery_charger/battery_charger.ino` is a separate sketch. It configures the on-board charger for a LiPo battery (4.2 V, 150 mA) and reports the charging state.

### 4. Python bridge and dashboard

Python 3.10 or later is recommended.

```bash
python -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env             # then edit .env
```

Run the bridge and the dashboard in two terminals from the repository root:

```bash
python backend/ttn_to_mariadb_bridge.py
streamlit run dashboard/app.py
```

The Twilio variables are optional. WhatsApp notifications are disabled when they are left empty.

## Usage

1. Power on the helmet and wait for the "Joined TTN" message on the serial monitor.
2. In the dashboard sidebar, select the user ID, the helmet ID and the activity area, then click **DÉMARRER LE TRAJET**.
3. Frames received while the session is active appear on the map and the speed chart. An alert banner is shown when a fall or avalanche frame arrives.
4. Click **CLÔTURER LA SESSION** to close the session and download the PDF report.

The dashboard interface and the database column names are in French, as the project was built at INSA Lyon.

## Limitations

- The fall and avalanche thresholds (3 g, light level, 15 s) were set empirically on the prototype and have not been validated in real conditions.
- An 18-byte frame every 18 s is fine for demonstration, but it exceeds the TTN fair use policy (30 s of uplink airtime per day) during long sessions. A longer periodic interval, or alert-only transmission, would be needed for regular use.
- Until the GPS gets its first valid fix, frames carry a default position (INSA Lyon, La Doua campus).
- The bridge listens to a single helmet, configured with `TTN_DEVICE_ID`.

## Future work

- Detect head impacts with a FlexiForce pressure sensor (planned in the database schema but not implemented).
- Send emergency alerts directly to the emergency services of the activity area.
- Improve fall detection by combining acceleration and orientation data.
- Design an integrated enclosure and measure battery life.

## Authors

Second-year FIMI students, INSA Lyon.

- Gaël Boënnec
- Gabriel Mayer
- Diego Niedbalski
