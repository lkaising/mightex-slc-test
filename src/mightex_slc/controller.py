"""
Mightex SLC LED Controller Interface
Clean Python API for controlling Mightex Sirius LED drivers via RS232
"""

import serial
import time
from typing import Optional
from dataclasses import dataclass


@dataclass
class DeviceInfo:
    """Device information returned from DEVICEINFO command"""

    firmware_version: str
    module_number: str
    serial_number: str

    @classmethod
    def from_response(cls, response: str):
        """Parse DEVICEINFO response"""
        firmware = "Unknown"
        module = "Unknown"
        serial = "Unknown"

        if "Driver:" in response:
            firmware = response.split("Driver:")[1].split()[0]

        if "Module No.:" in response:
            module = response.split("Module No.:")[1].split()[0]

        if "Serial No.:" in response:
            serial = response.split("Serial No.:")[1].split()[0]

        return cls(firmware, module, serial)


class MightexSLC:
    """Interface for Mightex SLC LED Controller via RS232"""

    # Operating modes
    MODE_DISABLE = 0
    MODE_NORMAL = 1
    MODE_STROBE = 2
    MODE_TRIGGER = 3

    def __init__(self, port: str = "/dev/ttyUSB0", baud: int = 9600, timeout: float = 1.0):
        """
        Initialize connection to Mightex SLC controller

        Args:
            port: Serial port path
            baud: Baud rate (default 9600)
            timeout: Serial timeout in seconds
        """
        self.port = port
        self.baud = baud
        self.timeout = timeout
        self._ser: Optional[serial.Serial] = None

    def __enter__(self):
        """Context manager entry"""
        self.connect()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit"""
        self.disconnect()

    def connect(self) -> None:
        """Open serial connection and disable echo"""
        self._ser = serial.Serial(
            port=self.port,
            baudrate=self.baud,
            bytesize=serial.EIGHTBITS,
            parity=serial.PARITY_NONE,
            stopbits=serial.STOPBITS_ONE,
            timeout=self.timeout,
        )
        # Disable echo for programmatic control
        self._send_command("ECHOOFF")

    def disconnect(self) -> None:
        """Close serial connection"""
        if self._ser and self._ser.is_open:
            self._ser.close()

    def _send_command(self, cmd: str, delay: float = 0.1) -> str:
        """
        Send command to controller and return response

        Args:
            cmd: Command string (without LF+CR)
            delay: Delay after sending before reading response

        Returns:
            Response string with whitespace stripped
        """
        if not self._ser or not self._ser.is_open:
            raise RuntimeError("Serial port not open. Call connect() first.")

        full_cmd = cmd + "\n\r"
        self._ser.write(full_cmd.encode("ascii"))
        time.sleep(delay)
        response = self._ser.read_all().decode("ascii", errors="replace")
        return response.strip()

    def get_device_info(self) -> DeviceInfo:
        """Get device information (model, firmware, serial number)"""
        response = self._send_command("DEVICEINFO")
        return DeviceInfo.from_response(response)

    def get_mode(self, channel: int) -> int:
        """
        Get current operating mode of a channel

        Args:
            channel: Channel number (1-based)

        Returns:
            Mode number (0=DISABLE, 1=NORMAL, 2=STROBE, 3=TRIGGER)
        """
        response = self._send_command(f"?MODE {channel}")
        # Response format: #mode<CR><LF>
        mode_str = response.replace("#", "").strip()
        return int(mode_str)

    def set_mode(self, channel: int, mode: int) -> bool:
        """
        Set operating mode of a channel

        Args:
            channel: Channel number (1-based)
            mode: Mode number (0=DISABLE, 1=NORMAL, 2=STROBE, 3=TRIGGER)

        Returns:
            True if successful
        """
        response = self._send_command(f"MODE {channel} {mode}")
        return "##" in response

    def set_normal_mode(self, channel: int, max_current_ma: int, set_current_ma: int) -> bool:
        """
        Set normal mode parameters for a channel

        Args:
            channel: Channel number (1-based)
            max_current_ma: Maximum allowed current in mA
            set_current_ma: Working current in mA

        Returns:
            True if successful
        """
        response = self._send_command(f"NORMAL {channel} {max_current_ma} {set_current_ma}")
        return "##" in response

    def set_current(self, channel: int, current_ma: int) -> bool:
        """
        Quick set current in NORMAL mode (must already be in NORMAL mode)

        Args:
            channel: Channel number (1-based)
            current_ma: Current in mA

        Returns:
            True if successful
        """
        response = self._send_command(f"CURRENT {channel} {current_ma}")
        return "##" in response

    def get_normal_params(self, channel: int) -> tuple[int, int]:
        """
        Get normal mode parameters for a channel

        Args:
            channel: Channel number (1-based)

        Returns:
            Tuple of (max_current_ma, set_current_ma)
        """
        response = self._send_command(f"?CURRENT {channel}")
        # Response format: #Cal1 Cal2 Imax Iset ... (ignore calibration values)
        parts = response.replace("#", "").split()
        if len(parts) >= 2:
            return int(parts[-2]), int(parts[-1])
        return 0, 0

    def enable_channel(
        self, channel: int, current_ma: int, max_current_ma: Optional[int] = None
    ) -> bool:
        """
        Convenience method: Enable a channel in NORMAL mode with specified current

        Args:
            channel: Channel number (1-based)
            current_ma: Working current in mA
            max_current_ma: Maximum current (defaults to 2x set current if not specified)

        Returns:
            True if successful
        """
        if max_current_ma is None:
            max_current_ma = current_ma * 2

        # Set parameters
        if not self.set_normal_mode(channel, max_current_ma, current_ma):
            return False

        # Enable channel
        return self.set_mode(channel, self.MODE_NORMAL)

    def disable_channel(self, channel: int) -> bool:
        """
        Disable a channel (turn off LED)

        Args:
            channel: Channel number (1-based)

        Returns:
            True if successful
        """
        return self.set_mode(channel, self.MODE_DISABLE)

    def store_settings(self) -> bool:
        """
        Store current settings to non-volatile memory

        Returns:
            True if successful
        """
        response = self._send_command("STORE")
        return "##" in response

    def reset(self) -> bool:
        """
        Soft reset the device

        Returns:
            True if successful
        """
        response = self._send_command("RESET")
        return "##" in response


# Convenience function
def get_controller(port: str = "/dev/ttyUSB0") -> MightexSLC:
    """Get a connected controller instance (use with context manager)"""
    return MightexSLC(port)
