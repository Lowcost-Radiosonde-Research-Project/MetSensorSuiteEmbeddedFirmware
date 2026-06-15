"""Met Pico main sample loop.

Initializes the full sensor suite, then runs a fixed-interval loop that
reads every sensor, assembles one packet.FIELD_NAMES record, appends it
to the SD card log, and builds a 38-byte iMet-1-RSB frame (GPS Data
Packet + PTU-enhanced Data Packet, see imet_packet.py) which is sent to
the RF Pico over the link UART for AFSK transmission. Also prints a
one-line summary to the console for live monitoring.

Sensors that fail to initialize or raise an error during read() report
NAN (or NO_DATA_U8 for the GPS satellite count) for their portion of
the record rather than halting the loop, per the "fail loudly in
development, not in flight" principle - a single bad sensor should not
take down the whole log.

Author: Nathaniel Peyer
Date: 06-14-2026
Last edited: 06-15-2026 
"""

import time

from machine import I2C, Pin, UART

import config
import packet
import imet_packet
import link_uart
from bme280 import init_bme280
from ms5611 import init_ms5611
from bmi330 import init_bmi330
from rtd_ads1115 import init_ads1115
from gps_neo_m9n import init_gps
from sd_logger import init_sd_logger


def _safe_init(name, init_fn, *args):
    """Attempt to initialize a sensor, logging and continuing on failure.

    Args:
        name: Human-readable sensor name for log messages.
        init_fn: Callable that performs the initialization.
        *args: Positional arguments passed to init_fn.

    Returns:
        The result of init_fn(*args), or None if initialization raised
        OSError or ValueError.
    """
    try:
        return init_fn(*args)
    except (OSError, ValueError) as e:
        print("[WARN] {} init failed: {}".format(name, e))
        return None


