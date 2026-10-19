"""Port candidates for fixtures which must hold TCP and UDP on the same port.

Windows has separate protocol exclusion tables. A TCP ephemeral allocation does
not establish that UDP may bind that port. Read the tables without changing the
host, then let the caller reserve both real sockets. This is candidate selection,
not permission-error recovery: callers must still propagate every access denial.
"""
from functools import lru_cache
import random
import re
import subprocess
import sys


def parse_exclusions(output):
    """Parse numeric netsh rows, independently of the localized column labels."""
    rows, table = [], False
    for line in output.splitlines():
        line = line.strip()
        if re.fullmatch(rb'-+\s+-+', line):
            table = True
            continue
        if not table or not line or line.startswith(b'* -'):
            continue
        match = re.fullmatch(rb'(\d+)\s+(\d+)\s*\*?', line)
        if match is None:
            raise ValueError(f'Unrecognized Windows port exclusion row: {line!r}')
        first, last = map(int, match.groups())
        if not 1 <= first <= last <= 65535:
            raise ValueError(f'Invalid Windows port exclusion range: {(first, last)!r}')
        rows.append((first, last))
    if not table:
        raise ValueError('Windows port exclusion query did not return a table')
    return rows


@lru_cache(maxsize=2)
def windows_candidates(ipv6):
    # One read-only snapshot per family/process. If reservations change later,
    # the actual bind error still fails the fixture; it is never swallowed.
    family = 'ipv6' if ipv6 else 'ipv4'
    excluded = set()
    for protocol in ('tcp', 'udp'):
        command = ['netsh', 'interface', family, 'show', 'excludedportrange',
                   f'protocol={protocol}']
        result = subprocess.run(command, check=True, stdout=subprocess.PIPE,
                                stderr=subprocess.PIPE, timeout=10)
        print(f'Loopback pair reservation snapshot: {family} {protocol}\n'
              + result.stdout.decode('utf-8', errors='replace'), file=sys.stderr)
        for first, last in parse_exclusions(result.stdout):
            excluded.update(range(first, last + 1))
    candidates = tuple(port for port in range(49152, 65536) if port not in excluded)
    if not candidates:
        raise RuntimeError(f'No unexcluded private TCP/UDP fixture port for {family}')
    return candidates


def pair_port(ipv6=False):
    if sys.platform != 'win32':
        return 0
    return random.SystemRandom().choice(windows_candidates(ipv6))
