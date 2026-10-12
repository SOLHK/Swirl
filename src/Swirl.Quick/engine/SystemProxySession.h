#pragma once
#include <QObject>
#include <QJsonObject>
#include <QTimer>
#include <QProcess>

// Current-user WinINET only. The independently running guard survives loss of
// the GUI; both paths compare all owned settings before restoring a snapshot.
class SystemProxySession final : public QObject {
    Q_OBJECT
    Q_PROPERTY(bool enabled READ enabled NOTIFY changed)
    Q_PROPERTY(bool owned READ owned NOTIFY changed)
    Q_PROPERTY(QString error READ error NOTIFY changed)
public:
    explicit SystemProxySession(QObject *parent=nullptr, QString journal={});
    ~SystemProxySession() override;
    bool enabled() const { return m_enabled; }
    bool owned() const { return m_owned; }
    QString error() const { return m_error; }
    bool enable(int port, qint64 enginePid);
    Q_INVOKABLE bool disable();
    Q_INVOKABLE void refresh();
    static QString journalPath();
    static QJsonObject snapshot(QString *error=nullptr);
    static bool apply(const QJsonObject &, QString *error=nullptr);
    static bool recover(const QString &journal, QString *error=nullptr, bool requireDeadOwner=true, const QString &expectedSession={});
    static int guard(const QString &journal);
signals:
    void changed();
private:
    QString m_journal, m_error, m_session;
    bool m_enabled=false, m_owned=false;
    QTimer m_poll;
    QProcess m_guard;
};
