"""Fixed-width binary record format for the Met Pico sensor log.

Each record represents one sample cycle from the full sensor suite.
Sensors that are not yet implemented or that fail during a read report
float('nan') for their fields (or NO_DATA_U8 for the GPS satellite
count) so that downstream decoding can distinguish "no data" from a
genuine zero reading.

Record layout (little-endian, no padding), PACKET_FORMAT = "<I15fB":

    timestamp_ms          uint32   time.ticks_ms() at sample time
    bme280_temp_c         float32  BME280 temperature, deg C
    bme280_pressure_hpa   float32  BME280 pressure, hPa
    bme280_humidity_pct   float32  BME280 relative humidity, %
    ms5611_temp_c         float32  MS5611 temperature, deg C
    ms5611_pressure_hpa   float32  MS5611 pressure, hPa
    rtd_temp_c            float32  PT1000 temperature, deg C
    bmi330_accel_x_mg     float32  BMI330 accelerometer X, milli-g
    bmi330_accel_y_mg     float32  BMI330 accelerometer Y, milli-g
    bmi330_accel_z_mg     float32  BMI330 accelerometer Z, milli-g
    bmi330_gyro_x_mdps    float32  BMI330 gyroscope X, milli-deg/s
    bmi330_gyro_y_mdps    float32  BMI330 gyroscope Y, milli-deg/s
    bmi330_gyro_z_mdps    float32  BMI330 gyroscope Z, milli-deg/s
    gps_lat_deg           float32  GPS latitude, decimal degrees
    gps_lon_deg           float32  GPS longitude, decimal degrees
    gps_alt_m             float32  GPS altitude, meters
    gps_num_sats          uint8    Satellites used in fix (NO_DATA_U8 = no data)

    Author: Nathaniel Peyer
    Date: 06-14-2026
"""

import struct


PACKET_FORMAT = "<I15fB"
PACKET_SIZE = struct.calcsize(PACKET_FORMAT)

# Field names in struct order. pack_record() / unpack_record() use this
# tuple so the record layout only has to be maintained in one place.
FIELD_NAMES = (
    "timestamp_ms",
    "bme280_temp_c",
    "bme280_pressure_hpa",
    "bme280_humidity_pct",
    "ms5611_temp_c",
    "ms5611_pressure_hpa",
    "rtd_temp_c",
    "bmi330_accel_x_mg",
    "bmi330_accel_y_mg",
    "bmi330_accel_z_mg",
    "bmi330_gyro_x_mdps",
    "bmi330_gyro_y_mdps",
    "bmi330_gyro_z_mdps",
    "gps_lat_deg",
    "gps_lon_deg",
    "gps_alt_m",
    "gps_num_sats",
)

# Sentinels used for missing/unavailable sensor data.
NAN = float("nan")
NO_DATA_U8 = 0xFF


def pack_record(values):
    """Pack a dict of sensor values into a fixed-width binary record.

    Args:
        values: Dict containing all keys listed in FIELD_NAMES. Missing
            float fields should be NAN and gps_num_sats should be
            NO_DATA_U8 if unavailable.

    Returns:
        A bytes object of length PACKET_SIZE ready to append to the SD
        log file or send over the link UART.
    """
    ordered = [values[name] for name in FIELD_NAMES]
    return struct.pack(PACKET_FORMAT, *ordered)


def unpack_record(raw):
    """Unpack one fixed-width binary record into a dict of values.

    Args:
        raw: Bytes object of length PACKET_SIZE, as produced by
            pack_record().

    Returns:
        A dict mapping each name in FIELD_NAMES to its decoded value.

    Raises:
        struct.error: If raw is not exactly PACKET_SIZE bytes.
    """
    unpacked = struct.unpack(PACKET_FORMAT, raw)
    return dict(zip(FIELD_NAMES, unpacked))


def new_blank_record():
    """Build a values dict with every field set to its "no data" sentinel.

    Useful as a starting point each sample cycle: sensor read functions
    fill in only the fields they own, and anything left untouched packs
    as "no data" rather than as a misleading zero.

    Returns:
        A dict with all FIELD_NAMES keys present. timestamp_ms is set to
        0, gps_num_sats is set to NO_DATA_U8, and every other field is
        set to NAN.
    """
    record = {}
    for name in FIELD_NAMES:
        if name == "timestamp_ms":
            record[name] = 0
        elif name == "gps_num_sats":
            record[name] = NO_DATA_U8
        else:
            record[name] = NAN
    return record