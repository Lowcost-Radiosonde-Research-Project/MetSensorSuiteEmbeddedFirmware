"""BMI330 6-axis IMU driver.

*** CAVEAT - READ BEFORE TRUSTING ANY OUTPUT FROM THIS DRIVER ***

The BMI330 is a recent (2024) Bosch part. At the time this driver was
written, a verified standalone BMI330 register-level reference was not
available. This driver is written against the register map and
configuration scheme of the BMI323 - a closely related part in the
same Bosch BMI3xx family, on the assumption that BMI330 keeps the same
core accelerometer/gyroscope register layout. THAT ASSUMPTION IS
UNVERIFIED.

Concretely:
  - _REG_ACC_CONF / _REG_GYR_CONF / _REG_ACC_DATA_X / _REG_GYR_DATA_X
    addresses may not be correct for BMI330.
  - _ACC_CONF_VALUE / _GYR_CONF_VALUE (ODR/range/mode bitfields) may not
    mean the same thing on BMI330, even if the register addresses
    happen to be right.
  - _ACCEL_RANGE_G / _GYRO_RANGE_DPS (used for the mg/mdps conversion)
    assume the config write above actually took effect as intended.

In short: this driver may run without raising any error and still
return meaningless numbers. On first power-up with real hardware,
__init__ prints whatever it reads from _REG_CHIP_ID purely as a
diagnostic - record that value. If accel/gyro readings look like noise,
sit at a constant value, or are wildly outside physical range (e.g.
accelerometer magnitude far from 1g at rest), the register map
assumption above is wrong and this driver needs to be revisited against
real BMI330 documentation (the Bosch BMI3 Sensor API repo is the best
starting point once it covers BMI330:
https://github.com/boschsensortec/BMI3-Sensor-API).

Authors: Nathaniel Peyer
Date: 06-15-2026

TODO: replace the register map / config below once verified BMI330
documentation is available.
"""

import struct

from micropython import const


# --- ASSUMED BMI323-family register map (see caveat above) ---
_REG_CHIP_ID = const(0x00)
_REG_ACC_CONF = const(0x20)
_REG_GYR_CONF = const(0x21)
_REG_ACC_DATA_X = const(0x03)  # X, Y, Z follow as 3x int16, little-endian
_REG_GYR_DATA_X = const(0x09)  # X, Y, Z follow as 3x int16, little-endian

# ACC_CONF / GYR_CONF: intended to select ODR ~100Hz, normal/continuous
# mode, range = +/-2g (accel) and +/-2000dps (gyro). Bitfield layout is
# assumed, not verified - see module caveat.
_ACC_CONF_VALUE = const(0x4027)
_GYR_CONF_VALUE = const(0x40C7)

# Full-scale ranges corresponding to the config values above. If the
# config write didn't do what's intended, these will be wrong too.
_ACCEL_RANGE_G = 2
_GYRO_RANGE_DPS = 2000

_INT16_FULL_SCALE = 32768.0


class BMI330:
    """Driver for the BMI330 IMU (see module docstring caveats)."""

    def __init__(self, i2c, addr):
        """Read CHIP_ID (diagnostic only) and configure the sensor.

        Args:
            i2c: An initialized machine.I2C bus instance.
            addr: 7-bit I2C address of the sensor.

        Raises:
            OSError: If the sensor does not respond on the bus.
        """
        self.i2c = i2c
        self.addr = addr

        chip_id = self.i2c.readfrom_mem(self.addr, _REG_CHIP_ID, 1)[0]
        print("[INFO] BMI330 CHIP_ID register read as 0x{:02X} "
              "(diagnostic only - see bmi330.py module "
              "docstring)".format(chip_id))

        self._configure()

    def _configure(self):
        """Write the assumed ACC_CONF/GYR_CONF registers."""
        self.i2c.writeto_mem(self.addr, _REG_ACC_CONF,
                              struct.pack("<H", _ACC_CONF_VALUE))
        self.i2c.writeto_mem(self.addr, _REG_GYR_CONF,
                              struct.pack("<H", _GYR_CONF_VALUE))

    def read(self):
        """Read and convert accelerometer and gyroscope data.

        Returns:
            A tuple (accel_x_mg, accel_y_mg, accel_z_mg, gyro_x_mdps,
            gyro_y_mdps, gyro_z_mdps).

        Raises:
            OSError: If the sensor does not respond on the bus.
        """
        accel_raw = self.i2c.readfrom_mem(self.addr, _REG_ACC_DATA_X, 6)
        gyro_raw = self.i2c.readfrom_mem(self.addr, _REG_GYR_DATA_X, 6)

        ax, ay, az = struct.unpack("<hhh", accel_raw)
        gx, gy, gz = struct.unpack("<hhh", gyro_raw)

        accel_scale = (_ACCEL_RANGE_G * 1000) / _INT16_FULL_SCALE
        gyro_scale = (_GYRO_RANGE_DPS * 1000) / _INT16_FULL_SCALE

        return (ax * accel_scale, ay * accel_scale, az * accel_scale,
                gx * gyro_scale, gy * gyro_scale, gz * gyro_scale)


def init_bmi330(i2c, addr):
    """Create and configure a BMI330 driver instance.

    Args:
        i2c: An initialized machine.I2C bus instance.
        addr: 7-bit I2C address of the sensor.

    Returns:
        A BMI330 instance ready for read().

    Raises:
        OSError: If the sensor does not respond on the bus.
    """
    return BMI330(i2c, addr)