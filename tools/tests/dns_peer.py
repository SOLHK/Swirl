"""Independent, synthetic UDP/TCP DNS peer. Loopback only; no system changes."""
from contextlib import ExitStack
import errno
import socketserver
import socket
import struct
import threading


def exact(sock, size):
    result = b''
    while len(result) < size:
        part = sock.recv(size-len(result))
        if not part:
            raise EOFError()
        result += part
    return result


def name(value):
    return b''.join(bytes([len(label)])+label.encode('ascii') for label in value.split('.'))+b'\0'


class DnsPeer:
    def __init__(self, mode='normal', ttl=30, ipv6=False):
        self.mode, self.ttl = mode, ttl
        self.ipv6=ipv6
        self.queries, self.errors = [], []
        owner = self

        class UDP(socketserver.ThreadingUDPServer):
            daemon_threads = True
            address_family=socket.AF_INET6 if ipv6 else socket.AF_INET
            def handle_error(self, request, address):
                owner.errors.append('udp-handler')

        class TCP(socketserver.ThreadingTCPServer):
            daemon_threads = True
            address_family=socket.AF_INET6 if ipv6 else socket.AF_INET
            def handle_error(self, request, address):
                owner.errors.append('tcp-handler')

        class UDPHandler(socketserver.BaseRequestHandler):
            def handle(self):
                data, sock = self.request
                response = owner.respond(data, False)
                if response is not None:
                    sock.sendto(response, self.client_address)

        class TCPHandler(socketserver.BaseRequestHandler):
            def handle(self):
                self.request.settimeout(3)
                try:
                    data = exact(self.request, struct.unpack('!H', exact(self.request, 2))[0])
                    response = owner.respond(data, True)
                    if response is not None:
                        framed = struct.pack('!H', len(response))+response
                        for at in range(0, len(framed), 3):
                            self.request.sendall(framed[at:at+3])
                except (EOFError, OSError):
                    pass

        host='::1' if ipv6 else '127.0.0.1'
        # A free UDP port can already be occupied by TCP. Hold both sockets
        # before starting either server, and release a failed partial pair.
        for attempt in range(8):
            try:
                with ExitStack() as cleanup:
                    self.udp = cleanup.enter_context(UDP((host, 0), UDPHandler))
                    self.port = self.udp.server_address[1]
                    self.tcp = cleanup.enter_context(TCP((host, self.port), TCPHandler))
                    cleanup.pop_all()
                break
            except OSError as error:
                if error.errno != errno.EADDRINUSE or attempt == 7:
                    raise
        for server in (self.udp, self.tcp):
            threading.Thread(target=server.serve_forever, daemon=True).start()

    @property
    def address(self):
        return f'[::1]:{self.port}' if self.ipv6 else f'127.0.0.1:{self.port}'

    def close(self):
        for server in (self.udp, self.tcp):
            server.shutdown()
            server.server_close()
        assert not self.errors, self.errors

    def respond(self, data, tcp):
        assert len(data) <= 512 and data[2:12] == b'\x01\x00\x00\x01\x00\x00\x00\x00\x00\x00'
        at, labels = 12, []
        while data[at]:
            size = data[at]
            labels.append(data[at+1:at+1+size].decode('ascii'))
            at += 1+size
        host = '.'.join(labels)
        at += 1
        kind, qclass = struct.unpack('!HH', data[at:])
        assert kind in (1, 28) and qclass == 1
        self.queries.append((host, kind, tcp))
        if self.mode == 'silent':
            return None
        flags, records = 0x8180, []
        if self.mode == 'truncated' and not tcp:
            flags |= 0x0200
        elif self.mode == 'nxdomain':
            flags |= 3
        elif self.mode == 'servfail':
            flags |= 2
        elif self.mode == 'mixed-negative':
            flags |= 2 if kind == 1 else 3
        elif self.mode == 'cname' and host != 'alias.fixture.invalid':
            body = name('alias.fixture.invalid')
            records.append(b'\xc0\x0c'+struct.pack('!HHIH', 5, 1, self.ttl, len(body))+body)
        elif kind == 1:
            records.append(b'\xc0\x0c'+struct.pack('!HHIH', 1, 1, self.ttl, 4)+b'\x7f\x00\x00\x01')
        response = data[:2]+struct.pack('!HHHHH', flags, 1, len(records), 0, 0)+data[12:]+b''.join(records)
        if self.mode == 'wrong-id':
            response = bytes([response[0]^1])+response[1:]
        elif self.mode == 'wrong-question':
            response = response[:13]+bytes([response[13]^1])+response[14:]
        elif self.mode == 'trailing':
            response += b'UNEXPECTED'
        return response
