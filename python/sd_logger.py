"""SD card logging for Met Pico sensor records.

Uses the standard MicroPython "sdcard" driver (see README.md for how to
get a copy onto the board) to mount an SPI SD card as a FAT filesystem,
then appends fixed-width binary records produced by
packet.pack_record().

The log file is opened once in append-binary mode and kept open for the
duration of the flight; flush() is called periodically (rather than
close()+reopen() every cycle) so a power loss only risks losing the
last partial batch of samples, not the whole file.

Author: Nathaniel Peyer
Date: 06-15-2026
"""

import os

import sdcard
from machine import SPI, Pin

import config


class SDLogger:
    """Appends fixed-width binary sensor records to a file on an SD card."""

    def __init__(self):
        """Mount the SD card and open the log file for appending.

        Raises:
            OSError: If the SD card cannot be initialized or mounted.
        """
        spi = SPI(config.SD_SPI_ID,
                  sck=Pin(config.SD_SCK_PIN),
                  mosi=Pin(config.SD_MOSI_PIN),
                  miso=Pin(config.SD_MISO_PIN))
        cs = Pin(config.SD_CS_PIN, Pin.OUT)

        self._sd = sdcard.SDCard(spi, cs)
        os.mount(self._sd, config.SD_MOUNT_POINT)

        self._file = open(config.SD_LOG_FILENAME, "ab")
        self._samples_since_flush = 0

    def write_record(self, record_bytes):
        """Append one fixed-width record and flush periodically.

        Args:
            record_bytes: A bytes object, normally produced by
                packet.pack_record().

        Raises:
            OSError: If the write to the SD card fails.
        """
        self._file.write(record_bytes)
        self._samples_since_flush += 1

        if self._samples_since_flush >= config.SD_FLUSH_INTERVAL_SAMPLES:
            self._file.flush()
            self._samples_since_flush = 0

    def close(self):
        """Flush and close the log file, then unmount the SD card."""
        self._file.flush()
        self._file.close()
        os.umount(config.SD_MOUNT_POINT)


def init_sd_logger():
    """Create an SDLogger instance.

    Returns:
        An SDLogger instance with the log file open and ready for
        write_record().

    Raises:
        OSError: If the SD card cannot be initialized or mounted.
    """
    return SDLogger()