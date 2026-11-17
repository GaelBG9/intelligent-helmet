// The Things Network (TTS v3) uplink payload formatter for the Intelligent Helmet.
// Paste this function in: Application > Payload formatters > Uplink > Custom Javascript formatter.
// Frame layout: see docs/payload-format.md

function decodeUplink(input) {
  var bytes = input.bytes;
  if (bytes.length !== 18) {
    return { errors: ["Payload size mismatch. Expected 18 bytes."] };
  }

  var data = {};

  // 1. Message type
  if (bytes[0] === 0x01) data.type = "PERIODIQUE";
  else if (bytes[0] === 0x02) data.type = "CHUTE";
  else if (bytes[0] === 0x03) data.type = "AVALANCHE";
  else data.type = "INCONNU";

  // 2. Current position (T) - signed 32-bit, degrees * 1e6
  var lat0_raw = (bytes[1] << 24) | (bytes[2] << 16) | (bytes[3] << 8) | bytes[4];
  var lon0_raw = (bytes[5] << 24) | (bytes[6] << 16) | (bytes[7] << 8) | bytes[8];
  data.latitude_T = lat0_raw / 1000000.0;
  data.longitude_T = lon0_raw / 1000000.0;

  // 3. Deltas T -> T-6s (signed 16-bit)
  var deltaLat1 = (bytes[9] << 8) | bytes[10];
  if (deltaLat1 > 32767) deltaLat1 -= 65536;
  var deltaLon1 = (bytes[11] << 8) | bytes[12];
  if (deltaLon1 > 32767) deltaLon1 -= 65536;

  data.latitude_T_moins_6s = (lat0_raw - deltaLat1) / 1000000.0;
  data.longitude_T_moins_6s = (lon0_raw - deltaLon1) / 1000000.0;

  // 4. Deltas T-6s -> T-12s (signed 16-bit)
  var lat1_raw = lat0_raw - deltaLat1;
  var lon1_raw = lon0_raw - deltaLon1;

  var deltaLat2 = (bytes[13] << 8) | bytes[14];
  if (deltaLat2 > 32767) deltaLat2 -= 65536;
  var deltaLon2 = (bytes[15] << 8) | bytes[16];
  if (deltaLon2 > 32767) deltaLon2 -= 65536;

  data.latitude_T_moins_12s = (lat1_raw - deltaLat2) / 1000000.0;
  data.longitude_T_moins_12s = (lon1_raw - deltaLon2) / 1000000.0;

  // 5. Speed (unsigned 8-bit, km/h)
  data.vitesse_kmh = bytes[17];

  return {
    data: data,
    warnings: [],
    errors: []
  };
}
