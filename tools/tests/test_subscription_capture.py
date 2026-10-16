"""Real loopback HTTP + Windows DPAPI tests; never uses private subscriptions."""
import base64
from collections import Counter
import datetime as dt
import gzip
import importlib.util
import json
import os
from pathlib import Path
import socket
import tempfile
import threading
import time
import unittest
from unittest import mock
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

spec = importlib.util.spec_from_file_location("capture", Path(__file__).parents[1] / "SubscriptionCapture.py")
cap = importlib.util.module_from_spec(spec)
spec.loader.exec_module(cap)
BODY = b'{"proxies":[{"name":"synthetic","type":"socks5","server":"example.org","port":1080}]}'


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *args):
        pass

    def do_GET(self):
        self.server.hits[self.path] += 1
        self.server.headers_seen.append(dict(self.headers))
        path = self.path.split("?", 1)[0]
        status, headers, body = 200, {}, BODY
        if path == "/html":
            body = b"<!doctype html><html>sign in SECRET_MARKER</html>"
        elif path == "/json-error":
            body = b'{"error":"SECRET_MARKER"}'
        elif path == "/forbidden":
            status = 403
        elif path == "/unauthorized":
            status = 401
        elif path == "/rate":
            status = 429
            headers["Retry-After"] = "99"
        elif path == "/retry" and self.server.hits[self.path] == 1:
            status = 503
        elif path == "/empty":
            body = b""
        elif path == "/gzip":
            body = gzip.compress(BODY)
            headers["Content-Encoding"] = "gzip"
        elif path == "/bad-gzip":
            body = b"broken"
            headers["Content-Encoding"] = "gzip"
        elif path == "/bomb":
            body = gzip.compress(b"x" * (cap.MAX_BODY + 1))
            headers["Content-Encoding"] = "gzip"
        elif path == "/oversize":
            body = b"x" * (cap.MAX_BODY + 1)
        elif path == "/unknown":
            body = b"future-client-format\nSECRET_MARKER\n"
        elif path == "/base64":
            body = base64.urlsafe_b64encode(b"socks5://127.0.0.1:1080#synthetic")
        elif path == "/references":
            body = ('proxy-providers:\n  a:\n    url: "' + self.server.base + '/good"\n  b:\n    url: "https://example.org/NOT_AUTHORIZED"\n').encode()
        elif path == "/cycle":
            body = json.dumps({"url": self.server.base + "/cycle"}).encode()
        elif path.startswith("/chain"):
            n = int(path[6:])
            body = json.dumps({"url": self.server.base + f"/chain{n+1}"} if n < 5 else {"end": True}).encode()
        elif path == "/redirect":
            status = 302
            headers["Location"] = self.server.base + "/good"
        elif path == "/cross":
            status = 302
            headers["Location"] = self.server.other + "/good"
        elif path == "/loop":
            status = 302
            headers["Location"] = self.server.base + "/loop"
        elif path == "/blocked-redirect":
            status = 302
            headers["Location"] = "http://169.254.169.254/private"
        try:
            if path == "/slow-headers":
                self.connection.sendall(b"HTTP/1.1 200 OK\r\nX-Slow: ")
                for _ in range(80):
                    self.connection.sendall(b"a")
                    time.sleep(0.1)
                return
            self.send_response(status)
            for k, v in headers.items():
                self.send_header(k, v)
            self.send_header("Content-Length", str(len(body) + (10 if path == "/truncated" else 0)))
            self.end_headers()
            self.wfile.write(body)
        except (BrokenPipeError, ConnectionResetError, ConnectionAbortedError):
            pass


