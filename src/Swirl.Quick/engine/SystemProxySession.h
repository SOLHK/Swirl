#pragma once
#include <QObject>
#include <QJsonObject>
#include <QTimer>
#include <QProcess>
#include <QVariantMap>

// Current-user WinINET connection settings plus their legacy registry view.
// The independent guard compares both stores before restoring their snapshots.
class SystemProxySession final : public QObject {
    Q_OBJECT
    Q_PROPERTY(bool enabled READ enabled NOTIFY changed)
    Q_PROPERTY(bool owned READ owned NOTIFY changed)
    Q_PROPERTY(bool systemEnabled READ systemEnabled NOTIFY changed)
    Q_PROPERTY(bool stateDiffers READ stateDiffers NOTIFY changed)
    Q_PROPERTY(QString stateReadError READ stateReadError NOTIFY changed)
    Q_PROPERTY(QString error READ error NOTIFY changed)
public:
    explicit SystemProxySession(QObject *parent=nullptr, QString journal={});
    ~SystemProxySession() override;
    bool enabled() const { return m_enabled; }
    bool owned() const { return m_owned; }
    bool systemEnabled() const { return m_systemEnabled; }
    bool stateDiffers() const { return m_stateDiffers; }
    QString stateReadError() const { return m_readError; }
    QVariantMap diagnosticState() const;
    QString error() const { return m_error; }
    bool enable(int port, qint64 enginePid);
    Q_INVOKABLE bool disable();
    bool turnOffSystemProxy(); // Explicit user action; unlike release, leaves Windows proxy off.
    Q_INVOKABLE void refresh();
    static QString journalPath();
    static QJsonObject snapshot(QString *error=nullptr);
    static bool apply(const QJsonObject &, QString *error=nullptr);
    static bool recover(const QString &journal, QString *error=nullptr, bool requireDeadOwner=true, const QString &expectedSession={});
    static int guard(const QString &journal);
signals:
    void changed();
private:
    QString m_journal, m_error, m_session, m_readError;
    bool m_enabled=false, m_owned=false;
    bool m_systemEnabled=false, m_stateDiffers=false;
    QTimer m_poll;
    QProcess m_guard;
};
