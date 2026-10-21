"""JSON booleans/floats cannot masquerade as physical face/GID identities."""
import unittest

import test_native_protocol as protocol
from rebuild import ReconstructionError


class NativeIdentityTests(unittest.TestCase):
    def setUp(self):
        self.fixture = protocol.NativeProtocolTests()

    def test_glyph_identity_requires_json_integer(self):
        for value in (True, 1.0):
            with self.subTest(value=value):
                oracle = self.fixture.oracle([self.fixture.success(value)])
                with self.assertRaisesRegex(ReconstructionError, 'native glyph'):
                    oracle.samples(0, [1], self.fixture.location)
                self.assertEqual(oracle.successful_glyph_count, 0)

    def test_face_identity_requires_json_integer(self):
        for face, value in ((0, False), (0, 0.0), (1, True), (1, 1.0)):
            with self.subTest(face=face, value=value):
                oracle = self.fixture.oracle([self.fixture.success(1, face_index=value)])
                with self.assertRaisesRegex(ReconstructionError, 'response identity mismatch'):
                    oracle.samples(face, [1], self.fixture.location)
                self.assertEqual(oracle.successful_glyph_count, 0)

    def test_boolean_is_not_an_exact_numeric_axis_echo(self):
        for expected, value in ((1., True), (0., False)):
            location = {**self.fixture.location, 'WDTH': expected}
            echo = {**location, 'WDTH': value}
            oracle = self.fixture.oracle([self.fixture.success(0, location=echo)])
            with self.assertRaisesRegex(ReconstructionError, 'axis location mismatch'):
                oracle.samples(0, [0], location)
            self.assertEqual(oracle.successful_glyph_count, 0)

    def test_integral_numeric_axis_echo_remains_valid(self):
        location = {**self.fixture.location, 'WDTH': 1.}
        oracle = self.fixture.oracle([self.fixture.success(1, location={**location, 'WDTH': 1})])
        self.assertEqual(set(oracle.samples(0, [1], location)), {1})


if __name__ == '__main__':
    unittest.main()
