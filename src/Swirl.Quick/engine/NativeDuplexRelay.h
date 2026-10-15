#pragma once
#include <QObject>
#include <QByteArray>
#include <QPointer>
#include <functional>
#include <memory>
class QTcpSocket;

// Swirl's data-plane relay preserves TCP read EOF separately from write EOF.
// It is attached only after the existing native protocol handshake completes.
class NativeDuplexRelay final : public QObject {
public:
    explicit NativeDuplexRelay(QObject *parent=nullptr);
    ~NativeDuplexRelay() override;
    bool attach(QTcpSocket *client,QTcpSocket *upstream,QByteArray initialUp,QByteArray initialDown);
    void cancel();
    static void configureKeepAlive(QTcpSocket *socket);
    std::function<void(qint64,qint64)> transferred;
    std::function<void(const QString &)> finished;
private:
    struct Private;
    std::unique_ptr<Private> d;
};
