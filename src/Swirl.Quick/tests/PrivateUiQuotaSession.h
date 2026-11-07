#pragma once

#include "engine/RustCoreLibrary.h"
#include <QByteArray>
#include <QJsonObject>

struct ControlledNodeSession;

// QA-only pipe/ABI boundary. It never reads a private subscription or enables
// product startup. Rust owns the one process-global raw TCP quota.
class PrivateUiQuotaSession final {
public:
    ~PrivateUiQuotaSession();
    static int writeBuildIdentity();
    bool begin();
    bool fixtureReady(const ControlledNodeSession &session);
    bool finish();
private:
    RustCoreLibrary::Command m_command = nullptr;
    QJsonObject m_binding, m_grant;
    bool m_started = false, m_finished = false;
    QByteArray control(const char *operation) const;
    bool invoke(const QByteArray &, QByteArray *, QJsonObject *);
};
