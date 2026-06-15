"""
Rubble Standard Library Objects
Implements panel, cabinet, machinery, and cable as Python objects
that the interpreter calls into.
"""

import os
import sys
import time
import socket


class RubbleError(Exception):
    """Generic runtime error from stdlib."""
    pass


# ---------------------------------------------------------------------------
# panel — user input control panel
# ---------------------------------------------------------------------------

class Panel:
    """
    panel — physical control panel for user input.
    Actions:
        panel.prompt("message")  -> text   (print message, return input line)
        panel.grab()             -> text   (read next line silently)
    """

    def prompt(self, message: str) -> str:
        """Display a message and return the user's input as text."""
        return input(str(message))

    def grab(self) -> str:
        """Read the next line of input from the keyboard silently."""
        return sys.stdin.readline().rstrip('\n')

    def __repr__(self):
        return "<panel>"


# ---------------------------------------------------------------------------
# cabinet — file system filing cabinet
# ---------------------------------------------------------------------------

class Cabinet:
    """
    cabinet — filing cabinet for the file system.
    Actions:
        cabinet.list("path")          -> crate[text]  (list file names)
        cabinet.open("path")          -> FileStream
        cabinet.create("path")        -> FileStream
    """

    def list(self, path: str):
        """Return a list of file names inside the given folder path."""
        try:
            return os.listdir(str(path))
        except FileNotFoundError:
            raise RubbleError(f"cabinet.list: path not found: {path!r}")
        except NotADirectoryError:
            raise RubbleError(f"cabinet.list: not a directory: {path!r}")

    def open(self, path: str):
        """Open an existing file for reading/writing. Returns a FileStream."""
        try:
            return FileStream(str(path), mode='r+')
        except FileNotFoundError:
            raise RubbleError(f"cabinet.open: file not found: {path!r}")

    def create(self, path: str):
        """Create a new file (or overwrite). Returns a FileStream."""
        return FileStream(str(path), mode='w')

    def __repr__(self):
        return "<cabinet>"


class FileStream:
    """A handle to an open file, returned by cabinet.open / cabinet.create."""

    def __init__(self, path: str, mode: str):
        self.path = path
        self._file = open(path, mode, encoding='utf-8')

    def read(self) -> str:
        return self._file.read()

    def write(self, data: str):
        self._file.write(str(data))

    def close(self):
        self._file.close()

    def __repr__(self):
        return f"<FileStream path={self.path!r}>"


# ---------------------------------------------------------------------------
# machinery — OS / hardware interface
# ---------------------------------------------------------------------------

class Machinery:
    """
    machinery — bare-metal OS interaction.
    Actions:
        machinery.rest(seconds)   -> empty   (pause execution)
        machinery.ram()           -> unit    (remaining memory bytes approx)
        machinery.halt()          -> (powers down / exits the program)
    """

    def rest(self, seconds):
        """Pause execution for the given number of seconds."""
        time.sleep(float(seconds))

    def ram(self) -> int:
        """Return an approximation of available system RAM in bytes."""
        try:
            import psutil
            return psutil.virtual_memory().available
        except ImportError:
            # Fallback: read from /proc/meminfo on Linux, return 0 on others
            try:
                with open('/proc/meminfo', 'r') as f:
                    for line in f:
                        if line.startswith('MemAvailable:'):
                            return int(line.split()[1]) * 1024
            except Exception:
                pass
            return 0

    def halt(self):
        """Power down — exit the program immediately."""
        sys.exit(0)

    def __repr__(self):
        return "<machinery>"


# ---------------------------------------------------------------------------
# cable — network socket library
# ---------------------------------------------------------------------------

class Cable:
    """
    cable — physical network cable.
    Actions:
        cable.connect(host, port) -> Connection
        cable.status()            -> switch (True if last connect succeeded)
    """

    def __init__(self):
        self._last_ok = False

    def connect(self, host: str, port) -> 'Connection':
        """Open a streaming TCP connection. Returns a Connection object."""
        try:
            conn = Connection(str(host), int(port))
            self._last_ok = True
            return conn
        except Exception as e:
            self._last_ok = False
            raise RubbleError(f"cable.connect: failed to connect to {host}:{port} — {e}")

    def status(self) -> bool:
        """Return True if the last connect() call succeeded."""
        return self._last_ok

    def __repr__(self):
        return "<cable>"


class Connection:
    """A live TCP connection, returned by cable.connect()."""

    def __init__(self, host: str, port: int):
        self.host = host
        self.port = port
        self._sock = socket.create_connection((host, port), timeout=10)
        self._file = self._sock.makefile('r', encoding='utf-8')

    def read(self) -> str:
        """Stream/read the next line of incoming text data."""
        line = self._file.readline()
        if not line:
            raise RubbleError("cable connection: stream closed by remote host")
        return line.rstrip('\n')

    def write(self, data: str):
        """Send text data over the connection."""
        self._sock.sendall((str(data) + '\n').encode('utf-8'))

    def close(self):
        """Close the connection."""
        self._sock.close()

    def status(self) -> bool:
        """Check if the connection socket is still open."""
        try:
            self._sock.getpeername()
            return True
        except Exception:
            return False

    def __repr__(self):
        return f"<Connection {self.host}:{self.port}>"


# ---------------------------------------------------------------------------
# Registry — maps stdlib names to singleton objects
# ---------------------------------------------------------------------------

STDLIB_REGISTRY = {
    "panel":    Panel(),
    "cabinet":  Cabinet(),
    "machinery": Machinery(),
    "cable":    Cable(),
}
