"""Bounded UTF-8 line reads for the macOS native oracle's POSIX stdout pipe."""
from __future__ import annotations

import math
import os
import selectors
import time


class TimedLineReader:
    def __init__(self, descriptor, maximum_bytes=64 * 1024 * 1024):
        if maximum_bytes <= 0:
            raise ValueError('maximum_bytes must be positive')
        self.descriptor = descriptor
        self.maximum_bytes = maximum_bytes
        self.buffer = bytearray()
        self.ended = False
        self.selector = selectors.DefaultSelector()
        self.selector.register(descriptor, selectors.EVENT_READ)

    def readline(self, timeout=30.0):
        if not math.isfinite(timeout) or timeout <= 0:
            raise ValueError('native response timeout must be finite and positive')
        deadline = time.monotonic() + timeout
        while True:
            newline = self.buffer.find(b'\n')
            if newline >= 0:
                if newline > self.maximum_bytes:
                    raise ValueError('native response line exceeds byte limit')
                data = bytes(self.buffer[:newline + 1])
                del self.buffer[:newline + 1]
                return data.decode('utf-8')
            if len(self.buffer) > self.maximum_bytes:
                raise ValueError('native response line exceeds byte limit')
            if self.ended:
                data = bytes(self.buffer)
                self.buffer.clear()
                return data.decode('utf-8')
            remaining = deadline - time.monotonic()
            if remaining <= 0 or not self.selector.select(remaining):
                raise TimeoutError('native oracle response deadline exceeded; no glyph data fabricated')
            try:
                data = os.read(self.descriptor, min(65536, self.maximum_bytes + 1))
            except InterruptedError:
                continue
            self.ended = not data
            self.buffer.extend(data)

    def close(self):
        self.selector.close()
