#pragma once

#include <QJsonObject>
#include <QString>
#include <memory>

// Called serially by RustCoreEngine's worker thread, never the GUI thread.
class NativeTunBrokerClient final {
public:
    NativeTunBrokerClient();
    ~NativeTunBrokerClient();
    NativeTunBrokerClient(const NativeTunBrokerClient &) = delete;
    NativeTunBrokerClient &operator=(const NativeTunBrokerClient &) = delete;

    bool launch(QString *error);
    QJsonObject command(const QJsonObject &request);
    // Transport shutdown only; stop/recover receipts prove network restoration.
    // A timeout retains the live process identity for a later close attempt.
    bool close(QString *error = nullptr);
    // Process liveness, including an EOF-disconnected broker still recovering.
    bool running() const;
    qint64 processId() const;

private:
    struct Impl;
    std::unique_ptr<Impl> m_impl;
};
