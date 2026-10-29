#pragma once

// Test-only reservations for a mixed TCP/UDP listener and its TCP controller.
// A free TCP port alone is not necessarily bindable by UDP (notably Windows
// excluded-port ranges). Keep all three sockets open while choosing the tuple;
// callers release it immediately before starting their controlled child.
#include <QHostAddress>
#include <QNetworkProxy>
#include <QTcpServer>
#include <QUdpSocket>

class LoopbackPortLease final {
public:
    bool reserve() {
        release();
        m_controlPort = 0;
        m_proxyPort = 0;
        m_error.clear();
        m_control.setProxy(QNetworkProxy::NoProxy);
        m_tcp.setProxy(QNetworkProxy::NoProxy);
        m_udp.setProxy(QNetworkProxy::NoProxy);
        if (!m_control.listen(QHostAddress::LocalHost, 0)) {
            m_error = m_control.errorString();
            return false;
        }
        for (int attempt = 0; attempt < 32; ++attempt) {
            if (!m_udp.bind(QHostAddress::LocalHost, 0, QUdpSocket::DontShareAddress)) {
                m_error = m_udp.errorString();
                break;
            }
            const auto candidate = m_udp.localPort();
            if (candidate != m_control.serverPort() &&
                m_tcp.listen(QHostAddress::LocalHost, candidate)) {
                m_controlPort = m_control.serverPort();
                m_proxyPort = candidate;
                return true;
            }
            m_error = QStringLiteral("No distinct loopback TCP/UDP test port: ") + m_tcp.errorString();
            m_tcp.close();
            m_udp.close();
        }
        release();
        return false;
    }

    void release() {
        m_tcp.close();
        m_udp.close();
        m_control.close();
    }

    quint16 controlPort() const { return m_controlPort; }
    quint16 proxyPort() const { return m_proxyPort; }
    QString errorString() const { return m_error; }

private:
    QTcpServer m_control;
    QTcpServer m_tcp;
    QUdpSocket m_udp;
    quint16 m_controlPort = 0;
    quint16 m_proxyPort = 0;
    QString m_error;
};
