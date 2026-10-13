#pragma once
#include <QObject>
#include <QVariantMap>
#include <QStringList>
#include <QNetworkAccessManager>
#include <QPointer>
#include <QNetworkReply>
#include <QTimer>

// Two explicit transports: a failing proxy must never silently fall back to direct.
class NetworkDiagnostics final : public QObject {
    Q_OBJECT
    Q_PROPERTY(QVariantMap directResult READ directResult NOTIFY changed)
    Q_PROPERTY(QVariantMap proxyResult READ proxyResult NOTIFY changed)
    Q_PROPERTY(QVariantMap currentResult READ currentResult NOTIFY changed)
    Q_PROPERTY(bool busy READ busy NOTIFY changed)
    Q_PROPERTY(QStringList log READ log NOTIFY changed)
    Q_PROPERTY(QVariantMap dnsResult READ dnsResult NOTIFY changed)
public:
    explicit NetworkDiagnostics(QObject *parent=nullptr);
    ~NetworkDiagnostics() override;
    QVariantMap directResult() const {return m_direct.result;}
    QVariantMap proxyResult() const {return m_proxy.result;}
    QVariantMap currentResult() const {return m_proxyPort?m_proxy.result:m_direct.result;}
    bool busy() const {return m_direct.pending || m_proxy.pending;}
    QStringList log() const {return m_log;}
    QVariantMap dnsResult() const {return m_dns;}
    void setProxyPort(int port);
    // Endpoint injection allows deterministic local tests without internet access.
    void setEndpoints(const QList<QUrl> &urls) {m_endpoints=urls;}
    void setTimeout(int ms) {m_timeout=ms;}
    Q_INVOKABLE void start();
    Q_INVOKABLE void cancel();
    void invalidate();
    static QString classify(QNetworkReply::NetworkError error, bool timeout, int code, const QByteArray &body);
signals:
    void changed();
private:
    struct Route {
        QNetworkAccessManager network;
        QPointer<QNetworkReply> reply;
        QVariantMap result{{"state",QStringLiteral("尚未检测")},{"latency",-1}};
        int endpoint=0;
        bool pending=false;
    };
    void next(Route &route, bool proxy);
    void reset(Route &route, const QString &state);
    Route m_direct, m_proxy;
    QList<QUrl> m_endpoints;
    QStringList m_log;
    int m_proxyPort=0, m_timeout=5000;
    int m_lookup=-1;
    quint64 m_dnsGeneration=0;
    QVariantMap m_dns{{"state",QStringLiteral("尚未检测")},{"latency",-1}};
};
