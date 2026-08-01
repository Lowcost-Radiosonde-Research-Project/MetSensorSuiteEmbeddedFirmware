"""MS5611 high-resolution barometric pressure sensor driver.

Implements the PROM calibration read and the first- and second-order
temperature compensation formulas from the MS5611 datasheet. Each
read() triggers a D2 (temperature) conversion and a D1 (pressure)
conversion in sequence, then computes temperature and pressure
together - the pressure compensation depends on the temperature
result.

Author: Nathaniel Peyer
Date: 06-15-2026
Last edited: 06-24-2026
"""

import time

from micropython import const


_CMD_RESET = const(0x1E)
_CMD_ADC_READ = const(0x00)
_CMD_CONVERT_D1 = const(0x40)  # pressure
_CMD_CONVERT_D2 = const(0x50)  # temperature
_CMD_PROM_READ_BASE = const(0xA2)  # C1..C6 at 0xA2, 0xA4, ..., 0xAC

# OSR (oversampling ratio) setting, ORed into the D1/D2 convert
# commands. Higher OSR -> better resolution, longer conversion time.
#   0x00 -> OSR=256,  max conversion time 0.6ms
#   0x02 -> OSR=512,  max conversion time 1.17ms
#   0x04 -> OSR=1024, max conversion time 2.28ms
#   0x06 -> OSR=2048, max conversion time 4.54ms
#   0x08 -> OSR=4096, max conversion time 9.04ms
_OSR = const(0x08)
_CONVERT_DELAY_MS = const(10)  # >= 9.04ms (OSR=4096) with margin

_RESET_DELAY_MS = const(3)  # datasheet: reset sequence takes ~2.8ms


def _idiv(numerator, denominator):
    """Integer-divide, truncating toward zero (matches the datasheet).

    Python's // operator floors toward negative infinity; the MS5611
    compensation formulas are specified using C's truncating integer
    division. denominator is always a positive power of two in this
    module, so only numerator's sign needs correcting.

    Args:
        numerator: Signed integer numerator.
        denominator: Positive integer denominator.

    Returns:
        numerator / denominator, truncated toward zero.
    """
    quotient = abs(numerator) // denominator
    return -quotient if numerator < 0 else quotient


class MS5611:
    """Driver for the MS5611 pressure/temperature sensor."""

    def __init__(self, i2c, addr):
        """Reset the sensor and read its factory calibration data.

        Args:
            i2c: An initialized machine.I2C bus instance.
            addr: 7-bit I2C address of the sensor (0x76 or 0x77).

        Raises:
            OSError: If the sensor does not respond on the bus.
        """
        self.i2c = i2c
        self.addr = addr

        self.i2c.writeto(self.addr, bytes([_CMD_RESET]))
        time.sleep_ms(_RESET_DELAY_MS)

        self._read_calibration()

    def _read_calibration(self):
        """Read the six PROM calibration coefficients C1-C6."""
        coeffs = []
        for i in range(6):
            cmd = _CMD_PROM_READ_BASE + 2 * i
            raw = self.i2c.readfrom_mem(self.addr, cmd, 2)
            coeffs.append((raw[0] << 8) | raw[1])
        (self._c1, self._c2, self._c3,
         self._c4, self._c5, self._c6) = coeffs

    def _read_adc(self, convert_cmd):
        """Trigger a conversion and read the resulting 24-bit ADC value.

        Args:
            convert_cmd: D1 or D2 convert command byte, including OSR.

        Returns:
            24-bit unsigned ADC result.
        """
        self.i2c.writeto(self.addr, bytes([convert_cmd]))
        time.sleep_ms(_CONVERT_DELAY_MS)
        raw = self.i2c.readfrom_mem(self.addr, _CMD_ADC_READ, 3)
        return (raw[0] << 16) | (raw[1] << 8) | raw[2]

    def read(self):
        """Read and compensate temperature and pressure.

        Compensation formulas per MS5611 datasheet (AN520):
          dT   = D2 - C5 * 2^8
          TEMP = 2000 + dT * C6 / 2^23
          OFF  = C2 * 2^17 + (C4 * dT) / 2^6
          SENS = C1 * 2^16 + (C3 * dT) / 2^7
          P    = (D1 * SENS / 2^21 - OFF) / 2^15

        Returns:
            A tuple (temperature_c, pressure_hpa).

        Raises:
            OSError: If the sensor does not respond on the bus.
        """
        d2 = self._read_adc(_CMD_CONVERT_D2 | _OSR)
        d1 = self._read_adc(_CMD_CONVERT_D1 | _OSR)

        dt   = d2 - self._c5 * 256
        temp = 2000 + _idiv(dt * self._c6, 2 ** 23)

        # Corrected exponents per datasheet AN520:
        #   OFF:  C2 * 2^17, (C4 * dT) / 2^6
        #   SENS: C1 * 2^16, (C3 * dT) / 2^7
        off  = self._c2 * (2 ** 17) + _idiv(self._c4 * dt, 2 ** 6)
        sens = self._c1 * (2 ** 16) + _idiv(self._c3 * dt, 2 ** 7)

        # Second-order temperature compensation for T < 20.00 C.
        if temp < 2000:
            t2    = _idiv(dt * dt, 2 ** 31)
            off2  = _idiv(5 * (temp - 2000) ** 2, 2)
            sens2 = _idiv(5 * (temp - 2000) ** 2, 4)
            if temp < -1500:
                off2  += 7 * (temp + 1500) ** 2
                sens2 += _idiv(11 * (temp + 1500) ** 2, 2)
        else:
            t2 = off2 = sens2 = 0

        temp -= t2
        off  -= off2
        sens -= sens2

        pressure = _idiv(_idiv(d1 * sens, 2 ** 21) - off, 2 ** 15)

        return temp / 100.0, pressure / 100.0


def init_ms5611(i2c, addr):
    """Create and initialize an MS5611 driver instance.

    Args:
        i2c: An initialized machine.I2C bus instance.
        addr: 7-bit I2C address of the sensor.

    Returns:
        An MS5611 instance ready for read().

    Raises:
        OSError: If the sensor does not respond on the bus.
    """
    return MS5611(i2c, addr)