def main():
    """Run the Met Pico sensor acquisition and logging loop."""
    # The 3.3V sensor rail is gated by the LM2596's EN pin - assert it
    # and give the regulator a moment to settle before touching any
    # I2C/UART peripheral, or every sensor init below will fail with
    # no ACK.
    regulator_en = Pin(config.REGULATOR_EN_PIN, Pin.OUT)
    regulator_en.value(1)
    time.sleep_ms(config.REGULATOR_ENABLE_DELAY_MS)

    i2c1 = I2C(config.I2C1,
               scl=Pin(config.I2C1_SCL_PIN),
               sda=Pin(config.I2C1_SDA_PIN),
               freq=config.I2C1_FREQ_HZ)
    i2c2 = I2C(config.I2C2,
               scl=Pin(config.I2C2_SCL_PIN),
               sda=Pin(config.I2C2_SDA_PIN),
               freq=config.I2C2_FREQ_HZ)

    try:
        gps_uart = UART(config.GPS_UART_ID,
                         baudrate=config.GPS_UART_BAUD_RATE,
                         tx=Pin(config.GPS_UART_TX_PIN),
                         rx=Pin(config.GPS_UART_RX_PIN))
    except (OSError, ValueError) as e:
        print("[WARN] GPS UART init failed: {}".format(e))
        gps_uart = None

    try:
        link_port = UART(config.LINK_UART_ID,
                          baudrate=config.LINK_UART_BAUD_RATE,
                          tx=Pin(config.LINK_UART_TX_PIN),
                          rx=Pin(config.LINK_UART_RX_PIN))
    except (OSError, ValueError) as e:
        print("[WARN] Link UART init failed: {}".format(e))
        link_port = None

    # ADS1115 and BME280 are on I2C bus 1.
    # MS5611 and BMI330 are on I2C bus 2.
    bme = _safe_init("BME280", init_bme280, i2c1, config.BME280_I2C_ADDR)
    rtd = _safe_init("RTD/ADS1115", init_ads1115, i2c1,
                      config.ADS1115_I2C_ADDR)
    ms5611 = _safe_init("MS5611", init_ms5611, i2c2, config.MS5611_I2C_ADDR)
    bmi330 = _safe_init("BMI330", init_bmi330, i2c2, config.BMI330_I2C_ADDR)
    gps = _safe_init("GPS/NEO-M9N", init_gps, gps_uart)
    sd_logger = _safe_init("SD card", init_sd_logger)

    next_sample_ms = time.ticks_ms()

    # Sequence number for the iMet PTU-enhanced packet's PKT field.
    # Wraps at 65536 (imet_packet.pack_ptu_enhanced_packet masks it too).
    imet_pkt_num = 0

    while True:
        now_ms = time.ticks_ms()
        if time.ticks_diff(now_ms, next_sample_ms) < 0:
            time.sleep_ms(1)
            continue
        next_sample_ms = time.ticks_add(next_sample_ms,
                                         config.SAMPLE_INTERVAL_MS)

        record = packet.new_blank_record()
        record["timestamp_ms"] = now_ms

        if bme is not None:
            try:
                (record["bme280_temp_c"],
                 record["bme280_pressure_hpa"],
                 record["bme280_humidity_pct"]) = bme.read()
            except OSError as e:
                print("[WARN] BME280 read failed: {}".format(e))

        if ms5611 is not None:
            try:
                (record["ms5611_temp_c"],
                 record["ms5611_pressure_hpa"]) = ms5611.read()
            except OSError as e:
                print("[WARN] MS5611 read failed: {}".format(e))

        if rtd is not None:
            try:
                record["rtd_temp_c"] = rtd.read_temperature_c()
            except OSError as e:
                print("[WARN] RTD/ADS1115 read failed: {}".format(e))

        if bmi330 is not None:
            try:
                (record["bmi330_accel_x_mg"],
                 record["bmi330_accel_y_mg"],
                 record["bmi330_accel_z_mg"],
                 record["bmi330_gyro_x_mdps"],
                 record["bmi330_gyro_y_mdps"],
                 record["bmi330_gyro_z_mdps"]) = bmi330.read()
            except OSError as e:
                print("[WARN] BMI330 read failed: {}".format(e))

        if gps is not None:
            try:
                (record["gps_lat_deg"],
                 record["gps_lon_deg"],
                 record["gps_alt_m"],
                 record["gps_num_sats"],
                 record["gps_hour"],
                 record["gps_minute"],
                 record["gps_second"]) = gps.read()
            except OSError as e:
                print("[WARN] GPS/NEO-M9N read failed: {}".format(e))

        record_bytes = packet.pack_record(record)

        if sd_logger is not None:
            try:
                sd_logger.write_record(record_bytes)
            except OSError as e:
                print("[WARN] SD card log append failed: {}".format(e))

        # --- iMet-1-RSB downlink frame ---
        # Sensor -> iMet field mapping (see imet_packet.py for field
        # definitions; this mapping is just keyword arguments below,
        # so it's a one-line change if you want a different sensor in
        # a given slot):
        #   GPS lat/lon/alt/num_sats/hour/min/sec -> straight from the
        #                               GPS record fields
        #   P    (pressure)          -> ms5611_pressure_hpa (TODO:
        #                               confirm - currently NAN since
        #                               MS5611 read may still fail on
        #                               first hardware bring-up)
        #   T    (primary temp)      -> bme280_temp_c
        #   U    (humidity)          -> bme280_humidity_pct
        #   Vbat (battery voltage)   -> not yet measured; NAN = no data
        #   Tint (internal temp)     -> bme280_temp_c (TODO: confirm -
        #                               currently duplicates T)
        #   Tpr  (probe temp)        -> rtd_temp_c
        #   Tu   (aux temp)          -> not yet mapped; NAN = no data
        imet_frame = imet_packet.pack_frame(
            {
                "lat_deg": record["gps_lat_deg"],
                "lon_deg": record["gps_lon_deg"],
                "alt_m": record["gps_alt_m"],
                "num_sats": record["gps_num_sats"],
                "hour": record["gps_hour"],
                "minute": record["gps_minute"],
                "second": record["gps_second"],
            },
            {
                "pkt_num": imet_pkt_num,
                "pressure_hpa": record["ms5611_pressure_hpa"],
                "temp_c": record["bme280_temp_c"],
                "humidity_pct": record["bme280_humidity_pct"],
                "vbat_v": packet.NAN,
                "temp_int_c": record["bme280_temp_c"],
                "temp_probe_c": record["rtd_temp_c"],
                "temp_u_c": packet.NAN,
            })
        imet_pkt_num = (imet_pkt_num + 1) & 0xFFFF

        if link_port is not None:
            try:
                link_uart.send_record(link_port, imet_frame)
            except OSError as e:
                print("[WARN] Link UART send failed: {}".format(e))

        print("t={:>8d}ms  T={:6.2f}C  P={:7.2f}hPa  RH={:5.1f}%  "
              "RTD={:6.2f}C".format(
                  record["timestamp_ms"], record["bme280_temp_c"],
                  record["bme280_pressure_hpa"],
                  record["bme280_humidity_pct"], record["rtd_temp_c"]))


if __name__ == "__main__":
    main()