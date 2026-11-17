# LoRaWAN payload format

Every uplink sent by the helmet is a fixed 18-byte frame. All multi-byte fields are big-endian.

| Bytes  | Field                         | Type   | Description                                          |
|--------|-------------------------------|--------|------------------------------------------------------|
| 0      | `type`                        | uint8  | `0x01` periodic, `0x02` fall, `0x03` avalanche       |
| 1-4    | `latitude_T`                  | int32  | Current latitude, degrees x 1e6                      |
| 5-8    | `longitude_T`                 | int32  | Current longitude, degrees x 1e6                     |
| 9-10   | delta latitude T -> T-6s      | int16  | `lat(T) - lat(T-6s)`, degrees x 1e6                  |
| 11-12  | delta longitude T -> T-6s     | int16  | `lon(T) - lon(T-6s)`, degrees x 1e6                  |
| 13-14  | delta latitude T-6s -> T-12s  | int16  | `lat(T-6s) - lat(T-12s)`, degrees x 1e6              |
| 15-16  | delta longitude T-6s -> T-12s | int16  | `lon(T-6s) - lon(T-12s)`, degrees x 1e6              |
| 17     | `vitesse_kmh`                 | uint8  | Current GPS speed in km/h (0 when no valid fix)      |

Sending the two previous positions as 16-bit deltas instead of absolute
coordinates saves 8 bytes per frame. An int16 delta covers +/- 0.032767 degrees,
about +/- 3.6 km in latitude, which is far more than a skier or cyclist moves in 6 seconds.

## Decoded JSON (TTN payload formatter)

`ttn/payload_decoder.js` turns the frame into the following object, which is
what `backend/ttn_to_mariadb_bridge.py` reads:

```json
{
  "type": "PERIODIQUE",
  "latitude_T": 45.7831,
  "longitude_T": 4.8774,
  "latitude_T_moins_6s": 45.78305,
  "longitude_T_moins_6s": 4.87735,
  "latitude_T_moins_12s": 45.783,
  "longitude_T_moins_12s": 4.8773,
  "vitesse_kmh": 12
}
```

`type` is one of `PERIODIQUE`, `CHUTE` (fall), `AVALANCHE` or `INCONNU` (unknown).

## Timing

| Event                  | Period                                   |
|------------------------|------------------------------------------|
| IMU and light sampling | 100 ms                                   |
| GPS snapshot           | 6 s (keeps the last three positions)     |
| Periodic uplink        | 18 s (three snapshots per frame)         |
| Alert uplink           | Immediately after a fall or avalanche    |

With a snapshot every 6 s and a frame every 18 s, consecutive periodic frames
cover the trajectory without gaps.
