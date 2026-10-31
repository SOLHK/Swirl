#pragma once
#include <QObject>
#include <QUdpSocket>
#include <QTimer>
#include <QHash>
#include <QHostAddress>
#include <QVariantList>
#include <QElapsedTimer>
#include <QJsonObject>
class DhcpServer final : public QObject {
    Q_OBJECT
public:
    struct Config { QHostAddress gateway,first,last,dns;int prefix=24,interfaceIndex=0,leaseSeconds=3600;bool operator==(const Config &) const = default; };
    explicit DhcpServer(bool isolated=false,QObject *parent=nullptr);
    ~DhcpServer() override;
    void setLeaseStorePath(const QString &path){m_leasePath=path;}
    bool configure(const Config &config);
    bool start(const Config &config);
    void stop();
    bool running() const {return m_socket.state()==QAbstractSocket::BoundState;}
    quint16 port() const {return m_socket.localPort();}
    QString error() const {return m_error;}
    QVariantList leases() const;
    bool reserve(const QString &mac,const QString &ip,const QString &name);
    bool replaceReservations(const QVariantList &rows);
    void clearReservations();
    QVariantList reservations() const;
    static bool validate(const Config &config,QString *error=nullptr);
    // Uses parsed option 53, never a byte search through client-supplied options.
    static QHostAddress replyAddress(const QByteArray &request,const QByteArray &response);
    // One-use Winsock receipt for the native helper worker. It carries no
    // authority to start a gateway and is never persisted in configuration.
    QJsonObject ownerReceipt(quint32 helperWorkerPid,QString *error=nullptr) const;
signals:
    void changed();
private:
    struct Lease {quint32 ip=0;QString mac,name; qint64 expires=0,lastSeen=0;bool committed=false;};
    void receive();
    QByteArray reply(const QByteArray &request);
    quint32 allocate(const QByteArray &client,quint32 preferred);
    bool available(quint32 address,const QByteArray &client) const;
    void expire();
    bool loadLeases();
    bool saveLeases();
    bool bindProductionSocket();
    bool m_isolated=false;
    bool m_nativeWinsock=false;
    QUdpSocket m_socket;QTimer m_expiry;
    Config m_config;QString m_error,m_leasePath;
    QHash<QByteArray,Lease> m_leases;
    QHash<quint32,qint64> m_quarantine;
    QHash<QString,QVariantMap> m_reservations;
    QElapsedTimer m_rateClock;
    qint64 m_rateSecond=-1;
    int m_requestsThisSecond=0;
    QHash<QByteArray,int> m_clientRequests;
};
