"""4-wire PT1000 RTD interface via ADS1115 differential ADC.

The RTD is measured ratiometrically against a known reference resistor:
both the RTD and the reference resistor are driven by the same
excitation current, so the ratio of their ADC readings cancels out the
excitation current's absolute accuracy and the ADC's LSB size. Only the
known reference resistance is needed to compute the RTD resistance.

RTD resistance is converted to temperature using the Callendar-Van
Dusen equation for PT1000 (valid for T >= 0 deg C; a sub-zero
extension is noted as a TODO below since the balloon will see negative
temperatures at altitude).

Author: Nathaniel Peyer
Date: 06-14-2026
"""

import struct
import time

from micropython import const

import python.config as config


_REG_CONVERSION = const(0x00)
_REG_CONFIG = const(0x01)

# Config register bit positions (see ADS1115 datasheet Table 8). Unlike
# most of the I2C registers used elsewhere in this project, the ADS1115
# config and conversion registers are big-endian (MSB first).
_OS_SINGLE = const(0x8000)
_MODE_SINGLE_SHOT = const(0x0100)
_DR_128SPS = const(0x0080)
_COMP_QUE_DISABLE = const(0x0003)

_CONVERSION_TIME_MS = const(10)


class RTDInterface:
    """Driver for a PT1000 RTD read ratiometrically via an ADS1115."""

    def __init__(self, i2c, addr):
        """Store the bus and address for later use.

        Args:
            i2c: An initialized machine.I2C bus instance.
            addr: 7-bit I2C address of the ADS1115.
        """
        self.i2c = i2c
        self.addr = addr

    def _read_differential(self, mux):
        """Trigger a single-shot conversion and return the signed result.

        Args:
            mux: 3-bit MUX code selecting the differential input pair.

        Returns:
            Signed 16-bit ADC conversion result.

        Raises:
            OSError: If the ADS1115 does not respond on the bus.
        """
        cfg = (_OS_SINGLE | (mux << 12) | (config.ADS1115_GAIN << 9) |
               _MODE_SINGLE_SHOT | _DR_128SPS | _COMP_QUE_DISABLE)
        self.i2c.writeto_mem(self.addr, _REG_CONFIG, struct.pack(">H", cfg))
        time.sleep_ms(_CONVERSION_TIME_MS)
        raw = self.i2c.readfrom_mem(self.addr, _REG_CONVERSION, 2)
        return struct.unpack(">h", raw)[0]

    def read_resistance(self):
        """Measure the RTD resistance ratiometrically.

        Returns:
            RTD resistance in ohms, or NAN if the reference reading is
            zero (would otherwise divide by zero).

        Raises:
            OSError: If the ADS1115 does not respond on the bus.
        """
        adc_rtd = self._read_differential(config.RTD_MUX)
        adc_ref = self._read_differential(config.REF_MUX)

        if adc_ref == 0:
            return float("nan")

        return (adc_rtd / adc_ref) * config.RTD_REF_RESISTANCE_OHMS

    def read_temperature_c(self):
        """Measure RTD resistance and convert to temperature.

        Uses the Callendar-Van Dusen equation for PT1000, valid for
        T >= 0 deg C:

            R(T) = R0 * (1 + A*T + B*T^2)

        which inverts to a closed-form quadratic in T. Below 0 deg C
        the full Callendar-Van Dusen equation adds a cubic term and the
        inversion requires iteration.

        TODO: add the sub-zero (T < 0 deg C) inversion before flight -
        ground-test temperatures should stay positive, but the balloon
        will see well below 0 deg C at altitude.

        Returns:
            Temperature in degrees Celsius, computed assuming T >= 0.
            Returns NAN if the resistance reading itself is NAN.

        Raises:
            OSError: If the ADS1115 does not respond on the bus.
        """
        resistance = self.read_resistance()

        # NaN check: NaN is the only float that is not equal to itself.
        if resistance != resistance:
            return float("nan")

        r0 = config.RTD_R0_OHMS
        a = config.RTD_CVD_A
        b = config.RTD_CVD_B

        # Solve b*T^2 + a*T + (1 - R/R0) = 0 for the positive root.
        c = 1.0 - resistance / r0
        discriminant = a * a - 4.0 * b * c
        temperature_c = (-a + discriminant ** 0.5) / (2.0 * b)
        return temperature_c


def init_ads1115(i2c, addr):
    """Create an RTDInterface driver instance.

    Args:
        i2c: An initialized machine.I2C bus instance.
        addr: 7-bit I2C address of the ADS1115.

    Returns:
        An RTDInterface instance.
    """
    return RTDInterface(i2c, addr)