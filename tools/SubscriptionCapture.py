"""Windows-only, local subscription acquisition. Python 3.11+, standard library.

No scheduler, proxy-setting changes, subscription converter or forwarding core.
Private manifests, response bytes, headers, provenance and indexes use user DPAPI.
Use --help; see docs/SUBSCRIPTION_CAPTURE.md for the authorization contract.
"""
from __future__ import annotations

import argparse
import base64
import concurrent.futures
import ctypes
from ctypes import wintypes
import datetime as dt
import hashlib
import http.client
import ipaddress
import json
import os
from pathlib import Path
import re
import socket
import ssl
import subprocess
import tempfile
import threading
import time
import urllib.parse
import uuid
import zlib

MAGIC = b"SWIRLCAPTURE1\n"
MAX_BODY = 8 * 1024 * 1024
MAX_TOTAL = 64 * 1024 * 1024
MAX_JOBS = 128
MAX_DEPTH = 3
MAX_REDIRECTS = 3
UTC = dt.timezone.utc


class CaptureError(Exception):
    """Only fixed, non-secret error codes may cross the logging boundary."""


def digest(data):
    return hashlib.sha256(data).hexdigest()


def packed(value):
    return json.dumps(value, ensure_ascii=False, separators=(",", ":")).encode("utf-8")


def protect(data, decrypt=False):
    if os.name != "nt":
        raise CaptureError("WindowsDPAPIRequired")

    class Blob(ctypes.Structure):
        _fields_ = [("size", wintypes.DWORD), ("data", ctypes.POINTER(ctypes.c_ubyte))]

    crypt = ctypes.WinDLL("crypt32", use_last_error=True)
    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel.LocalFree.argtypes = [ctypes.c_void_p]
    kernel.LocalFree.restype = ctypes.c_void_p
    storage = ctypes.create_string_buffer(data)
    src = Blob(len(data), ctypes.cast(storage, ctypes.POINTER(ctypes.c_ubyte)))
    out = Blob()
    if decrypt:
        fn = crypt.CryptUnprotectData
        fn.argtypes = [ctypes.POINTER(Blob), ctypes.c_void_p, ctypes.c_void_p,
                       ctypes.c_void_p, ctypes.c_void_p, wintypes.DWORD, ctypes.POINTER(Blob)]
        args = (ctypes.byref(src), None, None, None, None, 1, ctypes.byref(out))
    else:
        fn = crypt.CryptProtectData
        fn.argtypes = [ctypes.POINTER(Blob), wintypes.LPCWSTR, ctypes.c_void_p,
                       ctypes.c_void_p, ctypes.c_void_p, wintypes.DWORD, ctypes.POINTER(Blob)]
        args = (ctypes.byref(src), "Swirl subscription capture", None, None, None, 1, ctypes.byref(out))
    fn.restype = wintypes.BOOL
    try:
        if not fn(*args):
            raise CaptureError("DPAPIFailed")
        return ctypes.string_at(out.data, out.size)
    finally:
        ctypes.memset(storage, 0, len(data))
        if out.data:
            ctypes.memset(out.data, 0, out.size)
            kernel.LocalFree(out.data)


def atomic_write(path, data):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temp = tempfile.mkstemp(prefix=".capture-", dir=path.parent)
    try:
        with os.fdopen(fd, "wb") as stream:
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temp, path)
    finally:
        if os.path.exists(temp):
            os.unlink(temp)


def save_private(path, value):
    atomic_write(path, MAGIC + protect(packed(value)))


def read_private(path):
    path = Path(path)
    if path.stat().st_size > 100 * 1024 * 1024:
        raise CaptureError("EncryptedFileTooLarge")
    data = path.read_bytes()
    if not data.startswith(MAGIC):
        raise CaptureError("SealedFileRequired")
    try:
        return json.loads(protect(data[len(MAGIC):], True))
    except (ValueError, UnicodeError):
        raise CaptureError("InvalidPrivateDocument") from None


