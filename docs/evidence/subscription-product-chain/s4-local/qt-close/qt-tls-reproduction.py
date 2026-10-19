import json
import sys
import tempfile
import time

sys.path.insert(0, '/tmp/swirl-qt-tls-repro')
sys.path.insert(0, '/workspace/scratch/ca6cd1f88f6f/Swirl/tools/tests')
from PySide6.QtCore import QCoreApplication, QUrl
from PySide6.QtNetwork import QAbstractSocket, QNetworkAccessManager, QNetworkProxy, QNetworkRequest, QSslCertificate, QSslConfiguration, QSslSocket
from PySide6.QtTest import QTest
import shiboken6
from test_product_subscription_chain import Origin, certificates

app = QCoreApplication([])
print('Qt TLS', QSslSocket.activeBackend(), QSslSocket.sslLibraryVersionString())
for invalid, drain in ((False, False), (False, True), (True, False), (True, True)):
    with tempfile.TemporaryDirectory() as folder:
        context, _, pem = certificates(folder)
        origin = Origin(context=context)
        client = QNetworkAccessManager()
        client.setProxy(QNetworkProxy(QNetworkProxy.NoProxy))
        request = QNetworkRequest(QUrl(f'https://localhost:{origin.port}/probe'))
        request.setRawHeader(b'Connection', b'close')
        request.setAttribute(QNetworkRequest.Http2AllowedAttribute, False)
        request.setTransferTimeout(5000)
        tls = QSslConfiguration.defaultConfiguration()
        tls.setCaCertificates(QSslCertificate.fromData(pem.encode()))
        tls.setPeerVerifyMode(QSslSocket.VerifyPeer)
        request.setSslConfiguration(tls)
        if invalid:
            request.setPeerVerifyName('wrong.fixture.invalid')
        reply = client.get(request)
        deadline = time.monotonic() + 6
        while not reply.isFinished() and time.monotonic() < deadline:
            QTest.qWait(1)
        result = {'invalid': invalid, 'drain': drain,
                  'reply_error': str(reply.error()), 'body': bytes(reply.readAll()).decode()}
        if drain:
            deadline = time.monotonic() + 2
            while not origin.tls_closed and not origin.errors and time.monotonic() < deadline:
                QTest.qWait(1)
        shiboken6.delete(client)
        QTest.qWait(100)
        result.update(tls_closed=origin.tls_closed, sni=origin.sni, errors=origin.errors,
                      request_count=len(origin.requests))
        print(json.dumps(result))
        try:
            origin.close()
        except AssertionError:
            pass

for invalid in (False, True):
    with tempfile.TemporaryDirectory() as folder:
        context, _, pem = certificates(folder)
        origin = Origin(context=context)
        client = QSslSocket()
        client.setProxy(QNetworkProxy(QNetworkProxy.NoProxy))
        tls = QSslConfiguration.defaultConfiguration()
        tls.setCaCertificates(QSslCertificate.fromData(pem.encode()))
        tls.setPeerVerifyMode(QSslSocket.VerifyPeer)
        client.setSslConfiguration(tls)
        if invalid:
            client.setPeerVerifyName('wrong.fixture.invalid')
        client.connectToHostEncrypted('localhost', origin.port)
        deadline = time.monotonic() + 6
        while not client.isEncrypted() and client.state() != QAbstractSocket.UnconnectedState and time.monotonic() < deadline:
            QTest.qWait(1)
        response = b''
        if client.isEncrypted():
            client.write(b'GET /ssl-socket HTTP/1.1\r\nHost: localhost\r\nConnection: close\r\n\r\n')
            while not response.endswith(b'product-origin-ok:/ssl-socket') and time.monotonic() < deadline:
                QTest.qWait(1)
                response += bytes(client.readAll())
            client.disconnectFromHost()
            while client.state() != QAbstractSocket.UnconnectedState and time.monotonic() < deadline:
                QTest.qWait(1)
        close_deadline = time.monotonic() + 2
        while not invalid and not origin.tls_closed and not origin.errors and time.monotonic() < close_deadline:
            QTest.qWait(1)
            time.sleep(0.001)
        print(json.dumps({'mode': 'explicit-ssl-socket', 'invalid': invalid,
                          'socket_error': str(client.error()), 'state': str(client.state()),
                          'body': response.decode(), 'tls_closed': origin.tls_closed,
                          'sni': origin.sni, 'errors': origin.errors,
                          'request_count': len(origin.requests)}))
        shiboken6.delete(client)
        try:
            origin.close()
        except AssertionError:
            pass
