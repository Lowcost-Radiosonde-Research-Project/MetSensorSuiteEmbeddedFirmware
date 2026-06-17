"""Hardware configuration constants for the Met Pico sensor suite.

Centralizes pin assignments, bus addresses, ADC channel mappings, and
calibration constants so that hardware changes only require edits in
this file. Values marked TODO are placeholders pending hardware
confirmation and must be updated before flight.

Author: Nathaniel Peyer
Date: 06-16-2026
"""

# I2C bus 1: ADS1115 (RTD interface) and BME280.
I2C1 = 1
I2C1_SDA_PIN = 11
I2C1_SCL_PIN = 10
I2C1_FREQ_HZ = 100000

# I2C bus 2: MS5611 and BMI330.
# TODO: confirm BMI330 is on I2C (vs SPI) once hardware is finalized -
# this assumes both remaining I2C sensors share the second bus.
I2C2 = 1
I2C2_SDA_PIN = 2
I2C2_SCL_PIN = 3
I2C2_FREQ_HZ = 400000

# BME280 (temperature / pressure / humidity).
BME280_I2C_ADDR = 0x77

# MS5611 (high-resolution pressure / temperature).
# TODO: confirm address (0x77 if CSB tied high, 0x76 if tied low).
MS5611_I2C_ADDR = 0x77

# BMI330 (6-axis IMU).
# TODO: confirm address and bus once hardware is finalized.
BMI330_I2C_ADDR = 0x68

# ADS1115 (4-wire PT1000 RTD interface).
ADS1115_I2C_ADDR = 0x48

# ADS1115 MUX[2:0] codes (config register bits 14:12) select which
# differential pair is measured. The ADS1115 only supports four
# differential combinations:
#   0b000 -> AIN0 - AIN1
#   0b001 -> AIN0 - AIN3
#   0b010 -> AIN1 - AIN3
#   0b011 -> AIN2 - AIN3
# TODO: confirm which pair carries the RTD sense voltage and which
# carries the reference resistor once the RTD interface board wiring
# is finalized.
# AIN1 - AIN3 differential: high-side tap (between ref resistor and RTD)
# to low-side tap (between RTD and GND).
RTD_MUX = 0b010

# Excitation voltage in volts (3.3V regulated buck converter output).
# Used in voltage-divider resistance calculation since only one
# differential pair is available (no separate ref resistor tap).
RTD_EXCITATION_V = 3.3

# ADS1115 full-scale voltage for GAIN=1 (+-4.096V). One LSB = 0.125mV.
ADS1115_FSV = 4.096

# ADS1115 PGA[2:0] code (config register bits 11:9) sets the full-scale
# input range:
#   0 -> +/-6.144V   1 -> +/-4.096V   2 -> +/-2.048V
#   3 -> +/-1.024V   4 -> +/-0.512V   5 -> +/-0.256V
# TODO: confirm once excitation current and the expected voltage range
# across the RTD and reference resistor are known.
ADS1115_GAIN = 1

RTD_REF_RESISTANCE_OHMS = 10000.0

# Callendar-Van Dusen coefficients for PT1000 (IEC 60751).
RTD_R0_OHMS = 1000.0
RTD_CVD_A = 3.9083e-3
RTD_CVD_B = -5.775e-7
# Cubic term, only used for T < 0 deg C (see rtd_ads1115.py).
RTD_CVD_C = -4.183e-12

# Newton-Raphson iterations for the sub-zero CVD inversion. The
# quadratic (T >= 0) estimate used as the starting guess is already
# close, so this converges to well under 0.001 deg C within 2-3
# iterations; 5 leaves comfortable margin.
RTD_SUBZERO_ITERATIONS = 5

# NEO-M9N GPS (UART, NMEA 0183).
GPS_UART_ID = 1
GPS_UART_TX_PIN = 4
GPS_UART_RX_PIN = 5
GPS_UART_BAUD_RATE = 9600

# UART link to the RF Pico - one 38-byte iMet-1-RSB frame (see
# imet_packet.py), framed by link_uart.send_record(), is sent each
# sample cycle for the RF Pico to AFSK-modulate.
# TODO: confirm pins and baud rate once the inter-Pico wiring is set.
LINK_UART_ID = 0
LINK_UART_TX_PIN = 12
LINK_UART_RX_PIN = 13
LINK_UART_BAUD_RATE = 115200

# SD card (SPI).
SD_SPI_ID = 0
SD_SCK_PIN = 18
SD_MOSI_PIN = 19
SD_MISO_PIN = 16
SD_CS_PIN = 17
SD_MOUNT_POINT = "/sd"
SD_LOG_FILENAME = "/sd/metlog.bin"

# LM2596 switching regulator that supplies the 3.3V sensor rail. This
# GPIO must be driven high before any I2C/UART sensor transaction will
# succeed - main() asserts it first thing, then waits
# REGULATOR_ENABLE_DELAY_MS for the rail to settle.
# TODO: confirm pin number once wiring is finalized.
REGULATOR_EN_PIN = 14
REGULATOR_ENABLE_DELAY_MS = 50

# Sampling and logging cadence.
SAMPLE_INTERVAL_MS = 1000
SD_FLUSH_INTERVAL_SAMPLES = 5