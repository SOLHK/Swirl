#pragma once
#include "SwirlProxyEngine.h"
#include "MihomoAdapter.h"

// The sole runtime selector. Unsupported capabilities retain the selected node
// and use the pinned compatibility engine; failure never implies DIRECT.
class SwirlEngineManager final : public ProxyEngine {
    Q_OBJECT
public:
    explicit SwirlEngineManager(QObject *parent=nullptr);
    ~SwirlEngineManager() override;
    void start(const EngineStartOptions &) override;
    void stop() override;
    void refresh() override;
    void selectNode(const QString &) override;
    void probeNode(const QUrl &) override;
    void setRoutingMode(const QString &) override;
    Status status() const override;
    QString configurationSummary() const override;
    QVariantList routingRules() const override;
private:
    SwirlProxyEngine m_native;
    MihomoAdapter m_compatibility;
    ProxyEngine *m_active=nullptr,*m_pending=nullptr;
    EngineStartOptions m_options;
    QString m_reason,m_session;
    QUrl m_probe;
    bool m_transition=false,m_fallback=false;
    quint64 m_generation=0;
    void activate(ProxyEngine *);
    void changed(ProxyEngine *);
    void fallback(const QString &);
};
