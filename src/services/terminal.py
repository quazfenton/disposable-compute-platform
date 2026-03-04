"""
Ghost-Terminal Service for Vanish Compute (VNC)
Provides low-latency, browser-based terminal sessions using our SFU architecture
"""
import asyncio
import os
import pty
import fcntl
import struct
import termios
import logging
from typing import Dict, Optional, Any
from fastapi import WebSocket

logger = logging.getLogger(__name__)

class GhostTerminal:
    """Manages a PTY session and pipes it to a WebSocket"""
    
    def __init__(self, command: str = "/bin/bash"):
        self.command = command
        self.fd = None
        self.pid = None
        self.logger = logging.getLogger(__name__)

    async def start(self, ws: WebSocket):
        """Start the terminal session and link it to the WebSocket"""
        self.pid, self.fd = pty.fork()
        
        if self.pid == 0:  # Child process
            os.environ["TERM"] = "xterm-256color"
            os.execv(self.command, [self.command])
        
        # Parent process
        logger.info(f"Ghost-Terminal started (PID: {self.pid})")
        
        # Non-blocking read
        fcntl.fcntl(self.fd, fcntl.F_SETFL, os.O_NONBLOCK)
        
        try:
            await asyncio.gather(
                self._read_from_pty(ws),
                self._write_to_pty(ws)
            )
        except Exception as e:
            logger.error(f"Ghost-Terminal session ended: {e}")
        finally:
            os.close(self.fd)
            os.waitpid(self.pid, 0)

    async def _read_from_pty(self, ws: WebSocket):
        """Read output from PTY and send to WebSocket"""
        while True:
            try:
                # Use a small sleep to avoid tight loop but keep latency low
                await asyncio.sleep(0.01)
                output = os.read(self.fd, 1024 * 4)
                if output:
                    await ws.send_bytes(output)
            except (BlockingIOError, OSError):
                continue

    async def _write_to_pty(self, ws: WebSocket):
        """Read input from WebSocket and write to PTY"""
        async for message in ws.iter_bytes():
            os.write(self.fd, message)

    def set_winsize(self, rows: int, cols: int):
        """Update the terminal window size"""
        s = struct.pack("HHHH", rows, cols, 0, 0)
        fcntl.ioctl(self.fd, termios.TIOCSWINSZ, s)

class TerminalManager:
    """Orchestrates multiple Ghost-Terminal sessions across the platform"""
    
    def __init__(self):
        self.sessions: Dict[str, GhostTerminal] = {}

    async def create_session(self, session_id: str, ws: WebSocket):
        """Create and start a new terminal session for a compute pod"""
        # In a real environment, we'd use 'docker exec -it ... bash' here
        terminal = GhostTerminal()
        self.sessions[session_id] = terminal
        await terminal.start(ws)
        del self.sessions[session_id]
