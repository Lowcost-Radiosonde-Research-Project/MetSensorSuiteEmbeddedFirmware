"""BME280 combined temperature, pressure, and humidity sensor driver.

Implements the floating-point compensation formulas from the Bosch
BME280 datasheet (Rev 1.1, section 4.2.3). The sensor is operated in
forced mode: each call to read() triggers a single measurement, waits
for it to complete, and returns the compensated values.

Author: Nathaniel Peyer
Date: 06-14-2026
"""

import struct
import time

from micropython import const


# Register addresses.
_REG_CALIB_T_P = const(0x88)
_REG_CALIB_H1 = const(0xA1)
_REG_CALIB_H2_H6 = const(0xE1)
_REG_CHIP_ID = const(0xD0)
_REG_CTRL_HUM = const(0xF2)
_REG_STATUS = const(0xF3)
_REG_CTRL_MEAS = const(0xF4)
_REG_DATA = const(0xF7)

_CHIP_ID_BME280 = const(0x60)

# ctrl_hum: oversampling x1 for humidity.
_CTRL_HUM_OSRS_H1 = const(0x01)

# ctrl_meas: oversampling x1 for temperature and pressure, forced mode.
_CTRL_MEAS_FORCED = const(0x25)

_STATUS_MEASURING_BIT = const(0x08)

_MEASURE_TIMEOUT_MS = const(100)


