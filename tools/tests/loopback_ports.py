"""Own OS-allocated loopback TCP/UDP pairs without treating access denial as reuse.

Windows exclusion tables describe reservations, not live endpoint ownership.
Only a successful bind owns a port. Keep the actual TCP server bound while
checking the other protocol and creating UDP; never probe, close and rebind.
"""
from contextlib import ExitStack
import errno
from functools import lru_cache
import re
import socket
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
def windows_exclusions(ipv6):
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
    return frozenset(excluded)


class ExclusiveLoopbackBind:
    """SocketServer mixin: own Windows endpoints before bind, without REUSEADDR."""

    def server_bind(self):
        if sys.platform == 'win32' and hasattr(socket, 'SO_EXCLUSIVEADDRUSE'):
            self.socket.setsockopt(socket.SOL_SOCKET, socket.SO_EXCLUSIVEADDRUSE, 1)
        super().server_bind()


def reserve_tcp_udp(tcp_factory, udp_factory, *, ipv6=False, label='Loopback fixture'):
    """Return two bound SocketServers; neither factory may start a thread.

    TCP always requests port zero, so the OS avoids live TCP incumbents. Windows
    TCP/UDP reservations differ: hold rejected TCP owners until selection ends,
    so a sequential allocator can pass a whole UDP exclusion block without
    selecting the same endpoint again. The finite exclusion set bounds those
    prechecks separately from eight actual EADDRINUSE/10048 retries. Unknown
    access denials (including 10013), resource and construction errors propagate.

    https://learn.microsoft.com/en-us/windows/win32/api/winsock2/nf-winsock2-bind
    """
    excluded = windows_exclusions(ipv6) if sys.platform == 'win32' else frozenset()
    if len(excluded) == 65535:
        raise RuntimeError('No unexcluded TCP/UDP fixture port')
    host = '::1' if ipv6 else '127.0.0.1'
    filtered, attempt = set(), 0
    with ExitStack() as held:
        while attempt < 8:
            protocol, address = 'TCP', (host, 0)
            try:
                with ExitStack() as cleanup:
                    tcp = cleanup.enter_context(tcp_factory(address))
                    port = tcp.server_address[1]
                    if port in excluded:
                        if port in filtered:
                            raise RuntimeError('OS reused a still-held excluded TCP fixture port')
                        filtered.add(port)
                        held.callback(cleanup.pop_all().close)
                        continue
                    protocol, address = 'UDP', (host, port)
                    udp = cleanup.enter_context(udp_factory(address))
                    cleanup.pop_all()
                return tcp, udp
            except OSError as error:
                collision = error.errno == errno.EADDRINUSE or getattr(error, 'winerror', None) == 10048
                if not collision or attempt == 7:
                    error.add_note(f'{label} {protocol} bind on loopback {address!r}; '
                                   f'pair attempt {attempt + 1}/8')
                    raise
                attempt += 1