def url_parts(url, fixtures=False):
    if not isinstance(url, str) or len(url) > 8192 or re.search(r"[\x00-\x20\x7f\\]", url):
        raise CaptureError("InvalidURL")
    try:
        p = urllib.parse.urlsplit(url)
        port = p.port or (443 if p.scheme == "https" else 80)
        local = p.hostname in ("127.0.0.1", "::1")
        if (p.scheme != "https" and not (fixtures and local and p.scheme == "http")) or not p.hostname:
            raise ValueError()
        if p.username is not None or p.password is not None or p.fragment or not 1 <= port <= 65535:
            raise ValueError()
        p.hostname.encode("ascii")  # Explicit punycode URLs only.
        url.encode("ascii")
        return p
    except (ValueError, UnicodeError):
        raise CaptureError("InvalidURL") from None


def origin(url):
    p = urllib.parse.urlsplit(url)
    return p.scheme, p.hostname, p.port or (443 if p.scheme == "https" else 80)


def headers_valid(headers):
    if not isinstance(headers, dict) or len(headers) > 16:
        raise CaptureError("InvalidHeaders")
    forbidden = {"host", "connection", "content-length", "transfer-encoding", "proxy-authorization", "accept-encoding"}
    seen = set()
    for name, value in headers.items():
        if not re.fullmatch(r"[A-Za-z0-9-]{1,64}", name) or name.lower() in forbidden or name.lower() in seen:
            raise CaptureError("InvalidHeaders")
        if not isinstance(value, str) or len(value) > 8192 or re.search(r"[\x00-\x1f\x7f]", value):
            raise CaptureError("InvalidHeaders")
        try:
            value.encode("latin-1")
        except UnicodeError:
            raise CaptureError("InvalidHeaders") from None
        seen.add(name.lower())


def validate_manifest(m):
    if not isinstance(m, dict) or m.get("schema") != 1:
        raise CaptureError("InvalidManifest")
    groups, entries = m.get("groups"), m.get("entries")
    if not isinstance(groups, dict) or not groups or len(groups) > 32:
        raise CaptureError("InvalidGroups")
    for name, group in groups.items():
        if not re.fullmatch(r"[A-Za-z0-9_-]{1,40}", name) or not isinstance(group, dict):
            raise CaptureError("InvalidGroups")
        if type(group.get("windowSeconds")) is not int or not 1 <= group["windowSeconds"] <= 600:
            raise CaptureError("InvalidWindowDuration")
    if not isinstance(entries, list) or not 1 <= len(entries) <= MAX_JOBS:
        raise CaptureError("InvalidEntries")
    fixtures = m.get("localFixtures") is True
    ids = set()
    for entry in entries:
        if not isinstance(entry, dict) or not re.fullmatch(r"[A-Za-z0-9_-]{1,40}", entry.get("id", "")):
            raise CaptureError("InvalidEntryID")
        if entry["id"] in ids or entry.get("group") not in groups:
            raise CaptureError("DuplicateIDOrUnknownGroup")
        ids.add(entry["id"])
        url_parts(entry.get("url"), fixtures)
        headers_valid(entry.get("headers", {}))
        if entry.get("kind", "root") not in ("root", "resource"):
            raise CaptureError("InvalidResourceKind")
    # Only exact URLs listed in this local manifest may ever be requested.
    # No broad hostname allowlists, script execution or relative local file reads.
    proxy = m.get("proxy", {"mode": "direct"})
    if proxy.get("mode") not in ("direct", "http-loopback"):
        raise CaptureError("InvalidProxy")
    if proxy["mode"] == "http-loopback":
        if proxy.get("host") not in ("127.0.0.1", "::1") or type(proxy.get("port")) is not int or not 1 <= proxy["port"] <= 65535:
            raise CaptureError("InvalidProxy")
    if type(m.get("concurrency", 4)) is not int or not 1 <= m.get("concurrency", 4) <= 4:
        raise CaptureError("InvalidConcurrency")
    return m


