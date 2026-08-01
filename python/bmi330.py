"""BMI330 6-axis IMU driver.

Register map and configuration verified against the official Bosch
BMI330 datasheet (BST-BMI330-DS000-03, April 2026).

Register addresses (all confirmed from datasheet Section 6.1):
  CHIP_ID     0x00  reset value 0x0048
  ERR_REG     0x01
  STATUS      0x02  bit 0 = por_detected (clear-on-read)
  ACC_DATA_X  0x03  \ 3x int16 little-endian, burst-readable as
  ACC_DATA_Y  0x04  | 6 bytes starting at 0x03
  ACC_DATA_Z  0x05  /
  GYR_DATA_X  0x06  \ 3x int16 little-endian, burst-readable as
  GYR_DATA_Y  0x07  | 6 bytes starting at 0x06
  GYR_DATA_Z  0x08  /
  ACC_CONF    0x20  reset value 0x0028
  GYR_CONF    0x21  reset value 0x0008

I2C addresses (datasheet Section 7.3):
  0x68 if SDO pin is pulled to GND (default)
  0x69 if SDO pin is pulled to VDDIO

After POR or soft reset, both sensors are disabled (acc_mode=0b000,
gyr_mode=0b000) and must be explicitly enabled via ACC_CONF/GYR_CONF.
Default accelerometer range after POR is 8g. Default gyroscope range
after POR is 2000 dps.

Normal mode configuration used here (from datasheet Figure 5):
  ACC_CONF = 0x4027: normal mode (0x4000) | range 8g (0x0020) |
                     ODR 50Hz (0x0007)
  GYR_CONF = 0x404B: normal mode (0x4000) | range 2000dps (0x0040) |
                     ODR 800Hz (0x000B)

Sensitivity (from datasheet Table 2 / Table 6):
  Accelerometer at 8g: 4096 LSB/g  -> scale = 1000/4096 mg/LSB
  Gyroscope at 2000dps: 16.384 LSB/dps -> scale = 1000/16.384 mdps/LSB

Note on 16-bit register reads: all BMI330 registers are 16-bit wide.
Reading 1 byte from a register address returns only the high byte
(reserved/zero for most registers). Always read 2 bytes and take
index [0] for the low byte (little-endian).

Authors: Nathaniel Peyer
Date: 06-15-2026
Last edited: 06-24-2026
"""

import struct
import time

from micropython import const


# --- Register addresses (verified against BST-BMI330-DS000-03) ---
_REG_CHIP_ID    = const(0x00)
_REG_STATUS     = const(0x02)
_REG_ACC_DATA_X = const(0x03)  # ACC X/Y/Z follow as 3x int16 LE at 0x03-0x05
_REG_GYR_DATA_X = const(0x06)  # GYR X/Y/Z follow as 3x int16 LE at 0x06-0x08
_REG_ACC_CONF   = const(0x20)
_REG_GYR_CONF   = const(0x21)

# Expected CHIP_ID value (datasheet: reset value of register 0x00 is 0x0048;
# registers are 16-bit wide, little-endian - read 2 bytes and take index [0]
# to get the low byte (0x48). Reading only 1 byte returns the high byte (0x00).
_CHIP_ID_EXPECTED = const(0x48)

# Normal mode configuration (datasheet Figure 5):
#   ACC: normal mode=0x4000, range 8g=0x0020, ODR 50Hz=0x0007
#   GYR: normal mode=0x4000, range 2000dps=0x0040, ODR 800Hz=0x000B
_ACC_CONF_VALUE = const(0x4027)
_GYR_CONF_VALUE = const(0x404B)

# Sensitivity at the configured ranges (datasheet Tables 2 and 6):
#   8g range:       4096 LSB/g     -> mg/LSB  = 1000/4096
#   2000 dps range: 16.384 LSB/dps -> mdps/LSB = 1000/16.384
_ACCEL_MG_PER_LSB  = 1000.0 / 4096.0
_GYRO_MDPS_PER_LSB = 1000.0 / 16.384

# Startup time after enabling sensors (datasheet: 2.5ms fast start).
_STARTUP_MS = const(3)


class BMI330:
    """Driver for the BMI330 IMU."""

    def __init__(self, i2c, addr):
        """Verify CHIP_ID, check init status, and configure the sensor.

        Args:
            i2c: An initialized machine.I2C bus instance.
            addr: 7-bit I2C address of the sensor (0x68 or 0x69).

        Raises:
            OSError: If the sensor does not ACK on the bus.
            ValueError: If CHIP_ID does not match the expected value.
        """
        self._i2c = i2c
        self._addr = addr

        # Registers are 16-bit wide; read 2 bytes and take index [0]
        # for the low byte. Reading only 1 byte returns the high byte
        # (reserved, always 0x00).
        chip_id = self._i2c.readfrom_mem(self._addr, _REG_CHIP_ID, 2)[0]
        if chip_id != _CHIP_ID_EXPECTED:
            raise ValueError(
                "BMI330 CHIP_ID 0x{:02X} unexpected (expected 0x{:02X})".format(
                    chip_id, _CHIP_ID_EXPECTED))

        # STATUS.por_detected (bit 0) is set after POR/soft-reset and
        # is clear-on-read. Reading it confirms the device initialized
        # cleanly. A value of 1 here is the expected post-POR state.
        status = self._i2c.readfrom_mem(self._addr, _REG_STATUS, 2)[0]
        if not (status & 0x01):
            print("[WARN] BMI330 STATUS.por_detected not set - "
                  "device may not have completed POR")

        self._configure()

    def _configure(self):
        """Write ACC_CONF and GYR_CONF to enable normal mode."""
        self._i2c.writeto_mem(self._addr, _REG_ACC_CONF,
                              struct.pack("<H", _ACC_CONF_VALUE))
        self._i2c.writeto_mem(self._addr, _REG_GYR_CONF,
                              struct.pack("<H", _GYR_CONF_VALUE))
        # Allow sensors to start up before the first read.
        time.sleep_ms(_STARTUP_MS)

    def read(self):
        """Read and convert accelerometer and gyroscope data.

        Returns:
            A tuple (accel_x_mg, accel_y_mg, accel_z_mg, gyro_x_mdps,
            gyro_y_mdps, gyro_z_mdps).

        Raises:
            OSError: If the sensor does not ACK on the bus.
        """
        accel_raw = self._i2c.readfrom_mem(self._addr, _REG_ACC_DATA_X, 6)
        gyro_raw  = self._i2c.readfrom_mem(self._addr, _REG_GYR_DATA_X, 6)

        ax, ay, az = struct.unpack("<hhh", accel_raw)
        gx, gy, gz = struct.unpack("<hhh", gyro_raw)

        return (
            ax * _ACCEL_MG_PER_LSB,  ay * _ACCEL_MG_PER_LSB,
            az * _ACCEL_MG_PER_LSB,
            gx * _GYRO_MDPS_PER_LSB, gy * _GYRO_MDPS_PER_LSB,
            gz * _GYRO_MDPS_PER_LSB,
        )


def init_bmi330(i2c, addr):
    """Create and configure a BMI330 driver instance.

    Args:
        i2c: An initialized machine.I2C bus instance.
        addr: 7-bit I2C address of the sensor (0x68 or 0x69).

    Returns:
        A BMI330 instance ready for read().

    Raises:
        OSError: If the sensor does not ACK on the bus.
        ValueError: If CHIP_ID does not match the expected value.
    """
    return BMI330(i2c, addr)