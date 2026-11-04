# SwirlVF interrupted-work checkpoint (2026-11-02)

This checkpoint preserves the reviewed uncommitted source from the delivery
worktree at ca8e6f2c1c0b0da1e0529feed8cb47809c976524. The primary checkout is
clean main; it is not the interrupted font worktree. Remote test was still
63dde8812f85839aa6024cbba6c498c96cae022d when recovery began.

An active test process and subsequent source changes were observed in the old
worktree during recovery. The twelve reviewed files were copied byte-for-byte
into a separate worktree/branch. Its private snapshot manifest records SHA-256
for every recovered file. No reset, cleanup or overwrite of the old worktree
was performed. A separate remote checkpoint prevents concurrent branch updates
from replacing this snapshot.

Recovered work comprises detached HVF hierarchy traces, symbolic axis and
projection branch partitions, adaptive CFF2 line-slice fitting, explicit
slice-only installation admission, canonical vertical metric frames, appended
GPOS origin compensation, and the corresponding authored tests/diagnostics.
All tolerances and existing strict platform failures are retained. Slice
acceptance explicitly does not constitute three-axis or whole-font acceptance.

Recovery validation: the seven piecewise tests and six origin-compensation
tests pass on macOS 26.5.1 ARM64 / Python 3.12.16. The six audit regressions pass.
The broader suite is recorded separately with exact execution scope; tests
running in the old, concurrently modified worktree are not evidence for this
snapshot's exact tree. No font binaries, private source data, credentials or
personal files are included in this checkpoint.

Formal output remains absent: SwirlVF.ttc has no delivery hash. Source fitting,
raw metrics, full-face coverage, platform verification and final installation
remain open. This engineering checkpoint does not claim formal delivery.
