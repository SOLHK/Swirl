#pragma once
#include <QObject>
#include <QJsonObject>
#include <QTimer>
#include <QProcess>
#include <QVariantMap>
#include <QDeadlineTimer>
#include <functional>
#include <memory>
class QLockFile;

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
    Q_PROPERTY(bool busy READ busy NOTIFY changed)
public:
    // C++ constructor injection keeps isolated controller tests away from the
    // user's OS settings. A null backend always uses the native journal/guard.
    class Backend {
    public:
        struct State {
            bool enabled=false,owned=false,systemEnabled=false,stateDiffers=false;
            QString readError,error;
        };
        virtual ~Backend()=default;
        virtual State refresh()=0;
        virtual State enable(int port,qint64 enginePid)=0;
        virtual State disable()=0;
        // A platform adapter may need an asynchronous readiness handshake.
        // Each poll must return promptly; no OS settings change before Ready.
        enum class Preparation { Pending, Ready, Failed };
        virtual Preparation prepareEnable(int,qint64,QString *) { return Preparation::Ready; }
        virtual Preparation prepareDisable(QString *) { return Preparation::Ready; }
        virtual void cancelEnable() {}
    };
    explicit SystemProxySession(QObject *parent=nullptr, QString journal={},std::unique_ptr<Backend> backend={});
    ~SystemProxySession() override;
    bool enabled() const { return m_enabled; }
    bool owned() const { return m_owned; }
    bool systemEnabled() const { return m_systemEnabled; }
    bool stateDiffers() const { return m_stateDiffers; }
    QString stateReadError() const { return m_readError; }
    QVariantMap diagnosticState() const;
    QString error() const { return m_error; }
    Backend *backend() const { return m_backend.get(); }
    bool busy() const { return m_enableRequest!=0||m_releasePending; }
    quint64 requestEnable(int port,qint64 enginePid,std::function<bool()> stillValid={});
    void cancelEnable();
    // Synchronous entry point is for standalone acceptance tools only.
    // Product UI calls requestEnable so lock/guard waits yield to Qt.
    bool enable(int port, qint64 enginePid);
    Q_INVOKABLE bool disable();
    bool turnOffSystemProxy(); // Explicit user action; unlike release, leaves Windows proxy off.
    Q_INVOKABLE void refresh();
    static QString journalPath();
    static QJsonObject snapshot(QString *error=nullptr);
    static bool apply(const QJsonObject &, QString *error=nullptr);
    static bool recover(const QString &journal, QString *error=nullptr, bool requireDeadOwner=true, const QString &expectedSession={},int lockTimeout=1000,bool *contended=nullptr);
    static int guard(const QString &journal);
signals:
    void changed();
    void enableFinished(quint64 request,bool success);
    void releaseFinished(bool success);
private:
    void advanceEnable();
    void finishEnable(bool success,const QString &error={});
    void retryRelease();
    void awaitRelease();
    bool commitPreparedEnable(const QJsonObject &record);
    void adoptBackendState(const Backend::State &state);
    std::unique_ptr<Backend> m_backend;
    QString m_journal, m_error, m_session, m_readError;
    bool m_enabled=false, m_owned=false;
    bool m_systemEnabled=false, m_stateDiffers=false;
    QTimer m_poll;
    QProcess m_guard;
    QTimer m_enableTimer,m_releaseTimer;
    QDeadlineTimer m_enableDeadline,m_releaseDeadline;
    quint64 m_nextRequest=0,m_enableRequest=0;
    int m_enablePort=0;
    qint64 m_enablePid=0;
    bool m_releasePending=false;
    QJsonObject m_preparedRecord;
    std::unique_ptr<QLockFile> m_enableLock;
    std::function<bool()> m_stillValid;
};
