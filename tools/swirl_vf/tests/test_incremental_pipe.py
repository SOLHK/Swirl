"""Original pipe protocol cases, independent of any font or native renderer."""
import os
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'tools'))
from incremental_pipe import TimedLineReader


@unittest.skipIf(os.name == 'nt', 'CoreText oracle transport is a POSIX-only process')
class IncrementalPipeTests(unittest.TestCase):
    def setUp(self):
        self.read_fd, self.write_fd = os.pipe()
        self.addCleanup(os.close, self.read_fd)
        self.addCleanup(self.close_writer)
        self.reader = TimedLineReader(self.read_fd, maximum_bytes=16)
        self.addCleanup(self.reader.close)

    def close_writer(self):
        if self.write_fd is not None:
            os.close(self.write_fd)
            self.write_fd = None

    def test_response_before_eof_and_next_request(self):
        os.write(self.write_fd, b'one\n')
        self.assertEqual(self.reader.readline(.2), 'one\n')
        os.write(self.write_fd, b'two\nthree\n')
        self.assertEqual(self.reader.readline(.2), 'two\n')
        self.assertEqual(self.reader.readline(.2), 'three\n')

    def test_timeout_does_not_drop_partial_utf8(self):
        os.write(self.write_fd, b'\xe4\xb8')
        with self.assertRaises(TimeoutError):
            self.reader.readline(.02)
        os.write(self.write_fd, b'\xad\n')
        self.assertEqual(self.reader.readline(.2), '\u4e2d\n')

    def test_last_unterminated_line_at_eof(self):
        os.write(self.write_fd, b'tail')
        self.close_writer()
        self.assertEqual(self.reader.readline(.2), 'tail')
        self.assertEqual(self.reader.readline(.2), '')

    def test_overlong_response_is_rejected(self):
        os.write(self.write_fd, b'x' * 17)
        with self.assertRaisesRegex(ValueError, 'byte limit'):
            self.reader.readline(.2)

    def test_invalid_utf8_is_not_replaced(self):
        os.write(self.write_fd, b'\xff\n')
        with self.assertRaises(UnicodeDecodeError):
            self.reader.readline(.2)

    def test_empty_line_is_distinct_from_eof(self):
        os.write(self.write_fd, b'\n')
        self.assertEqual(self.reader.readline(.2), '\n')
        with self.assertRaises(TimeoutError):
            self.reader.readline(.02)

    def test_invalid_deadline_is_rejected(self):
        for value in (0, -1, float('nan'), float('inf')):
            with self.assertRaises(ValueError):
                self.reader.readline(value)


if __name__ == '__main__':
    unittest.main()
