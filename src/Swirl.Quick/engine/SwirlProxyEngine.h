#pragma once
#include "ProxyEngine.h"
#include <memory>
class SwirlProxyEngine final:public ProxyEngine {
    Q_OBJECT
public:
    explicit SwirlProxyEngine(QObject *parent=nullptr);
    ~SwirlProxyEngine() override;
    void start(const EngineStartOptions &) override;
    void stop() override;
    void refresh() override;
    void selectNode(const QString &) override;
    void probeNode(const QUrl &) override;
    void setRoutingMode(const QString &) override;
    Status status()const override;
    QString configurationSummary()const override;
    qsizetype activeStreamCount()const;
    qsizetype activeConnectionCount()const;
private:
    struct Private;
    std::unique_ptr<Private> d;
};