@unittest.skipUnless(os.name == "nt", "DPAPI tests require Windows")
class CaptureTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.servers = []
        for _ in range(2):
            s = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
            s.daemon_threads = True
            s.hits, s.headers_seen = Counter(), []
            s.base = f"http://127.0.0.1:{s.server_port}"
            threading.Thread(target=s.serve_forever, daemon=True).start()
            cls.servers.append(s)
        cls.server, cls.other = cls.servers
        cls.server.other = cls.other.base

    @classmethod
    def tearDownClass(cls):
        for server in cls.servers:
            server.shutdown()
            server.server_close()

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.cache = Path(self.temp.name) / "cache"

    def manifest(self, *paths):
        return {"schema": 1, "localFixtures": True, "proxy": {"mode": "direct"},
                "groups": {"g1": {"windowSeconds": 600}}, "entries": [
                    {"id": f"e{i}", "group": "g1", "url": p if p.startswith("http") else self.server.base + p,
                     "headers": {"Authorization": "Bearer SECRET_MARKER"}, "kind": "root"}
                    for i, p in enumerate(paths)]}

    def auth(self, seconds_ago=0):
        return {"confirmed": True, "groups": {"g1": {"openedAt": (dt.datetime.now(dt.timezone.utc) - dt.timedelta(seconds=seconds_ago)).isoformat()}}}

    def run_capture(self, *paths, seconds_ago=0):
        return cap.capture(self.manifest(*paths), self.auth(seconds_ago), self.cache)

    def test_dpapi_seal_reopen_and_tamper(self):
        path = Path(self.temp.name) / "manifest.private"
        m = self.manifest("/good?token=SECRET_MARKER")
        cap.save_private(path, m)
        self.assertNotIn(b"SECRET_MARKER", path.read_bytes())
        self.assertEqual(cap.read_private(path), m)
        data = bytearray(path.read_bytes()); data[-12] ^= 1; path.write_bytes(data)
        with self.assertRaises(cap.CaptureError):
            cap.read_private(path)

    def test_local_export_encrypted_without_network(self):
        path=Path(self.temp.name)/'export.yaml'
        path.write_bytes(BODY)
        before=sum(self.server.hits.values())
        result=cap.import_local(path,self.cache)
        self.assertEqual(result['networkRequests'],0)
        self.assertEqual(sum(self.server.hits.values()),before)
        index=cap.read_private(self.cache/'index.dpapi')
        cached=self.cache/next(iter(index['entries'].values()))['file']
        self.assertNotIn(b'example.org',cached.read_bytes())
        self.assertEqual(cap.replay(cached)['code'],'OfflineIntegrityPassed')

    @unittest.skipUnless(os.environ.get('SWIRL_RUST_INSPECTOR'), 'Rust offline inspector is opt-in')
    def test_rust_offline_pipeline_preserves_private_fields(self):
        module_spec=importlib.util.spec_from_file_location('analysis',Path(__file__).parents[1]/'Analyze-CapturedSubscriptions.py')
        analysis=importlib.util.module_from_spec(module_spec);module_spec.loader.exec_module(analysis)
        path=Path(self.temp.name)/'export.yaml'
        path.write_bytes(b'proxies:\n - {name: PRIVATE_NAME, type: trojan, server: private.example.org, port: 443, password: PRIVATE_SECRET, future-field: PRIVATE_VALUE}\ndns: {enable: true}\n')
        cap.import_local(path,self.cache)
        private=Path(self.temp.name)/'analysis.dpapi'
        report=analysis.analyze(self.cache,os.environ['SWIRL_RUST_INSPECTOR'],private)
        self.assertEqual(report['realTcpProbes'],0)
        self.assertTrue(report['sources'][0]['report']['parsed'])
        self.assertNotIn('PRIVATE',json.dumps(report))
        self.assertNotIn('private.example.org',json.dumps(report))
        self.assertNotIn(b'PRIVATE_SECRET',private.read_bytes())
        saved=cap.read_private(private)
        self.assertEqual(saved['documents'][0]['analysis']['nodes'][0]['future-field'],'PRIVATE_VALUE')

    def test_gzip_raw_preserved_and_offline_replay(self):
        report = self.run_capture("/gzip")
        self.assertEqual(report["captured"], 1)
        index = cap.read_private(self.cache / "index.dpapi")
        path = self.cache / next(iter(index["entries"].values()))["file"]
        record = cap.read_private(path)
        self.assertEqual(gzip.decompress(base64.b64decode(record["rawBase64"])), BODY)
        self.assertEqual(cap.replay(path)["code"], "OfflineIntegrityPassed")
        self.assertNotIn(b"SECRET_MARKER", path.read_bytes())

    def test_error_pages_status_compression_and_size(self):
        paths = ["/html", "/json-error", "/forbidden", "/unauthorized", "/rate", "/empty", "/bad-gzip", "/bomb", "/oversize", "/truncated"]
        report = self.run_capture(*paths)
        self.assertEqual(report["captured"], 0)
        self.assertEqual(report["failed"], len(paths))
        self.assertEqual([r["code"] for r in report["results"]], ["HTMLOrLoginPage", "ErrorDocument", "HTTP403", "HTTP401", "RateLimited", "EmptyResponse", "InvalidCompressedBody", "DecompressedBodyTooLarge", "ResponseTooLarge", "TruncatedResponse"])
        self.assertNotIn("SECRET_MARKER", json.dumps(report))

    def test_bounded_retry(self):
        self.server.hits["/retry"] = 0
        report = self.run_capture("/retry")
        self.assertEqual(report["captured"], 1)
        self.assertEqual(self.server.hits["/retry"], 2)

    def test_unknown_and_base64_cached_without_parser(self):
        self.assertEqual(self.run_capture("/unknown", "/base64")["captured"], 2)

    def test_closed_window_makes_no_request_and_keeps_cache(self):
        self.run_capture("/good")
        before = cap.read_private(self.cache / "index.dpapi")
        hits = self.server.hits["/good"]
        report = self.run_capture("/good", seconds_ago=601)
        self.assertEqual(report["results"][0]["code"], "WindowClosed")
        self.assertEqual(self.server.hits["/good"], hits)
        self.assertEqual(cap.read_private(self.cache / "index.dpapi"), before)

    def test_slow_headers_aborted_at_actual_opening_deadline(self):
        start = time.monotonic()
        report = self.run_capture("/slow-headers", seconds_ago=569)
        self.assertLess(time.monotonic() - start, 3)
        self.assertEqual(report["results"][0]["code"], "WindowClosed")

    def test_no_confirmation_no_network(self):
        with self.assertRaisesRegex(cap.CaptureError, "OpeningConfirmationRequired"):
            cap.capture(self.manifest("/good"), {"confirmed": False}, self.cache)

    def test_future_or_naive_opening_rejected(self):
        for value in ((dt.datetime.now(dt.timezone.utc) + dt.timedelta(seconds=60)).isoformat(), "2026-01-01T00:00:00"):
            with self.assertRaises(cap.CaptureError):
                cap.Window(value, 600)

    def test_roots_deduplicate_with_source_mapping(self):
        before = self.server.hits["/good"]
        report = self.run_capture("/good", "/good")
        self.assertEqual(report["captured"], 2)
        self.assertEqual(self.server.hits["/good"], before + 1)
        index = cap.read_private(self.cache / "index.dpapi")
        self.assertEqual(len(index["entries"]), 1)
        self.assertEqual(len(next(iter(index["entries"].values()))["sources"]), 2)

    def test_redirect_authorization_and_loops(self):
        report = self.run_capture("/redirect", "/good", "/loop", "/blocked-redirect")
        self.assertEqual([r["code"] for r in report["results"]], ["CapturedUnvalidated", "CapturedUnvalidated", "RedirectCycle", "InvalidURL"])

    def test_cross_origin_strips_all_custom_headers(self):
        self.other.headers_seen.clear()
        m = self.manifest("/cross", self.other.base + "/good")
        m["entries"][1]["headers"] = {}
        report = cap.capture(m, self.auth(), self.cache)
        self.assertEqual(report["captured"], 2)
        self.assertEqual(len(self.other.headers_seen), 2)
        self.assertTrue(all("Authorization" not in h for h in self.other.headers_seen))

    def test_reference_report_and_cycle(self):
        report = self.run_capture("/references", "/good", "/cycle")
        self.assertEqual(report["unapprovedReferences"], 1)
        self.assertEqual(report["cycles"], 1)
        self.assertNotIn("NOT_AUTHORIZED", json.dumps(report))

    def test_reference_depth(self):
        self.assertGreater(self.run_capture(*(f"/chain{i}" for i in range(6)))["overDepth"], 0)

    def test_cache_lock_and_corruption_fail_closed(self):
        self.cache.mkdir()
        (self.cache / "capture.lock").write_text("locked")
        with self.assertRaisesRegex(cap.CaptureError, "CacheBusy"):
            self.run_capture("/good")
        (self.cache / "capture.lock").unlink()
        (self.cache / "index.dpapi").write_bytes(b"corrupt")
        with self.assertRaises(cap.CaptureError):
            self.run_capture("/good")
        self.assertEqual((self.cache / "index.dpapi").read_bytes(), b"corrupt")

    def test_invalid_requests_blocked(self):
        for headers in ({"Host": "bad"}, {"Authorization": "a\r\nX: b"}, {"X-A": "1", "x-a": "2"}):
            with self.assertRaises(cap.CaptureError):
                cap.headers_valid(headers)
        for url in ("file:///etc/passwd", "https://u:p@example.org", "http://example.org", "https://example.org/\nsecret"):
            with self.assertRaises(cap.CaptureError):
                cap.url_parts(url)

    def test_raw_integrity_checked_on_replay(self):
        self.run_capture("/good")
        index = cap.read_private(self.cache / "index.dpapi")
        path = self.cache / next(iter(index["entries"].values()))["file"]
        record = cap.read_private(path)
        record["rawBase64"] = base64.b64encode(b"tampered").decode()
        cap.save_private(path, record)
        with self.assertRaisesRegex(cap.CaptureError, "CacheIntegrityFailed"):
            cap.replay(path)

    def test_atomic_write_failure_preserves_old_ciphertext(self):
        path = Path(self.temp.name) / "last-good.dpapi"
        cap.save_private(path, {"value": "old"})
        before = path.read_bytes()
        with mock.patch.object(cap.os, "replace", side_effect=OSError("synthetic write failure")):
            with self.assertRaises(OSError):
                cap.save_private(path, {"value": "new"})
        self.assertEqual(path.read_bytes(), before)
        self.assertEqual(cap.read_private(path), {"value": "old"})

    def test_multiple_windows_and_user_agents_stay_separate(self):
        m = self.manifest("/good", "/good", "/good")
        m["entries"][1]["headers"]["User-Agent"] = "Synthetic-Other-Client/1"
        m["entries"][2]["group"] = "g2"
        m["groups"]["g2"] = {"windowSeconds": 600}
        a = self.auth()
        a["groups"]["g2"] = self.auth(601)["groups"]["g1"]
        before = self.server.hits["/good"]
        report = cap.capture(m, a, self.cache)
        self.assertEqual(self.server.hits["/good"], before + 2)
        self.assertEqual([r["code"] for r in report["results"]], ["CapturedUnvalidated", "CapturedUnvalidated", "WindowClosed"])

    @unittest.skipUnless(os.environ.get("SWIRL_CAPTURE_INSPECTOR"), "Set SWIRL_CAPTURE_INSPECTOR to the built C++ importer")
    def test_offline_cpp_import_and_existing_store_protection(self):
        self.run_capture("/gzip")
        index = cap.read_private(self.cache / "index.dpapi")
        path = self.cache / next(iter(index["entries"].values()))["file"]
        store = Path(self.temp.name) / "isolated-nodes.dpapi"
        before = sum(self.server.hits.values())
        result = cap.replay(path, os.environ["SWIRL_CAPTURE_INSPECTOR"], store)
        self.assertEqual(result["code"], "OfflineImportPassed")
        self.assertEqual(result["nodes"], 1)
        self.assertEqual(sum(self.server.hits.values()), before)
        self.assertTrue(store.read_bytes().startswith(b"SWIRLNODE1\n"))
        self.assertNotIn(b"example.org", store.read_bytes())
        with self.assertRaisesRegex(cap.CaptureError, "NewIsolatedStoreRequired"):
            cap.replay(path, os.environ["SWIRL_CAPTURE_INSPECTOR"], store)


if __name__ == "__main__":
    unittest.main(verbosity=2)
