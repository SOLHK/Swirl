"""Regress the actual early timed-wait result without changing REALITY bounds."""
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

import test_reality_runtime as reality


class AuthenticatedHelloHoldTests(unittest.TestCase):
    def run_hold(self, observations, *, already_released=False, waits=None, states=None):
        release = Mock()
        release.is_set.return_value = already_released
        if states is not None:
            release.is_set.side_effect = states
        release.wait.return_value = False
        if waits is not None:
            release.wait.side_effect = waits
        clock = Mock(side_effect=observations)
        with patch.object(reality, "time", SimpleNamespace(monotonic=clock)):
            elapsed = reality.hold_authenticated_hello(release)
        return elapsed, release

    def test_full_hold_reports_actual_monotonic_elapsed(self):
        elapsed, release = self.run_hold([100.0, 100.0, 103.251])
        self.assertAlmostEqual(elapsed, 3.251)
        release.wait.assert_called_once_with(3.25)

    def test_observed_windows_early_wake_does_not_release_hello(self):
        elapsed, release = self.run_hold([100.0, 100.0, 103.2494637, 103.25])
        self.assertEqual(elapsed, 3.25)
        self.assertEqual(release.wait.call_count, 2)
        self.assertEqual(release.wait.call_args_list[0].args, (3.25,))
        self.assertAlmostEqual(release.wait.call_args_list[1].args[0], 0.0005363, places=9)

    def test_repeated_early_wakes_cannot_restart_the_hold(self):
        elapsed, release = self.run_hold([100.0, 100.0, 101.0, 103.2494637, 103.25])
        self.assertEqual(elapsed, 3.25)
        self.assertEqual(release.wait.call_count, 3)
        self.assertEqual(release.wait.call_args_list[1].args, (2.25,))
        self.assertAlmostEqual(release.wait.call_args_list[2].args[0], 0.0005363, places=9)

    def test_preexisting_cleanup_never_waits_or_forwards(self):
        elapsed, release = self.run_hold([100.0], already_released=True)
        self.assertIsNone(elapsed)
        release.wait.assert_not_called()

    def test_cleanup_wakeup_never_claims_the_full_hold(self):
        elapsed, release = self.run_hold([100.0, 100.0], waits=[True])
        self.assertIsNone(elapsed)
        release.wait.assert_called_once_with(3.25)

    def test_cleanup_after_early_wakeup_remains_cancellable(self):
        elapsed, release = self.run_hold([100.0, 100.0], states=[False, True])
        self.assertIsNone(elapsed)
        release.wait.assert_called_once_with(3.25)


if __name__ == "__main__":
    unittest.main(verbosity=2)
