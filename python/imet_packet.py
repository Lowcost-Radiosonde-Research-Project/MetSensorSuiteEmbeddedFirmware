"""iMet-1-RSB binary telemetry packet construction.

Implements the "open" iMet binary radiosonde packet format documented
in InterMet's Appendix A - Binary Radiosonde Packet Definition, as
decoded by rs1729's imet1rsb tool (source: RS/imet/imet1rsb.c). That
decoder expects Bell 202 AFSK at 1200 baud, 8N1 framing, with a
128-bit alternating sync preamble, followed by a single 38-byte
transmission frame made up of two back-to-back packets:

    GPS Data Packet       (PKT_ID = 0x02), 18 bytes
    PTU (enhanced) Packet (PKT_ID = 0x04), 20 bytes

imet1rsb's print_frame() specifically looks for a GPS packet
immediately followed (at byte offset 18) by a PTU-enhanced packet, so
both must be present and in this order for the frame to be recognized.

Each packet is independently CRC-16 protected. The algorithm, taken
directly from imet1rsb's crc16():

    polynomial = 0x1021 (CRC-16/CCITT), initial value = 0x1D0F
    MSB-first, no input/output reflection, no final XOR
    computed over all bytes of the packet preceding its own CRC field

The CRC value is transmitted big-endian (high byte first); every other
multi-byte field (floats, altitude, pressure, temperature, humidity,
packet number) is little-endian, matching how imet1rsb reads them.

This module only builds the 38-byte frame bytes - Bell 202 AFSK
modulation and the 1200 baud 8N1 serial framing happen downstream, on
whichever Pico drives the RF transmitter.

NOTE: imet1rsb is a different (simpler, fully open) decoder from the
imet1rs_dft decoder that radiosonde_auto_rx uses for OEM iMet-4
telemetry. Matching this spec produces a frame imet1rsb can decode;
whether/how that integrates with auto_rx/SondeHub is a separate, open
question.

Author: Nathaniel Peyer
Date: 06-15-2026
"""

import struct


SOH = 0x01
PKT_ID_GPS = 0x02
PKT_ID_PTU_ENHANCED = 0x04

_CRC16_POLY = 0x1021
_CRC16_INIT = 0x1D0F

# "No data" sentinels for the scaled integer fields below.
_NO_DATA_I16 = 0x7FFF
_NO_DATA_U16 = 0xFFFF
_NO_DATA_U8 = 0xFF
_NO_DATA_U24 = 0xFFFFFF


def crc16(data):
    """Compute the iMet-1-RSB CRC-16 over a sequence of bytes.

    Args:
        data: bytes/bytearray - the packet bytes preceding its own
            CRC field.

    Returns:
        The 16-bit CRC value.
    """
    rem = _CRC16_INIT
    for byte in data:
        rem ^= (byte << 8)
        for _ in range(8):
            if rem & 0x8000:
                rem = ((rem << 1) ^ _CRC16_POLY) & 0xFFFF
            else:
                rem = (rem << 1) & 0xFFFF
    return rem


def _scaled_int16(value, scale):
    """Scale a float and clamp it to a signed 16-bit range.

    Args:
        value: Float value, or NAN if unavailable.
        scale: Multiplier applied before rounding to an integer.

    Returns:
        A signed 16-bit integer, or _NO_DATA_I16 if value is NAN.
    """
    if value != value:
        return _NO_DATA_I16
    return max(-32768, min(32767, int(round(value * scale))))


def _scaled_uint16(value, scale):
    """Scale a float and clamp it to an unsigned 16-bit range.

    Args:
        value: Float value, or NAN if unavailable.
        scale: Multiplier applied before rounding to an integer.

    Returns:
        An unsigned 16-bit integer, or _NO_DATA_U16 if value is NAN.
    """
    if value != value:
        return _NO_DATA_U16
    return max(0, min(0xFFFF, int(round(value * scale))))


def _scaled_uint8(value, scale):
    """Scale a float and clamp it to an unsigned 8-bit range.

    Args:
        value: Float value, or NAN if unavailable.
        scale: Multiplier applied before rounding to an integer.

    Returns:
        An unsigned 8-bit integer, or _NO_DATA_U8 if value is NAN.
    """
    if value != value:
        return _NO_DATA_U8
    return max(0, min(0xFF, int(round(value * scale))))


