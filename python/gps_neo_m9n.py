"""NEO-M9N GPS receiver driver.

Reads NMEA 0183 sentences from a UART (default 9600 baud) and parses
GGA sentences for position, altitude, satellite count, and UTC time.
read() returns the most recently parsed values; if no valid GGA
sentence has been seen yet (or ever), the position/altitude fields are
NAN and the satellite count and time fields are NO_DATA_U8.

Only GGA is parsed. GGA reports time and satellite count even without
a fix (fix quality 0); position and altitude are only updated when the
fix quality field is non-zero and the corresponding fields are present.

Author: Nathaniel Peyer
Date: 06-15-2026
Last edited: 06-24-2026
"""

from packet import NAN, NO_DATA_U8


_MAX_BUFFER_LEN = 256


def _checksum_ok(body, checksum_str):
    """Validate an NMEA sentence's checksum.

    Args:
        body: Sentence contents between '$' and '*' (exclusive).
        checksum_str: Two hex digits following '*'.

    Returns:
        True if the XOR of all characters in body matches checksum_str.
    """
    try:
        expected = int(checksum_str, 16)
    except ValueError:
        return False

    actual = 0
    for ch in body:
        actual ^= ord(ch)
    return actual == expected


def _nmea_to_decimal_degrees(value_str, direction):
    """Convert an NMEA ddmm.mmmm / dddmm.mmmm field to decimal degrees.

    Args:
        value_str: Latitude or longitude field, e.g. "4916.45" for 49
            degrees 16.45 minutes.
        direction: 'N'/'S' for latitude, 'E'/'W' for longitude.

    Returns:
        Signed decimal degrees (negative for S/W).
    """
    value = float(value_str)
    degrees = int(value / 100)
    minutes = value - degrees * 100
    decimal = degrees + minutes / 60.0
    if direction in ("S", "W"):
        decimal = -decimal
    return decimal


class GPSReceiver:
    """Driver for the NEO-M9N GPS receiver (NMEA GGA parsing)."""

    def __init__(self, uart):
        """Store the UART instance and initialize "no data" state.

        Args:
            uart: An initialized machine.UART instance, or None if the
                GPS UART has not been configured.
        """
        self.uart = uart
        self._buffer = ""
        self._lat_deg = NAN
        self._lon_deg = NAN
        self._alt_m = NAN
        self._num_sats = NO_DATA_U8
        self._hour = NO_DATA_U8
        self._minute = NO_DATA_U8
        self._second = NO_DATA_U8

    def read(self):
        """Process any buffered NMEA sentences and return current state.

        Returns:
            A tuple (lat_deg, lon_deg, alt_m, num_sats, hour, minute,
            second). Position/altitude fields are NAN and the
            satellite/time fields are NO_DATA_U8 until a valid GGA
            sentence has been parsed.

        Raises:
            OSError: If reading from the UART fails.
        """
        for sentence in self._read_sentences():
            self._parse_sentence(sentence)

        return (self._lat_deg, self._lon_deg, self._alt_m,
                self._num_sats, self._hour, self._minute, self._second)

    def _read_sentences(self):
        """Read available UART bytes and split off complete NMEA lines.

        Returns:
            A list of complete sentence strings (without line
            terminators). Empty if no UART is configured or no
            complete sentence is available yet.
        """
        if self.uart is None:
            return []

        data = self.uart.read()
        if data:
            try:
                self._buffer += data.decode("ascii")
            except UnicodeError:
                # Corrupted/binary data on the line - drop the buffer
                # and resync on the next '$'.
                self._buffer = ""

        sentences = []
        while "\n" in self._buffer:
            line, self._buffer = self._buffer.split("\n", 1)
            line = line.strip("\r\n ")
            if line:
                sentences.append(line)

        # Guard against unbounded growth if '\n' never arrives.
        if len(self._buffer) > _MAX_BUFFER_LEN:
            self._buffer = ""

        return sentences

    def _parse_sentence(self, sentence):
        """Validate and dispatch one NMEA sentence.

        Args:
            sentence: Full sentence including leading '$' and trailing
                "*hh" checksum, without line terminators.
        """
        if not sentence.startswith("$") or "*" not in sentence:
            return

        body, _, checksum_str = sentence[1:].partition("*")
        if not _checksum_ok(body, checksum_str):
            return

        fields = body.split(",")
        # fields[0] is the talker+sentence ID, e.g. "GNGGA" or "GPGGA".
        if len(fields) < 10 or fields[0][2:5] != "GGA":
            return

        self._parse_gga(fields)

    def _parse_gga(self, fields):
        """Update state from a checksum-valid GGA sentence's fields.

        Args:
            fields: GGA sentence fields, split on ',', with the
                leading '$' and trailing checksum already removed.
        """
        time_str = fields[1]
        if len(time_str) >= 6:
            try:
                self._hour = int(time_str[0:2])
                self._minute = int(time_str[2:4])
                self._second = int(time_str[4:6])
            except ValueError:
                pass

        try:
            self._num_sats = int(fields[7])
        except ValueError:
            pass

        fix_quality = fields[6]
        lat_str, lat_dir = fields[2], fields[3]
        lon_str, lon_dir = fields[4], fields[5]
        alt_str = fields[9]

        if fix_quality != "0" and lat_str and lon_str:
            try:
                self._lat_deg = _nmea_to_decimal_degrees(lat_str, lat_dir)
                self._lon_deg = _nmea_to_decimal_degrees(lon_str, lon_dir)
            except ValueError:
                return

            if alt_str:
                try:
                    self._alt_m = float(alt_str)
                except ValueError:
                    pass


def init_gps(uart):
    """Create a GPSReceiver driver instance.

    Args:
        uart: An initialized machine.UART instance, or None.

    Returns:
        A GPSReceiver instance.
    """
    return GPSReceiver(uart)