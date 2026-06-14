"""Met Pico main sample Loop

Initializes the full sensor suite, then runs a fixed-interval loop that
reads every sensor, assembles one packet.FIELD_NAMES record, appends it
to the SD card log, and prints a one-line summary to the console for
live monitoring.

Sensors that fail to initialize or raise an error during read() reports
NAN (or NO_DATA_U8 for the GPS integer fields) for their portions of the 
record rather than halting the loop, per the "fail loudly in development,
not in flight" principle - a single bad sensor should not take down the
whole log.

Author: Nathaniel Peyer
Date 06-14-2026
"""

import time

from machine import I2C, Pin, UART

import config
import packet
import link_uart
from bme280 import init_bme280
from ms5611 import init_ms5611
from bmi330 import init_bmi330
from rtd_ads1115 import init_ads1115
from gps_neo_m9n import init_gps
from sd_logger import init_sd_logger

def _safe_init(name, init_fn, *args):
    """Attempt to intialize a sensor, logging and continuing on failure.

    Args:
        name: Human-readable sensor name for log messages.
        init_fn: Callable that performs the initialization.
        *args: Positional arguments to pass to init_fn.

    Returns:
        The result of init_fun(*args), or None if initialization raised
        OSError or ValueError.   
    """ 

    try:
        return init_fn(*args)
    except (OSError, ValueError) as e:
        print("[Warn] {} init failed: {}".format(name,e))
        return None

def main():
    """Running the Met Pico sensor acquisition and logging loop"""
    i2c1 = I2C(config.I2C1,
               scl = Pin(config.I2C1_SCL_PIN),
               sda = Pin(config.I2C1_SDA_PIN),
               freq = config.I2C1_FREQ_HZ)

    i2c2= I2C(config.I2C2,
              scl = Pin(config.I2C2_SCL_PIN),
              sda = Pin(config.I2C2_SDA_PIN),
              freq = config.I2C2_FREQ_HZ)

    try:
        gps_uart = UART(config.GPS_UART_ID,\
                        baudrate = config.GPS_UART_BAUD_RATE,
                        tx = Pin(config.GPS_UART_TX_PIN),
                        rx = Pin(config.GPS_UART_RX_PIN))
    except(OSError, ValueError) as e:
        print("[Warn] GPS UART init failed: {}".format(e))
        gps_uart = None

    try:
        link_port = UART(config.LINK_UART_ID,
                         baudrate = config.LINK_UART_BAUD_RATE,
                         tx = Pin(config.LINK_UART_TX_PIN),
                         rx = Pin(config.LINK_UART_RX_PIN))
    except(OSError, ValueError) as e:
        print("[Warn] LINK UART init failed: {}".format(e))
        link_port = None

    # ADS1115 and BME 280 are on I2C1.
    # MS5611 and BMI330 are on I2C2.

    bme = _safe_init("BME280", init_bme280, i2c1, config.BME280_I2C_ADDR)
    rtd = _safe_init("RTD/ADS1115", init_ads1115, i2c1, config.ADS1115_I2C_ADDR)
    ms5611 =_safe_init("MS5611", init_ms5611, i2c2, config.MS5611_I2C_ADDR)
    bmi330 = _safe_init("BMI330", init_bmi330, i2c2, config.BMI330_I2C_ADDR)
    gps = _safe_init("GPS/NEO-M9N", init_gps, gps_uart)
    sd_logger = _safe_init("SD card", init_sd_logger)

    next_sample_ms = time.ticks_ms()

    while True:
        now_ms = time.ticks_ms()
        if time.ticks_diff(now_ms, next_sample_ms) < 0:
            time.sleep_ms(1)
            continue
        next_sample_ms = time.ticks_add(next_sample_ms, config.SAMPLE_INTERVAL_MS)

        record = packet.new_blank_record()
        record["timestamp_ms"] = now_ms

        if bme is not None:
            try:
                (record["bme280_temp_c"],
                 record["bme280_pressure_hp"],
                 record["bme280_humidity_pct"]) = bme.read()
            except OSError as e:
               print("[Warn] BME280 read failed: {}".format(e))

        if ms5611 is not None:
            try:
                (record["ms5611_pressure_hp"],
                 record["ms5611_temp_c"]) = ms5611.read()
            except OSError as e:
               print("[Warn] MS5611 read failed: {}".format(e))

        if rtd is not None:
            try:
                record["rtd_temp_c"] = rtd.read_temperature_c()
            except OSError as e:
               print("[Warn] RTD/ADS1115 read failed: {}".format(e))

        if bmi330 is not None:
            try:
                (record["bmi330_accel_x_mg"],
                 record["bmi330_accel_y_mg"],
                 record["bmi330_accel_z_mg"],
                 record["bmi330_gyro_x_mdps"],
                 record["bmi330_gyro_y_mdps"],
                 record["bmi330_gyro_z_mdps"]) = bmi330.read()
            except OSError as e:
               print("[Warn] BMI330 read failed: {}".format(e))

        if gps is not None:
            try:
                (record["gps_lat_deg"],
                 record["gps_lon_deg"],
                 record["gps_alt_m"],
                 record["gps_num_sats"]) = gps.read()
            except OSError as e:
               print("[Warn] GPS/NEO-M9N read failed: {}".format(e))

        if sd_logger is not None:
            try:
                sd_logger.append_record(record)
            except OSError as e:
               print("[Warn] SD card log append failed: {}".format(e))

        if link_port is not None:
            try:
                link_uart.send_record(link_port, record)
            except OSError as e:
               print("[Warn] Link UART send failed: {}".format(e))

        print("t={:>8d}ms T={:6.2f}C P={:7.2f}hPa RH={5.1f%}%  " 
              "RTD={:6.2f}C".format(
                  record["timestamp_ms"], record["bme280_temp_c"], record["bme280_pressure_hp"],
                    record["bme280_humidity_pct"], record["rtd_temp_c"]
              ))

if __name__ == "__main__":
    main()