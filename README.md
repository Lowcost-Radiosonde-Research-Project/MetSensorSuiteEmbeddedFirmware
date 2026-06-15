# piPicoTesting
![Raspberry Pi](https://img.shields.io/badge/Raspberry%20Pi-Pico%202-C51A4A?style=flat&logo=raspberrypi&logoColor=white)
![License](https://img.shields.io/badge/License-BSD%203--Clause-blue.svg)
![Firmware](https://img.shields.io/badge/Firmware-C%20%2B%20MicroPython-3776AB?style=flat&logo=micropython&logoColor=white)
![KiCad](https://img.shields.io/badge/Hardware-KiCad-314CB0?style=flat&logo=kicad&logoColor=white)
![Status](https://img.shields.io/badge/Status-In%20Development-orange?style=flat)

# Met Pico Sensor Suite - Firmware Skeleton

Status as of latest revision. Every module now has a real
implementation - BMI330's carries a significant caveat (see below and
its module docstring) since its register map is unverified.

## File layout

| File              | Status | Notes |
|-------------------|--------|-------|
| `config.py`       | Real   | All pins/addresses/constants in one place. Several `TODO`s remain. |
| `packet.py`       | Real   | Fixed-width binary record format (`PACKET_FORMAT = "<I15fBBBB"`, 68 bytes). |
| `bme280.py`       | Real   | Full Bosch compensation formulas, forced-mode reads. I2C bus 1. |
| `rtd_ads1115.py`  | Real   | Ratiometric RTD read + Callendar-Van Dusen (T >= 0 C only). I2C bus 1. |
| `ms5611.py`       | Real   | PROM calibration + 1st/2nd-order temp/pressure compensation. I2C bus 2. |
| `bmi330.py`       | **Unverified** | Register map guessed from the related BMI323; may not function as intended - see caveat below. I2C bus 2. |
| `gps_neo_m9n.py`  | Real   | NMEA GGA parsing: lat/lon/alt/num_sats/UTC time. |
| `sd_logger.py`    | Real   | Mounts SD, appends `packet.pack_record()` output, periodic flush. |
| `imet_packet.py`  | Real   | Builds the 38-byte iMet-1-RSB GPS+PTU-enhanced downlink frame + CRC-16. |
| `link_uart.py`    | Real   | Frames and sends one 38-byte iMet frame per cycle to the RF Pico over UART. |
| `main.py`         | Real   | Two I2C buses, SD log + iMet frame to RF Pico link, per-sensor fault isolation. |

Every sensor module exposes `init_<name>(i2c, addr)` returning an
object with a `read()` method, and `main.py` wraps each init in
`try/except (OSError, ValueError)` and each read in `try/except
OSError` (the only error read() can raise) so one bad/missing sensor
doesn't take down the loop or the log - it just logs NAN for that field
and a `[WARN]` line to the console.

## Bus layout

- **I2C bus 1** (`I2C1*`): ADS1115 (RTD) + BME280
- **I2C bus 2** (`I2C2*`): MS5611 + BMI330
- **UART** (`GPS_UART_*`): NEO-M9N GPS
- **UART** (`LINK_UART_*`): outbound link to the RF Pico, one framed
  38-byte iMet-1-RSB frame per cycle (see `imet_packet.py` /
  `link_uart.py`)
- **SPI** (`SD_*`): SD card

All pin numbers above are placeholders pending the Tuesday wiring
session - see the `TODO`s in `config.py`.

## BMI330 caveat - documentation lacking, driver may not work as intended

`bmi330.py` is written against the BMI323's register map (a related
Bosch part) because verified BMI330-specific register documentation
wasn't available when this was written. The register addresses,
ACC_CONF/GYR_CONF bitfield values, and full-scale range assumptions are
all unverified guesses. **The driver may run without raising any error
and still return meaningless numbers.**

On Tuesday, `init_bmi330()` will print whatever it reads from the
assumed CHIP_ID register (0x00) as a diagnostic - note that value down.
If accel/gyro readings look like noise, sit constant, or are far
outside physical range (accelerometer magnitude should be close to 1g
at rest), the register map guess is wrong and `bmi330.py` needs
revisiting against real BMI330 documentation (Bosch's BMI3 Sensor API
repo is the best starting point once it covers BMI330). This isn't
blocking for Wednesday - BMI330 isn't part of that test.

## Field naming convention

`packet.FIELD_NAMES` prefixes every field with the sensor that owns it
(`bme280_*`, `ms5611_*`, `rtd_*`, `bmi330_*`, `gps_*`). BMI330 fields
are in milli-g / milli-deg/s (`_mg` / `_mdps`) rather than g / deg-per-s
- worth keeping in mind when the real BMI330 driver is written, since
the conversion from raw counts will need to land in those units.

The GPS record has `gps_num_sats` plus `gps_hour`/`gps_minute`/
`gps_second` (UTC time of fix), but no fix-type field - `gps.read()`
returns a 7-tuple `(lat, lon, alt, num_sats, hour, minute, second)`.
Position/altitude are NAN and the satellite/time fields are
`NO_DATA_U8` until a checksum-valid GGA sentence with a non-zero fix
quality has been parsed. If you want fix-quality (e.g. for
SondeHub-style reporting) added too, that's a small change to
`packet.py` (one more `B` field) and `gps_neo_m9n.py`'s `_parse_gga()`.

## iMet-1-RSB downlink frame

Each cycle, after the SD record is written, `main.py` builds a
separate 38-byte frame via `imet_packet.pack_frame()` - a GPS Data
Packet (`PKT_ID=0x02`, 18 bytes) immediately followed by a PTU
(enhanced) Data Packet (`PKT_ID=0x04`, 20 bytes), each with its own
CRC-16, matching InterMet's "Appendix A - Binary Radiosonde Packet
Definition" as decoded by `imet1rsb`. This frame - not the `packet.py`
record - is what gets sent over `link_uart` to the RF Pico for AFSK
modulation; `packet.py` stays SD-only.

Current sensor -> iMet field mapping (set in `main.py`, easy to
change - it's just which `record[...]` value is passed to which
`imet_packet` keyword argument):

| iMet field | Source | Notes |
|---|---|---|
| GPS lat/lon/alt/num_sats/hour/min/sec | `gps_*` record fields | real NMEA GGA parsing; NAN/NO_DATA until a fix is acquired |
| P (pressure) | `ms5611_pressure_hpa` | **TODO**: confirm vs. BME280 as the primary pressure source |
| T (primary temp) | `bme280_temp_c` | |
| U (humidity) | `bme280_humidity_pct` | |
| Vbat | hardcoded NAN | **TODO**: no battery-voltage sensing exists yet (new ADC channel) |
| Tint (internal temp) | `bme280_temp_c` | **TODO**: currently duplicates T - confirm intent |
| Tpr (probe temp) | `rtd_temp_c` | |
| Tu (aux temp) | hardcoded NAN | **TODO**: no mapping defined - InterMet's intended use of this field is unclear |

All of the NAN/sentinel placeholders above pack safely (verified in
`imet_packet.py`'s `_scaled_*`/`_encode_altitude` helpers - they map
NAN to the field's "no data" value rather than raising), so the frame
is well-formed even with everything still stubbed.

## Before Tuesday (no hardware needed)

- [ ] Get a copy of `sdcard.py` onto the board. Easiest path in
      Thonny/REPL: `import mip; mip.install("sdcard")`. This is the
      standard MicroPython SD-over-SPI block driver - `sd_logger.py`
      imports it as `sdcard`.
- [ ] Skim `config.py` for the `TODO` items - nothing blocks you from
      reading the code now, but these are the values you'll set Tuesday.

## Tuesday, once hardware is in hand

- [ ] Update `config.py` pin numbers for both I2C buses, SPI (SD), GPS
      UART, the RF Pico link UART, and `REGULATOR_EN_PIN` (LM2596 3.3V
      rail enable) to match actual wiring.
- [ ] Confirm `RTD_MUX` / `REF_MUX` (which ADS1115 differential pair is
      the RTD vs. the reference resistor) and `ADS1115_GAIN` (PGA
      setting), based on the RTD interface board.
- [ ] Confirm `MS5611_I2C_ADDR` and `BMI330_I2C_ADDR` once those boards
      are wired. MS5611 and GPS now have real drivers, so a wrong
      address will surface as `[WARN] ... init failed` from
      `_safe_init` rather than silently logging NaN.
- [ ] For BMI330: note the `[INFO] BMI330 CHIP_ID register read as
      0x..` line at startup and sanity-check accel/gyro readings
      against the caveat above - this driver's register map is a
      guess.
- [ ] Run `main.py`. With only BME280 + RTD wired, expect `[WARN]`
      lines at startup for MS5611/BMI330/GPS init or SD mount (if not
      present) - that's expected, the loop should keep running and
      print live T/P/RH/RTD values once per second.

## Wednesday (storm chase)

The console line each cycle:

```
t=   12345ms  T= 23.45C  P=1006.32hPa  RH= 45.2%  RTD= 23.10C
```

gives a live sanity check that BME280 and RTD agree roughly with each
other and with ambient conditions. The SD card (if mounted) accumulates
`PACKET_SIZE`-byte (68-byte) binary records in `/sd/metlog.bin` - decode
with `packet.unpack_record()` in a small post-processing script, reading
`PACKET_SIZE` bytes at a time.

## Known gaps / next steps

- RTD conversion only handles T >= 0 C (Callendar-Van Dusen quadratic
  inversion). The sub-zero cubic-term inversion needs to be added before
  the actual flight.
- BMI330 is unverified - see the dedicated caveat section above and
  `bmi330.py`'s module docstring before trusting any IMU data.
- `link_uart.py` now sends a 38-byte iMet frame instead of the
  65-byte `packet.py` record - see "iMet-1-RSB downlink frame" above
  for the sensor mapping and its open TODOs (Vbat sensing, GPS UTC
  time, P/Tint/Tu assignment).
- `imet_packet.py` matches the field layout and CRC algorithm from
  `imet1rsb.c`'s source, but hasn't been cross-checked byte-for-byte
  against a compiled run of that decoder yet. Worth doing once there's
  a spare moment - compile `imet1rsb.c`, feed it a known frame, and
  confirm its `crc16()` agrees with `imet_packet.crc16()`.
- The RF Pico's receive-side parser for `link_uart`'s frame format
  (sync bytes + length + checksum) doesn't exist yet - that's firmware
  for the other board, out of scope here, but the frame format is
  documented at the top of `link_uart.py` so it can be matched.
- `main.py` currently runs everything on a single core via a simple
  fixed-interval loop. If SD writes, link UART sends, or sensor reads
  start causing timing jitter once everything is real, revisit
  splitting acquisition and logging across the two cores with
  `_thread`.