#pragma once
#include <QObject>
#include <QJsonObject>
#include <QLockFile>
#include <memory>
#include <optional>

struct SystemProxyState {
    quint32 flags=1;
    QString server, bypass, pac;
    bool operator==(const SystemProxyState &) const = default;
    QJsonObject json() const;
    static SystemProxyState fromJson(const QJsonObject &);
};
class SystemProxyBackend {
public:
    virtual ~SystemProxyBackend()=default;
    virtual bool read(SystemProxyState &,QString &error)=0;
    virtual bool write(const SystemProxyState &,QString &error)=0;
};
// A lease on WinINet settings. Restore only settings still owned by this lease.
class SystemProxy final : public QObject {
    Q_OBJECT
public:
    explicit SystemProxy(bool native=true, QObject *parent=nullptr,
                         std::unique_ptr<SystemProxyBackend> backend={},QString journal={});
    ~SystemProxy() override;
    bool enable(int port);
    bool disable();
    bool enabled() const {return m_enabled;}
    QString error() const {return m_error;}
    void refresh();
signals:
    void changed();
private:
    bool recover();
    bool saveJournal();
    void release();
    std::unique_ptr<SystemProxyBackend> m_backend;
    std::unique_ptr<QLockFile> m_lock;
    QString m_journal,m_error;
    std::optional<SystemProxyState> m_before;
    SystemProxyState m_applied;
    bool m_enabled=false;
};