def decode_body(raw, encoding):
    if len(raw) > MAX_BODY:
        raise CaptureError("ResponseTooLarge")
    if not encoding or encoding.lower() == "identity":
        return raw
    if encoding.lower() not in ("gzip", "deflate"):
        raise CaptureError("UnsupportedContentEncoding")
    try:
        dec = zlib.decompressobj(31 if encoding.lower() == "gzip" else 15)
        out = dec.decompress(raw, MAX_BODY + 1)
        if len(out) > MAX_BODY or dec.unconsumed_tail:
            raise CaptureError("DecompressedBodyTooLarge")
        if not dec.eof or dec.unused_data:
            raise CaptureError("InvalidCompressedBody")
        return out
    except zlib.error:
        raise CaptureError("InvalidCompressedBody") from None


def document_status(body, content_type):
    if not body.strip():
        raise CaptureError("EmptyResponse")
    text = body[:65536].decode("utf-8-sig", "replace").lstrip().lower()
    if "text/html" in content_type.lower() or re.search(r"^<(?:!doctype\s+html|html|head|body|form)\b", text):
        raise CaptureError("HTMLOrLoginPage")
    if text.startswith(("access denied", "unauthorized", "forbidden", "error:", "subscription expired")):
        raise CaptureError("ErrorDocument")
    if text.startswith("{"):
        try:
            value = json.loads(body)
            if isinstance(value, dict) and any(k in value for k in ("error", "errors", "message", "success")) and not any(k in value for k in ("proxies", "outbounds", "servers")):
                raise CaptureError("ErrorDocument")
        except (ValueError, UnicodeError):
            pass  # Unknown/malformed formats are retained for offline analysis.
    return "CapturedUnvalidated"  # Never implies semantic import or working nodes.


def discover(body, base):
    """Conservative hints only; all candidates require exact manifest authorization.

    Handles common YAML url:, JSON url/download_url and INI URL/resource lines.
    Unknown layouts remain in the encrypted original and are explicitly unverified.
    """
    text = body.decode("utf-8-sig", "replace")
    found = set()
    pattern = r'''(?im)(?:["']?(?:url|download_url)["']?\s*[:=]\s*["']?)(https?://[^\s"'<>,]+)'''
    for match in re.finditer(pattern, text):
        found.add(urllib.parse.urljoin(base, match.group(1)))
    for match in re.finditer(r"(?im)^\s*(https?://[^\s,]+)\s*(?:,|$)", text):
        found.add(match.group(1))
    # Structural JSON recursion avoids interpreting arbitrary script code.
    try:
        obj = json.loads(body)
        def walk(v, depth=0):
            if depth > 32:
                return
            if isinstance(v, dict):
                for k, item in v.items():
                    if k in ("url", "download_url") and isinstance(item, str):
                        found.add(urllib.parse.urljoin(base, item))
                    elif isinstance(item, (dict, list)):
                        walk(item, depth + 1)
            elif isinstance(v, list):
                for item in v:
                    walk(item, depth + 1)
        walk(obj)
    except (ValueError, UnicodeError, RecursionError):
        pass
    if len(found) > MAX_JOBS:
        raise CaptureError("ReferenceLimit")
    return sorted(found)


class Window:
    def __init__(self, opened_at, duration, margin=30):
        try:
            opened = dt.datetime.fromisoformat(opened_at.replace("Z", "+00:00"))
            if opened.tzinfo is None:
                raise ValueError()
            now = dt.datetime.now(UTC)
            if opened > now:
                raise ValueError()
        except (AttributeError, TypeError, ValueError):
            raise CaptureError("InvalidActualOpeningTime") from None
        self.wall_deadline = opened.timestamp() + duration - margin
        self.monotonic_deadline = time.monotonic() + max(0, self.wall_deadline - now.timestamp())

    def remaining(self):
        # Clock rollback never extends a grant; forward jumps shorten it.
        return max(0, min(self.monotonic_deadline - time.monotonic(), self.wall_deadline - time.time()))


