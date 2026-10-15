#pragma once
#include <QObject>
#include <QSslCertificate>
#include <QSslKey>
#include <QHash>
#include <QUrl>
#include <memory>

class TlsCertificateService final : public QObject {
    Q_OBJECT
    Q_PROPERTY(bool ready READ ready NOTIFY changed)
    Q_PROPERTY(bool skipServerVerification READ skipServerVerification WRITE setSkipServerVerification NOTIFY changed)
    Q_PROPERTY(bool http2Enabled READ http2Enabled WRITE setHttp2Enabled NOTIFY changed)
    Q_PROPERTY(bool enabled READ enabled WRITE setEnabled NOTIFY changed)
    Q_PROPERTY(bool trusted READ trusted NOTIFY changed)
    Q_PROPERTY(QString error READ error NOTIFY changed)
    Q_PROPERTY(QString fingerprint READ fingerprint NOTIFY changed)
    Q_PROPERTY(QStringList hostnames READ hostnames WRITE setHostnames NOTIFY changed)
public:
    struct Identity { QSslCertificate certificate; QSslKey key; };
    explicit TlsCertificateService(QString path={},QObject *parent=nullptr);
    ~TlsCertificateService() override;
    bool ready() const { return !m_certificate.isNull(); }
    bool skipServerVerification() const { return m_skipServerVerification; }
    void setSkipServerVerification(bool enabled) { m_skipServerVerification=enabled;emit changed(); }
    bool http2Enabled() const { return m_http2Enabled; }
    void setHttp2Enabled(bool enabled) { m_http2Enabled=enabled;emit changed(); }
    bool enabled() const { return m_enabled; }
    bool trusted() const;
    QString error() const { return m_error; }
    QString fingerprint() const;
    QStringList hostnames() const { return m_hostnames; }
    QSslCertificate certificate() const { return m_certificate; }
    void setEnabled(bool enabled);
    void setHostnames(const QStringList &hostnames);
    Q_INVOKABLE bool addHostname(const QString &hostname);
    Q_INVOKABLE void removeHostname(const QString &hostname);
    bool shouldIntercept(const QString &host) const;
    bool matchesHost(const QString &host) const;
    Identity identityFor(const QString &host);
    Q_INVOKABLE bool generate();
    Q_INVOKABLE bool importPkcs12(const QUrl &source,const QString &password);
    Q_INVOKABLE bool installTrust();
    Q_INVOKABLE bool exportCertificate(const QUrl &destination);
signals:
    void changed();
private:
    struct Impl;
    std::unique_ptr<Impl> d;
    bool persist();
    void load();
    QString m_path,m_error;
    bool m_enabled=false,m_http2Enabled=false,m_skipServerVerification=false;
    QStringList m_hostnames;
    QSslCertificate m_certificate;
    QHash<QString,Identity> m_cache;
};
