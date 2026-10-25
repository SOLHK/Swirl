#pragma once
#include "RustCoreEngine.h"
#include <QThread>
#include <atomic>

// Production facade: all listeners, sockets, DNS and engine control live on a
// dedicated event loop. QML receives immutable snapshots on its own thread.
class ThreadedEngine final : public ProxyEngine {
public:
    explicit ThreadedEngine(QObject *parent=nullptr):ProxyEngine(parent) {
        m_context=new QObject;
        m_context->moveToThread(&m_thread);
        connect(&m_thread,&QThread::finished,m_context,&QObject::deleteLater);
        connect(&m_thread,&QThread::started,m_context,[this]{
            m_engine=new RustCoreEngine(m_context);
            connect(m_engine,&ProxyEngine::statusChanged,m_context,[this]{
                auto status=m_engine->status();const auto summary=m_engine->configurationSummary();
                status.probeFailureStage=m_engine->probeFailureStage();
                status.probeOutboundConnectMs=m_engine->probeOutboundConnectMs();
                status.probeOriginTlsMs=m_engine->probeOriginTlsMs();
                status.probeRequestTag=m_workerProbeTag;
                const auto rules=m_engine->routingRules();const auto epoch=m_workerEpoch;
                QMetaObject::invokeMethod(this,[this,status,summary,rules,epoch]{
                    if(epoch!=m_epoch)return;
                    m_status=status;m_summary=summary;m_rules=rules;emit statusChanged();
                },Qt::QueuedConnection);
            });
            connect(m_engine,&ProxyEngine::diagnostic,m_context,[this](const QString &module,const QString &code,const QString &message){
                const auto epoch=m_workerEpoch;
                QMetaObject::invokeMethod(this,[this,module,code,message,epoch]{if(epoch==m_epoch)emit diagnostic(module,code,message);},Qt::QueuedConnection);
            });
            connect(m_engine,&ProxyEngine::configurationCommandFinished,m_context,[this](const QString &requestId,const QJsonObject &response){
                const auto epoch=m_workerEpoch;
                QMetaObject::invokeMethod(this,[this,requestId,response,epoch]{if(epoch==m_epoch)emit configurationCommandFinished(requestId,response);},Qt::QueuedConnection);
            });
        });
        m_thread.setObjectName("Swirl network");m_thread.start();
    }
    ~ThreadedEngine() override {
        QMetaObject::invokeMethod(m_context,[this]{delete m_engine;m_engine=nullptr;m_thread.quit();},Qt::QueuedConnection);
        // Engine stop is asynchronous during normal shutdown. Destruction is
        // a final safety net; never terminate a thread holding network state.
        m_thread.wait();
    }
    void start(const EngineStartOptions &options) override {
        const auto epoch=++m_epoch;m_status.state=State::Starting;emit statusChanged();
        QMetaObject::invokeMethod(m_context,[this,options,epoch]{if(epoch!=m_epoch)return;m_workerEpoch=epoch;m_workerProbeTag=0;m_engine->start(options);},Qt::QueuedConnection);
    }
    void stop() override {
        const auto epoch=++m_epoch;m_status.state=State::Stopping;emit statusChanged();
        // An explicit stop remains ordered before a subsequently queued start.
        // Suppress stale snapshots, not the resource-release operation itself.
        QMetaObject::invokeMethod(m_context,[this,epoch]{m_workerEpoch=epoch;m_workerProbeTag=0;m_engine->stop();
            const auto status=m_engine->status();
            QMetaObject::invokeMethod(this,[this,status,epoch]{if(epoch==m_epoch){m_status=status;emit statusChanged();}},Qt::QueuedConnection);},Qt::QueuedConnection);
    }
    void refresh() override {post([](auto *engine){engine->refresh();});}
    void selectNode(const QString &id) override {post([this,id](auto *engine){m_workerProbeTag=0;engine->selectNode(id);});}
    void probeNode(const QUrl &url) override {probeNodeTagged(url,0);}
    void probeNodeTagged(const QUrl &url,quint64 tag) override {
        post([this,url,tag](auto *engine){
            const auto current=engine->status();
            if(!current.apiHealthy||current.nodeBusy){
                const auto epoch=m_workerEpoch;
                const auto code=current.nodeBusy?QStringLiteral("probe-busy"):QStringLiteral("core-unavailable");
                QMetaObject::invokeMethod(this,[this,epoch,tag,code]{if(epoch==m_epoch)emit probeRequestRejected(tag,code);},Qt::QueuedConnection);
                return;
            }
            m_workerProbeTag=tag;engine->probeNode(url);
        });
    }
    void setRoutingMode(const QString &mode) override {post([this,mode](auto *engine){m_workerProbeTag=0;engine->setRoutingMode(mode);});}
    void configurationCommand(const QJsonObject &command) override {post([command](auto *engine){engine->configurationCommand(command);});}
    Status status() const override{return m_status;}
    QString configurationSummary() const override{return m_summary;}
    QVariantList routingRules() const override{return m_rules;}
    QString probeFailureStage() const override{return m_status.probeFailureStage;}
    qint64 probeOutboundConnectMs() const override{return m_status.probeOutboundConnectMs;}
    qint64 probeOriginTlsMs() const override{return m_status.probeOriginTlsMs;}
private:
    template<class F> void post(F action){
        const auto epoch=m_epoch.load();
        QMetaObject::invokeMethod(m_context,[this,action,epoch]{if(epoch==m_epoch)action(m_engine);},Qt::QueuedConnection);
    }
    QThread m_thread;
    QObject *m_context=nullptr;
    RustCoreEngine *m_engine=nullptr; // Worker thread only.
    Status m_status;
    QString m_summary;
    QVariantList m_rules;
    std::atomic<quint64> m_epoch{0};
    quint64 m_workerEpoch=0;
    quint64 m_workerProbeTag=0;
};