class Budget:
    def __init__(self):
        self.lock = threading.Lock()
        self.used = 0

    def add(self, size):
        with self.lock:
            self.used += size
            if self.used > MAX_TOTAL:
                raise CaptureError("BatchByteLimit")


def request_once(url, headers, proxy, window, budget, fixtures=False):
    p = url_parts(url, fixtures)
    if window.remaining() <= 0:
        raise CaptureError("WindowClosed")
    cancelled = threading.Event()
    sockets = []
    socket_lock = threading.Lock()

    def stop():
        cancelled.set()
        with socket_lock:
            for sock in sockets:
                try:
                    sock.shutdown(socket.SHUT_RDWR)
                except OSError:
                    pass
                sock.close()

    def check():
        if window.remaining() <= 0:
            raise CaptureError("WindowClosed")
        if cancelled.is_set():
            raise CaptureError("RequestTimeout")

    # Called by http.client before TLS/CONNECT. DNS never grants a fresh deadline.
    def connect(address, timeout=None, source_address=None, **kwargs):
        host, port = address
        addresses = socket.getaddrinfo(host, port, type=socket.SOCK_STREAM)
        check()
        permitted_local = proxy["mode"] == "http-loopback" or fixtures
        for family, kind, protocol, _, endpoint in addresses:
            ip = ipaddress.ip_address(endpoint[0])
            if not ip.is_global and not (permitted_local and ip.is_loopback):
                raise CaptureError("NonPublicTargetRejected")
        for family, kind, protocol, _, endpoint in addresses:
            check()
            sock = socket.socket(family, kind, protocol)
            with socket_lock:
                sockets.append(sock)
            try:
                check()
                sock.settimeout(min(5, window.remaining()))
                sock.connect(endpoint)
                check()
                return sock
            except OSError:
                sock.close()
                check()
        raise CaptureError("ConnectFailed")

    # Numeric private destinations are forbidden even through an explicit proxy.
    try:
        ip = ipaddress.ip_address(p.hostname)
        if not ip.is_global and not (fixtures and ip.is_loopback):
            raise CaptureError("NonPublicTargetRejected")
    except ValueError:
        if p.hostname.lower() == "localhost" or p.hostname.lower().endswith((".localhost", ".local")):
            raise CaptureError("NonPublicTargetRejected")
    target_port = p.port or (443 if p.scheme == "https" else 80)
    via_proxy = proxy["mode"] == "http-loopback"
    host = proxy["host"] if via_proxy else p.hostname
    port = proxy["port"] if via_proxy else target_port
    class CaptureHTTPSConnection(http.client.HTTPSConnection):
        def connect(self):
            http.client.HTTPConnection.connect(self)
            self.sock = self._context.wrap_socket(self.sock, server_hostname=self._tunnel_host or self.host,
                                                 do_handshake_on_connect=False)
            with socket_lock:
                sockets.append(self.sock)
            check()
            self.sock.do_handshake()
            check()

    cls = CaptureHTTPSConnection if p.scheme == "https" else http.client.HTTPConnection
    conn = cls(host, port, timeout=min(5, window.remaining()))
    conn._create_connection = connect
    if via_proxy and p.scheme == "https":
        conn.set_tunnel(p.hostname, target_port)
    # A wall deadline also interrupts slow headers and TLS, not only body reads.
    timer = threading.Timer(min(20, window.remaining()), stop)
    timer.daemon = True
    timer.start()
    try:
        check()
        request_headers = {"User-Agent": "Swirl-Capture/1", "Accept": "*/*", "Accept-Encoding": "gzip, deflate", "Connection": "close"}
        request_headers.update(headers)
        target = url if via_proxy and p.scheme == "http" else urllib.parse.urlunsplit(("", "", p.path or "/", p.query, ""))
        conn.request("GET", target, headers=request_headers)
        # HTTPS wraps the connected socket; retain that handle for deadline abort.
        with socket_lock:
            if conn.sock is not None:
                sockets.append(conn.sock)
        check()
        response = conn.getresponse()
        received_headers = {k.lower(): v for k, v in response.getheaders()}
        if response.status != 200:
            return response.status, received_headers, b""
        raw = bytearray()
        while True:
            check()
            chunk = response.read1(min(65536, MAX_BODY + 1 - len(raw)))
            if not chunk:
                break
            budget.add(len(chunk))
            raw.extend(chunk)
            if len(raw) > MAX_BODY:
                raise CaptureError("ResponseTooLarge")
        check()
        if response.length not in (None, 0):
            raise CaptureError("TruncatedResponse")
        return response.status, received_headers, bytes(raw)
    except CaptureError:
        raise
    except ssl.SSLError:
        raise CaptureError("TLSFailed") from None
    except (OSError, http.client.HTTPException, ValueError):
        check()
        raise CaptureError("TransportFailed") from None
    finally:
        timer.cancel()
        conn.close()
        stop()


