"""Framing for the UART link between the Met Pico and the RF Pico.

Each sample cycle, the Met Pico sends one 38-byte iMet-1-RSB frame
(see imet_packet.py) to the RF Pico over a dedicated UART. The RF Pico
treats this payload as opaque bytes to Bell-202-AFSK-modulate; it does
not need to parse the sensor data itself - the Met Pico has already
placed every field where imet1rsb's frame layout expects it.

A minimal frame format wraps the payload with a sync word, a length
byte, and a checksum so the RF Pico can find frame boundaries even if
it starts listening mid-stream or a byte gets dropped:

    SYNC0  SYNC1  LENGTH  <LENGTH bytes of payload>  CHECKSUM

    SYNC0, SYNC1: fixed sync bytes (0xAA, 0x55)
    LENGTH:       payload length in bytes (== packet.PACKET_SIZE)
    CHECKSUM:     sum of all payload bytes, mod 256

Author: Nathaniel Peyer
Date: 06-15-2026

TODO: if the link proves error-prone in practice, replace the additive
checksum with a CRC-16 for stronger error detection. The RF Pico's
receive-side parser needs to be kept in sync with this frame format.
"""

_SYNC0 = 0xAA
_SYNC1 = 0x55


def send_record(uart, record_bytes):
    """Frame and transmit one packet record over the link UART.

    Args:
        uart: An initialized machine.UART instance connected to the RF
            Pico.
        record_bytes: A bytes object, normally produced by
            packet.pack_record().
    """
    checksum = sum(record_bytes) & 0xFF
    frame = bytes([_SYNC0, _SYNC1, len(record_bytes)])
    frame += record_bytes
    frame += bytes([checksum])
    uart.write(frame)