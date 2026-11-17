"""
TTN -> MariaDB bridge for the Intelligent Helmet.

Subscribes to the helmet uplinks on The Things Network MQTT broker and, for
every decoded message:
  - looks up the active session of the helmet (Sessions.DateFin IS NULL),
  - stores the three GPS points (T, T-6s, T-12s) in the infotrajet table,
  - stores an alert in the alerte table when the message is not periodic.

Configuration is read from environment variables (see .env.example).
"""

import os
import time
from datetime import datetime, timedelta

import pymysql
from dotenv import load_dotenv

from ttn_client import TTNClient

load_dotenv()

DB_CONFIG = {
    'user': os.getenv('DB_USER', 'root'),
    'password': os.getenv('DB_PASSWORD', ''),
    'host': os.getenv('DB_HOST', 'localhost'),
    'port': int(os.getenv('DB_PORT', '3306')),
    'database': os.getenv('DB_NAME', 'Projet_casque'),
}


class MariaDBBridgeHandler:
    def __init__(self, db_config):
        self.config = db_config

    def on_ttn_message(self, device_payload):
        """Called by TTNClient every time the helmet sends an uplink."""
        conn = None
        cursor = None
        try:
            # Data extracted from the TTN message
            device_id = device_payload['device_id']
            date_msg = device_payload.get('date') or datetime.now()
            decoded = device_payload.get('json', None)

            if not decoded:
                print(f"Message received from {device_id} but the TTN payload formatter output is empty.")
                return

            # Fields produced by ttn/payload_decoder.js
            msg_type = decoded.get('type', 'INCONNU')
            lat_t0 = decoded.get('latitude_T', 0.0)
            lon_t0 = decoded.get('longitude_T', 0.0)
            lat_t6 = decoded.get('latitude_T_moins_6s', 0.0)
            lon_t6 = decoded.get('longitude_T_moins_6s', 0.0)
            lat_t12 = decoded.get('latitude_T_moins_12s', 0.0)
            lon_t12 = decoded.get('longitude_T_moins_12s', 0.0)
            speed = decoded.get('vitesse_kmh', 0.0)

            print(f"\n[TTN] Message from {device_id} | Type: {msg_type}")

            conn = pymysql.connect(**self.config)
            cursor = conn.cursor(pymysql.cursors.DictCursor)

            # Find the active session of this helmet
            sql_session = """SELECT IdSession FROM sessions
                             WHERE IdentifiantCasque = %s AND DateFin IS NULL
                             LIMIT 1"""
            cursor.execute(sql_session, (device_id,))
            active_session = cursor.fetchone()

            if not active_session:
                print(f"Message from {device_id} ignored: no active session (DateFin IS NULL) for this helmet.")
                return

            id_session = active_session['IdSession']

            # 1. Trajectory: current point and the two previous snapshots
            trajectory_points = [
                (date_msg, lat_t0, lon_t0, speed, id_session),
                (date_msg - timedelta(seconds=6), lat_t6, lon_t6, None, id_session),
                (date_msg - timedelta(seconds=12), lat_t12, lon_t12, None, id_session),
            ]

            sql_insert_point = """INSERT INTO infotrajet
                                  (DateHeureMesure, latitude, longitude, MesureVitesse, IdSession)
                                  VALUES (%s, %s, %s, %s, %s)"""
            for point in trajectory_points:
                cursor.execute(sql_insert_point, point)

            print(f"3 history points inserted (session {id_session}).")

            # 2. Emergency messages
            if msg_type != "PERIODIQUE":
                sql_insert_alert = """INSERT INTO alerte
                                      (HeureAlerte, latitude, longitude, IdSession, TypeAlerte)
                                      VALUES (%s, %s, %s, %s, %s)"""
                cursor.execute(sql_insert_alert, (date_msg, lat_t0, lon_t0, id_session, msg_type))
                print(f"ALERT STORED: {msg_type}")

            conn.commit()

        except Exception as e:
            print(f"Error while processing message: {e}")

        finally:
            if cursor:
                cursor.close()
            if conn:
                conn.close()


if __name__ == "__main__":
    bridge_handler = MariaDBBridgeHandler(DB_CONFIG)

    # TTN network configuration
    client = TTNClient(
        host=os.getenv('TTN_HOST', 'eu1.cloud.thethings.network'),
        application_id=os.environ['TTN_APP_ID'],
        application_access_key=os.environ['TTN_API_KEY'],
        ttn_data_handler=bridge_handler,
    )

    device_id = os.getenv('TTN_DEVICE_ID', 'arduino-mkr-1310-1')

    print("Starting LoRaWAN -> MariaDB bridge")

    client.mqtt_register_device(device_id)
    client.mqtt_connect()
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        print("\nStopping bridge...")
        client.mqtt_disconnect()