def fetch(entry, manifest, windows, budget):
    url = entry["url"]
    headers = entry.get("headers", {})
    window = windows[entry["group"]]
    allowed = {e["url"]: e for e in manifest["entries"]}
    seen = set()
    for redirect in range(MAX_REDIRECTS + 1):
        if url in seen:
            raise CaptureError("RedirectCycle")
        seen.add(url)
        for attempt in range(2):
            try:
                status, meta, raw = request_once(url, headers, manifest.get("proxy", {"mode": "direct"}), window, budget, manifest.get("localFixtures", False))
                if status in (429, 500, 502, 503, 504) and attempt == 0:
                    delay = 1
                    if status == 429:
                        retry = meta.get("retry-after", "1")
                        if not retry.isdecimal() or int(retry) > 2:
                            raise CaptureError("RateLimited")
                        delay = max(1, int(retry))
                    if window.remaining() <= delay:
                        raise CaptureError("WindowClosed")
                    time.sleep(delay)
                    continue
                break
            except CaptureError as exc:
                if str(exc) not in ("ConnectFailed", "TransportFailed", "RequestTimeout") or attempt == 1:
                    raise
                if window.remaining() <= 1:
                    raise CaptureError("WindowClosed") from None
                time.sleep(1)
        if status in (301, 302, 303, 307, 308):
            target = urllib.parse.urljoin(url, meta.get("location", ""))
            url_parts(target, manifest.get("localFixtures", False))
            if target not in allowed:
                raise CaptureError("RedirectNotAuthorized")
            if origin(url)[0] == "https" and origin(target)[0] != "https":
                raise CaptureError("RedirectDowngrade")
            if redirect == MAX_REDIRECTS:
                raise CaptureError("RedirectLimit")
            # No supplied headers (including cookies/custom tokens) cross origins.
            if origin(target) != origin(url):
                headers = {}
            target_window = windows[allowed[target]["group"]]
            if target_window.remaining() < window.remaining():
                window = target_window
            url = target
            continue
        if status != 200:
            raise CaptureError(f"HTTP{status}")
        decoded = decode_body(raw, meta.get("content-encoding", ""))
        classification = document_status(decoded, meta.get("content-type", ""))
        return {"schema": 1, "source": entry, "final_url": url,
                "fetchedAt": dt.datetime.now(UTC).isoformat(), "headers": meta,
                "rawBase64": base64.b64encode(raw).decode("ascii"),
                "rawSha256": digest(raw), "decodedSha256": digest(decoded),
                "classification": classification, "references": discover(decoded, url)}
    raise CaptureError("RedirectLimit")


def acquisition_key(entry):
    # Different user agents/auth/group remain separate exports of a subscription.
    return digest(packed([entry["url"], sorted((k.lower(), v) for k, v in entry.get("headers", {}).items()), entry["group"]]))


