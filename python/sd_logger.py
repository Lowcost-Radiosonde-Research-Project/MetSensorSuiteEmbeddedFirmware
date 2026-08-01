"""SD card logging for Met Pico sensor records.

Uses the standard MicroPython "sdcard" driver (see README.md for how to
get a copy onto the board) to mount an SPI SD card as a FAT filesystem,
then appends fixed-width binary records produced by packet.pack_record().

A new log file is created on every boot, named metlog_NNN.bin where NNN
is the lowest three-digit index not already present on the card. This
ensures each power cycle produces a distinct file and no data is
overwritten across flights.

The log file is opened once in append-binary mode and kept open for the
duration of the flight; flush() is called periodically (rather than
close()+reopen() every cycle) so a power loss only risks losing the
last partial batch of samples, not the whole file.

Author: Nathaniel Peyer
Date: 06-15-2026
"""

import os
import time
import sdcard
from machine import SPI, Pin

import config


def _reset_sd_spi(spi: SPI, cs: Pin) -> None:
    """Clock out the SD card SPI state machine after a dirty shutdown.

    Drives CS high and sends 10 dummy 0xFF bytes to force the card back
    to idle. Must be called before constructing the SDCard driver,
    especially after a KeyboardInterrupt or power loss mid-write.

    Args:
        spi: The SPI bus the SD card is on.
        cs:  The chip-select pin for the SD card (active-low).
    """
    cs.value(1)
    spi.write(bytes([0xFF] * 10))
    time.sleep_ms(10)


def _next_log_filename(mount_point: str) -> str:
    """Return the next available metlog_NNN.bin filename.

    Scans the root of the mounted SD card for files matching the
    metlog_NNN.bin pattern and returns the path with the lowest unused
    three-digit index.

    Args:
        mount_point: Filesystem path where the SD card is mounted
                     (e.g. "/sd").

    Returns:
        Full path string, e.g. "/sd/metlog_003.bin".

    Raises:
        OSError: If 1000 log files already exist (indices 000-999 full).
    """
    existing = set(os.listdir(mount_point))
    for i in range(1000):
        name = "metlog_{:03d}.bin".format(i)
        if name not in existing:
            return "{}/{}".format(mount_point, name)
    raise OSError("SD card log directory full: all metlog_000-999 taken")


class SDLogger:
    """Appends fixed-width binary sensor records to a file on an SD card."""

    def __init__(self):
        """Mount the SD card and open a new log file for this boot.

        Performs an SPI bus reset before initializing the SD card driver
        to recover cleanly from any previous dirty shutdown or interrupted
        write.

        Raises:
            OSError: If the SD card cannot be initialized, mounted, or
                     if no log filename slot is available.
        """
        spi = SPI(
            config.SD_SPI_ID,
            sck=Pin(config.SD_SCK_PIN),
            mosi=Pin(config.SD_MOSI_PIN),
            miso=Pin(config.SD_MISO_PIN),
        )
        cs = Pin(config.SD_CS_PIN, Pin.OUT)

        _reset_sd_spi(spi, cs)

        self._sd = sdcard.SDCard(spi, cs)
        os.mount(self._sd, config.SD_MOUNT_POINT)

        self._log_path = _next_log_filename(config.SD_MOUNT_POINT)
        self._file = open(self._log_path, "wb")
        self._samples_since_flush = 0

        print("[SD] Logging to", self._log_path)

    @property
    def log_path(self) -> str:
        """Full path of the log file opened for this session."""
        return self._log_path

    def write_record(self, record_bytes: bytes) -> None:
        """Append one fixed-width record and flush periodically.

        Args:
            record_bytes: A bytes object, normally produced by
                packet.pack_record().

        Raises:
            OSError: If the write to the SD card fails.
            MemoryError: If the SD card returns corrupt data causing an
                         oversized buffer allocation; caller should
                         attempt re-init.
        """
        self._file.write(record_bytes)
        self._samples_since_flush += 1
        if self._samples_since_flush >= config.SD_FLUSH_INTERVAL_SAMPLES:
            self._file.flush()
            self._samples_since_flush = 0

    def close(self) -> None:
        """Flush and close the log file, then unmount the SD card."""
        self._file.flush()
        self._file.close()
        os.umount(config.SD_MOUNT_POINT)


def init_sd_logger() -> SDLogger:
    """Create an SDLogger instance.

    Returns:
        An SDLogger with a new boot-specific log file open and ready
        for write_record().

    Raises:
        OSError: If the SD card cannot be initialized or mounted.
    """
    return SDLogger()