def _scaled_uint24(value, scale):
    """Scale a float and clamp it to an unsigned 24-bit range.

    Args:
        value: Float value, or NAN if unavailable.
        scale: Multiplier applied before rounding to an integer.

    Returns:
        An unsigned 24-bit integer, or _NO_DATA_U24 if value is NAN.
    """
    if value != value:
        return _NO_DATA_U24
    return max(0, min(0xFFFFFF, int(round(value * scale))))


def _encode_altitude(alt_m):
    """Encode altitude in meters as the GPS packet's (alt + 5000) field.

    Args:
        alt_m: Altitude in meters, or NAN if unavailable.

    Returns:
        Unsigned 16-bit field value (alt_m + 5000, clamped to
        0-0xFFFF), or _NO_DATA_U16 if alt_m is NAN.
    """
    if alt_m != alt_m:
        return _NO_DATA_U16
    return max(0, min(0xFFFF, int(round(alt_m)) + 5000))


def pack_gps_packet(lat_deg, lon_deg, alt_m, num_sats, hour, minute, second):
    """Pack an iMet-1-RSB GPS Data Packet (PKT_ID = 0x02).

    Args:
        lat_deg: Latitude in decimal degrees (signed float).
        lon_deg: Longitude in decimal degrees (signed float).
        alt_m: Altitude in meters. Encoded as (alt_m + 5000) in an
            unsigned 16-bit field, so the representable range is
            -5000 to 60535 m; out-of-range values are clamped.
        num_sats: Satellites used in fix, clamped to 0-255.
        hour: UTC hour of fix (0-23).
        minute: UTC minute of fix (0-59).
        second: UTC second of fix (0-59).

    Returns:
        18 bytes: the packet body plus its CRC-16.
    """
    alt_field = _encode_altitude(alt_m)

    body = struct.pack("<BBffHBBBB", SOH, PKT_ID_GPS, lat_deg, lon_deg,
                        alt_field, num_sats & 0xFF, hour, minute, second)
    return body + struct.pack(">H", crc16(body))


def pack_ptu_enhanced_packet(pkt_num, pressure_hpa, temp_c, humidity_pct,
                              vbat_v, temp_int_c, temp_probe_c, temp_u_c):
    """Pack an iMet-1-RSB PTU (enhanced) Data Packet (PKT_ID = 0x04).

    Args:
        pkt_num: Packet/frame sequence number (wraps at 65536).
        pressure_hpa: Pressure in hPa/mbar. Encoded as an unsigned
            24-bit value of (pressure_hpa * 100).
        temp_c: Primary temperature in deg C.
        humidity_pct: Relative humidity in percent.
        vbat_v: Battery voltage in volts (0-25.5 V range).
        temp_int_c: "Internal" temperature in deg C.
        temp_probe_c: "Probe" temperature in deg C.
        temp_u_c: Third auxiliary temperature in deg C.

    Returns:
        20 bytes: the packet body plus its CRC-16.
    """
    p_field = _scaled_uint24(pressure_hpa, 100)
    p_bytes = bytes([p_field & 0xFF, (p_field >> 8) & 0xFF,
                      (p_field >> 16) & 0xFF])

    body = (struct.pack("<BBH", SOH, PKT_ID_PTU_ENHANCED, pkt_num & 0xFFFF) +
            p_bytes +
            struct.pack("<hHBhhh",
                         _scaled_int16(temp_c, 100),
                         _scaled_uint16(humidity_pct, 100),
                         _scaled_uint8(vbat_v, 10),
                         _scaled_int16(temp_int_c, 100),
                         _scaled_int16(temp_probe_c, 100),
                         _scaled_int16(temp_u_c, 100)))
    return body + struct.pack(">H", crc16(body))


def pack_frame(gps_packet_kwargs, ptu_packet_kwargs):
    """Build the full 38-byte iMet-1-RSB transmission frame.

    Args:
        gps_packet_kwargs: Dict of keyword arguments for
            pack_gps_packet().
        ptu_packet_kwargs: Dict of keyword arguments for
            pack_ptu_enhanced_packet().

    Returns:
        38 bytes: the GPS Data Packet immediately followed by the PTU
        (enhanced) Data Packet, as imet1rsb's print_frame() expects.
    """
    return (pack_gps_packet(**gps_packet_kwargs) +
            pack_ptu_enhanced_packet(**ptu_packet_kwargs))