def capture(manifest, authorization, cache):
    validate_manifest(manifest)
    if authorization.get("confirmed") is not True:
        raise CaptureError("OpeningConfirmationRequired")
    windows = {name: Window(authorization.get("groups", {}).get(name, {}).get("openedAt"), value["windowSeconds"])
               for name, value in manifest["groups"].items()}
    cache = Path(cache).resolve()
    cache.mkdir(parents=True, exist_ok=True)
    # Exclusive lock prevents competing runs overwriting each other's cache index.
    lock = cache / "capture.lock"
    try:
        fd = os.open(lock, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
    except FileExistsError:
        raise CaptureError("CacheBusy") from None
    os.close(fd)
    try:
        index_path = cache / "index.dpapi"
        index = read_private(index_path) if index_path.exists() else {"schema": 1, "entries": {}}
        batch = uuid.uuid4().hex
        budget = Budget()
        results, records = [], {}
        groups = {}
        for i, entry in enumerate(manifest["entries"]):
            groups.setdefault(acquisition_key(entry), []).append((i, entry))
        # All authorized resources are queued now, so discovery never delays roots.
        ordered = sorted(groups.items(), key=lambda pair: pair[1][0][1].get("kind", "root") != "root")
        with concurrent.futures.ThreadPoolExecutor(max_workers=manifest.get("concurrency", 4)) as pool:
            futures = {pool.submit(fetch, entries[0][1], manifest, windows, budget): (key, entries)
                       for key, entries in ordered}
            for future in concurrent.futures.as_completed(futures):
                key, entries = futures[future]
                try:
                    record = future.result()
                    record["sources"] = [e for _, e in entries]
                    file = f"{batch}/{key}.dpapi"
                    save_private(cache / file, record)
                    # Verify persisted bytes before making the last-good pointer visible.
                    saved = read_private(cache / file)
                    if saved["rawSha256"] != digest(base64.b64decode(saved["rawBase64"], validate=True)):
                        raise CaptureError("CacheIntegrityFailed")
                    index["entries"][key] = {"file": file, "sources": record["sources"]}
                    records[key] = record
                    code = record["classification"]
                except CaptureError as exc:
                    code = str(exc)
                except Exception:
                    code = "InternalFailure"  # Never print exception URLs/credentials.
                for ordinal, _ in entries:
                    results.append({"entry": ordinal + 1, "code": code})
        # Unknown references are retained encrypted and reported, never auto-authorized.
        known = {e["url"] for e in manifest["entries"]}
        missing = sorted({u for r in records.values() for u in r["references"] if u not in known})
        graph = {r["source"]["url"]: r["references"] for r in records.values()}
        cycles, too_deep = set(), set()
        # Memoized (node, depth) traversal bounds adversarial fan-out/cycles.
        for root in graph:
            visited = set()
            def visit(url, path):
                if url in path:
                    cycles.add(url)
                    return
                if len(path) > MAX_DEPTH:
                    too_deep.add(url)
                    return
                state = (url, len(path))
                if state in visited:
                    return
                visited.add(state)
                for child in graph.get(url, []):
                    visit(child, path + [url])
            visit(root, [])
        report = {"schema": 1, "batch": batch, "results": sorted(results, key=lambda row: row["entry"]),
                  "captured": sum(r["code"] == "CapturedUnvalidated" for r in results),
                  "failed": sum(r["code"] != "CapturedUnvalidated" for r in results),
                  "unapprovedReferences": len(missing), "cycles": len(cycles),
                  "overDepth": len(too_deep), "networkBytes": budget.used,
                  "referenceCoverage": "common-hints-only", "activeConfigurationChanged": False}
        save_private(cache / batch / "details.dpapi", {"manifest": manifest, "authorization": authorization,
                     "unapprovedReferences": missing, "cycles": sorted(cycles), "overDepth": sorted(too_deep), "report": report})
        save_private(index_path, index)
        atomic_write(cache / batch / "report.json", packed(report))
        return report
    finally:
        lock.unlink(missing_ok=True)


def replay(cache_file, inspector=None, store=None):
    record = read_private(cache_file)
    raw = base64.b64decode(record["rawBase64"], validate=True)
    if digest(raw) != record["rawSha256"]:
        raise CaptureError("CacheIntegrityFailed")
    body = decode_body(raw, record["headers"].get("content-encoding", ""))
    if digest(body) != record["decodedSha256"]:
        raise CaptureError("CacheIntegrityFailed")
    result = {"code": "OfflineIntegrityPassed", "rawBytes": len(raw), "decodedBytes": len(body)}
    if inspector:
        if not store:
            raise CaptureError("IsolatedStoreRequired")
        store = Path(store).resolve()
        if store.exists():
            raise CaptureError("NewIsolatedStoreRequired")
        store.parent.mkdir(parents=True, exist_ok=True)
        # The existing C++ inspector accepts DPAPI blobs with no outer magic.
        fd, path = tempfile.mkstemp(prefix="replay-", suffix=".dpapi", dir=store.parent)
        os.close(fd)
        try:
            atomic_write(path, protect(body))
            run = subprocess.run([str(Path(inspector).resolve()), path, str(store)],
                                 capture_output=True, timeout=60, check=False)
            result["importExitCode"] = run.returncode
            if run.returncode == 0:
                values = json.loads(run.stdout.decode("utf-8-sig"))
                result["nodes"] = values.get("nodes", 0)
                result["incompleteNodes"] = values.get("incompleteNodes", 0)
                result["code"] = "OfflineImportPassed"
            else:
                result["code"] = "OfflineImportRejected"
        finally:
            Path(path).unlink(missing_ok=True)
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    for name in ("seal", "check"):
        p = sub.add_parser(name)
        p.add_argument("manifest", type=Path)
    p = sub.add_parser("capture")
    p.add_argument("manifest", type=Path)
    p.add_argument("authorization", type=Path)
    p.add_argument("cache", type=Path)
    p = sub.add_parser("replay")
    p.add_argument("cache_file", type=Path)
    p.add_argument("--inspector", type=Path)
    p.add_argument("--store", type=Path)
    args = parser.parse_args()
    try:
        if args.command == "seal":
            if args.manifest.stat().st_size > 1024 * 1024:
                raise CaptureError("ManifestTooLarge")
            manifest = json.loads(args.manifest.read_text(encoding="utf-8-sig"))
            # Empty template rows mean the user does not have that export.
            manifest["notProvided"] = [e.get("client", e.get("id")) for e in manifest.get("entries", []) if not e.get("url")]
            manifest["entries"] = [e for e in manifest.get("entries", []) if e.get("url")]
            manifest = validate_manifest(manifest)
            save_private(args.manifest, manifest)  # Replace in place; no plaintext backup.
            result = {"code": "ManifestSealed", "entries": len(manifest["entries"])}
        elif args.command == "check":
            manifest = validate_manifest(read_private(args.manifest))
            result = {"code": "ManifestCheckedNoNetwork", "entries": len(manifest["entries"]), "groups": len(manifest["groups"])}
        elif args.command == "capture":
            result = capture(read_private(args.manifest), json.loads(args.authorization.read_text(encoding="utf-8-sig")), args.cache)
        else:
            result = replay(args.cache_file, args.inspector, args.store)
        print(json.dumps(result, ensure_ascii=True))
        return 1 if result.get("failed", 0) or result.get("unapprovedReferences", 0) or result.get("cycles", 0) or result.get("overDepth", 0) or result.get("code") == "OfflineImportRejected" else 0
    except CaptureError as exc:
        print(json.dumps({"code": str(exc)}))
        return 2
    except Exception:
        print('{"code":"LocalOperationFailed"}')
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