class BME280:
    """Driver for a single BME280 sensor on an I2C bus."""

    def __init__(self, i2c, addr):
        """Initialize the sensor and read its factory calibration data.

        Args:
            i2c: An initialized machine.I2C bus instance.
            addr: 7-bit I2C address of the sensor (0x76 or 0x77).

        Raises:
            OSError: If the sensor does not respond on the bus.
            ValueError: If the chip ID register does not read 0x60.
        """
        self.i2c = i2c
        self.addr = addr
        self._t_fine = 0.0

        chip_id = self.i2c.readfrom_mem(self.addr, _REG_CHIP_ID, 1)[0]
        if chip_id != _CHIP_ID_BME280:
            raise ValueError(
                "Unexpected BME280 chip ID: 0x{:02X}".format(chip_id))

        self._read_calibration()

    def _read_calibration(self):
        """Read and unpack the factory calibration coefficients."""
        calib = self.i2c.readfrom_mem(self.addr, _REG_CALIB_T_P, 24)
        (self._dig_t1, self._dig_t2, self._dig_t3,
         self._dig_p1, self._dig_p2, self._dig_p3, self._dig_p4,
         self._dig_p5, self._dig_p6, self._dig_p7, self._dig_p8,
         self._dig_p9) = struct.unpack("<HhhHhhhhhhhh", calib)

        self._dig_h1 = self.i2c.readfrom_mem(self.addr, _REG_CALIB_H1, 1)[0]

        h_calib = self.i2c.readfrom_mem(self.addr, _REG_CALIB_H2_H6, 7)
        dig_h2 = struct.unpack("<h", h_calib[0:2])[0]
        dig_h3 = h_calib[2]

        # dig_H4 and dig_H5 are signed 12-bit values packed across three
        # bytes (E4, E5, E6) with overlapping nibbles per the datasheet.
        e4, e5, e6 = h_calib[3], h_calib[4], h_calib[5]
        dig_h4 = (e4 << 4) | (e5 & 0x0F)
        dig_h5 = (e6 << 4) | (e5 >> 4)
        if dig_h4 > 2047:
            dig_h4 -= 4096
        if dig_h5 > 2047:
            dig_h5 -= 4096

        dig_h6 = struct.unpack("<b", bytes([h_calib[6]]))[0]

        self._dig_h2 = dig_h2
        self._dig_h3 = dig_h3
        self._dig_h4 = dig_h4
        self._dig_h5 = dig_h5
        self._dig_h6 = dig_h6

    def read(self):
        """Trigger a forced-mode measurement and return compensated values.

        Returns:
            A tuple (temperature_c, pressure_hpa, humidity_pct).

        Raises:
            OSError: If the sensor does not respond on the bus, or if the
                measurement does not complete within _MEASURE_TIMEOUT_MS.
        """
        # Humidity oversampling must be written before ctrl_meas for the
        # setting to take effect.
        self.i2c.writeto_mem(self.addr, _REG_CTRL_HUM,
                              bytes([_CTRL_HUM_OSRS_H1]))
        self.i2c.writeto_mem(self.addr, _REG_CTRL_MEAS,
                              bytes([_CTRL_MEAS_FORCED]))

        start_ms = time.ticks_ms()
        while True:
            status = self.i2c.readfrom_mem(self.addr, _REG_STATUS, 1)[0]
            if (status & _STATUS_MEASURING_BIT) == 0:
                break
            if time.ticks_diff(time.ticks_ms(), start_ms) > _MEASURE_TIMEOUT_MS:
                raise OSError("BME280 measurement did not complete")
            time.sleep_ms(2)

        data = self.i2c.readfrom_mem(self.addr, _REG_DATA, 8)
        adc_p = (data[0] << 12) | (data[1] << 4) | (data[2] >> 4)
        adc_t = (data[3] << 12) | (data[4] << 4) | (data[5] >> 4)
        adc_h = (data[6] << 8) | data[7]

        temperature_c = self._compensate_temperature(adc_t)
        pressure_hpa = self._compensate_pressure(adc_p)
        humidity_pct = self._compensate_humidity(adc_h)
        return temperature_c, pressure_hpa, humidity_pct

    def _compensate_temperature(self, adc_t):
        """Apply the BME280 temperature compensation formula.

        Also stores the intermediate t_fine value, which the pressure
        and humidity compensation formulas depend on.

        Args:
            adc_t: Raw 20-bit ADC temperature reading.

        Returns:
            Compensated temperature in degrees Celsius.
        """
        var1 = (adc_t / 16384.0 - self._dig_t1 / 1024.0) * self._dig_t2
        var2 = (adc_t / 131072.0 - self._dig_t1 / 8192.0)
        var2 = var2 * var2 * self._dig_t3
        self._t_fine = var1 + var2
        return self._t_fine / 5120.0

    def _compensate_pressure(self, adc_p):
        """Apply the BME280 pressure compensation formula.

        Args:
            adc_p: Raw 20-bit ADC pressure reading.

        Returns:
            Compensated pressure in hPa. Returns 0.0 if the calibration
            data would cause a division by zero.
        """
        var1 = self._t_fine / 2.0 - 64000.0
        var2 = var1 * var1 * self._dig_p6 / 32768.0
        var2 = var2 + var1 * self._dig_p5 * 2.0
        var2 = var2 / 4.0 + self._dig_p4 * 65536.0
        var1 = (self._dig_p3 * var1 * var1 / 524288.0 +
                self._dig_p2 * var1) / 524288.0
        var1 = (1.0 + var1 / 32768.0) * self._dig_p1

        if var1 == 0:
            return 0.0

        pressure = 1048576.0 - adc_p
        pressure = (pressure - var2 / 4096.0) * 6250.0 / var1
        var1 = self._dig_p9 * pressure * pressure / 2147483648.0
        var2 = pressure * self._dig_p8 / 32768.0
        pressure = pressure + (var1 + var2 + self._dig_p7) / 16.0

        # Convert Pa to hPa.
        return pressure / 100.0

    def _compensate_humidity(self, adc_h):
        """Apply the BME280 humidity compensation formula.

        Args:
            adc_h: Raw 16-bit ADC humidity reading.

        Returns:
            Compensated relative humidity in percent, clamped to the
            0-100 range.
        """
        var_h = self._t_fine - 76800.0
        var_h = ((adc_h - (self._dig_h4 * 64.0 +
                  self._dig_h5 / 16384.0 * var_h)) *
                 (self._dig_h2 / 65536.0 *
                  (1.0 + self._dig_h6 / 67108864.0 * var_h *
                   (1.0 + self._dig_h3 / 67108864.0 * var_h))))
        var_h = var_h * (1.0 - self._dig_h1 * var_h / 524288.0)

        if var_h > 100.0:
            var_h = 100.0
        elif var_h < 0.0:
            var_h = 0.0

        return var_h


def init_bme280(i2c, addr):
    """Create and initialize a BME280 driver instance.

    Args:
        i2c: An initialized machine.I2C bus instance.
        addr: 7-bit I2C address of the sensor.

    Returns:
        A BME280 instance ready for read().

    Raises:
        OSError: If the sensor does not respond on the bus.
        ValueError: If the chip ID register is unexpected.
    """
    return BME280(i2c, addr)