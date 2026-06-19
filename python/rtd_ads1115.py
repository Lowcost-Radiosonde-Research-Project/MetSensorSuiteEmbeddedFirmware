"""4-wire PT1000 RTD interface via ADS1115 differential ADC.

The RTD is measured ratiometrically against a known reference resistor:
both the RTD and the reference resistor are driven by the same
excitation current, so the ratio of their ADC readings cancels out the
excitation current's absolute accuracy and the ADC's LSB size. Only the
known reference resistance is needed to compute the RTD resistance.

RTD resistance is converted to temperature using the Callendar-Van
Dusen equation for PT1000. For T >= 0 deg C this inverts to a
closed-form quadratic; for T < 0 deg C a cubic term is added and the
result is refined via Newton-Raphson (see _refine_subzero()).

Author: Nathaniel Peyer
Date: 06-16-2026
"""

import struct
import time

from micropython import const

import config


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
        """Measure the RTD resistance via voltage divider calculation.

        The circuit is a simple voltage divider:
            V_exc -> R_ref -> [A1 tap] -> RTD -> [A3 tap] -> GND

        Only one differential pair (AIN1-AIN3) is available, measuring
        V_rtd directly. R_rtd is derived from the voltage divider:

            R_rtd = R_ref * V_rtd / (V_exc - V_rtd)

        Returns:
            RTD resistance in ohms, or NAN if V_rtd >= V_exc (would
            produce a non-physical result).

        Raises:
            OSError: If the ADS1115 does not respond on the bus.
        """
        adc_raw = self._read_differential(config.RTD_MUX)

        # Convert raw ADC count to volts. GAIN=1 -> FSV=4.096V,
        # 16-bit signed -> 32768 counts full scale.
        # abs() corrects for swapped A1/A3 wires (hardware fixed).
        v_rtd = abs(adc_raw) * (config.ADS1115_FSV / 32768.0)

        v_exc = config.RTD_EXCITATION_V

        if v_rtd <= 0.0 or v_rtd >= v_exc:
            return float("nan")

        return config.RTD_REF_RESISTANCE_OHMS * v_rtd / (v_exc - v_rtd)

    def read_temperature_c(self):
        """Measure RTD resistance and convert to temperature.

        Uses the Callendar-Van Dusen equation for PT1000. For
        T >= 0 deg C:

            R(T) = R0 * (1 + A*T + B*T^2)

        which inverts to a closed-form quadratic and is exact. That
        quadratic result is used directly when it comes out >= 0, and
        as the starting guess for _refine_subzero() when it comes out
        < 0 (the full equation below 0 deg C adds a cubic term with no
        closed-form inverse).

        Returns:
            Temperature in degrees Celsius, or NAN if the resistance
            reading itself is NAN.

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
        if discriminant < 0.0:
            return float("nan")
        # ** 0.5 is the sqrt.
        temperature_c = (-a + discriminant ** 0.5) / (2.0 * b)

        if temperature_c < 0.0:
            temperature_c = self._refine_subzero(resistance, temperature_c)

        return temperature_c

    def _refine_subzero(self, resistance, initial_guess):
        """Refine a sub-zero temperature estimate via Newton-Raphson.

        For T < 0 deg C, the Callendar-Van Dusen equation gains a cubic
        term that has no closed-form inverse:

            R(T) = R0 * (1 + A*T + B*T^2 + C*(T - 100)*T^3)

        This runs config.RTD_SUBZERO_ITERATIONS of Newton-Raphson on
        that full equation, starting from initial_guess (the T >= 0
        quadratic-formula estimate, which is already close near the
        T=0 boundary - e.g. it lands within ~0.04 deg C of the true
        value at -50 deg C).

        Args:
            resistance: Measured RTD resistance in ohms.
            initial_guess: Starting temperature estimate in deg C.

        Returns:
            Refined temperature in degrees Celsius.
        """
        r0 = config.RTD_R0_OHMS
        a = config.RTD_CVD_A
        b = config.RTD_CVD_B
        c = config.RTD_CVD_C

        temperature_c = initial_guess
        for _ in range(config.RTD_SUBZERO_ITERATIONS):
            t = temperature_c
            r_model = r0 * (1.0 + a * t + b * t * t +
                             c * (t - 100.0) * t ** 3)
            r_model_prime = r0 * (a + 2.0 * b * t +
                                   c * (4.0 * t ** 3 - 300.0 * t * t))
            temperature_c = t - (r_model - resistance) / r_model_prime

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