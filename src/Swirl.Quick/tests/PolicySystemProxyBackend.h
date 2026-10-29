#pragma once

#include "engine/SystemProxySession.h"

// A per-controller adapter for native UI acceptance. It models ownership and
// restoration entirely in memory; it never calls WinINET, the registry, a
// recovery journal, or the independent production guard.
class PolicySystemProxyBackend final : public SystemProxySession::Backend {
public:
    explicit PolicySystemProxyBackend(bool externalEnabled = true) {
        m_state.systemEnabled = externalEnabled;
    }

    State refresh() override {
        ++refreshCalls;
        return m_state;
    }

    State enable(int port, qint64 pid) override {
        ++enableCalls;
        lastPort = port;
        lastPid = pid;
        if (port < 1 || port > 65535 || pid < 1) {
            m_state.error = QStringLiteral("Invalid isolated proxy endpoint");
            return m_state;
        }
        if (!m_state.owned) {
            m_original = m_state;
            ++takeoverCalls;
        }
        m_state.enabled = true;
        m_state.owned = true;
        m_state.systemEnabled = true;
        m_state.stateDiffers = false;
        m_state.readError.clear();
        m_state.error.clear();
        return m_state;
    }

    State disable() override {
        ++disableCalls;
        if (m_state.owned) {
            m_state = m_original;
            ++restoreCalls;
        }
        return m_state;
    }

    State current() const { return m_state; }
    int refreshCalls = 0;
    int enableCalls = 0;
    int takeoverCalls = 0;
    int disableCalls = 0;
    int restoreCalls = 0;
    int lastPort = 0;
    qint64 lastPid = 0;

private:
    State m_state;
    State m_original;
};
