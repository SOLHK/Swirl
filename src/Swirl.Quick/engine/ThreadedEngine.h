#pragma once
#include "SwirlEngineManager.h"
#include <QThread>

// Production facade: all listeners, sockets, DNS and engine control live on a
// dedicated event loop. QML receives immutable snapshots on its own thread.
class ThreadedEngine final : public ProxyEngine {
public:
    ThreadedEngine() {
        m_context=new QObject;
        m_context->moveToThread(&m_thread);
        connect(&m_thread,&QThread::finished,m_context,&QObject::deleteLater);
        connect(&m_thread,&QThread::started,m_context,[this]{
            m_engine=new SwirlEngineManager(m_context);
            connect(m_engine,&ProxyEngine::statusChanged,m_context,[this]{
                const auto status=m_engine->status();const auto summary=m_engine->configurationSummary();
                const auto rules=m_engine->routingRules();const auto epoch=m_workerEpoch;
                QMetaObject::invokeMethod(this,[this,status,summary,rules,epoch]{
                    if(epoch!=m_epoch)return;
                    m_status=status;m_summary=summary;m_rules=rules;emit statusChanged();
                },Qt::QueuedConnection);
            });
            connect(m_engine,&ProxyEngine::diagnostic,m_context,[this](const QString &module,const QString &code,const QString &message){
                QMetaObject::invokeMethod(this,[this,module,code,message]{emit diagnostic(module,code,message);},Qt::QueuedConnection);
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
        QMetaObject::invokeMethod(m_context,[this,options,epoch]{m_workerEpoch=epoch;m_engine->start(options);},Qt::QueuedConnection);
    }
    void stop() override {
        const auto epoch=++m_epoch;m_status.state=State::Stopping;emit statusChanged();
        QMetaObject::invokeMethod(m_context,[this,epoch]{m_workerEpoch=epoch;m_engine->stop();
            const auto status=m_engine->status();
            QMetaObject::invokeMethod(this,[this,status,epoch]{if(epoch==m_epoch){m_status=status;emit statusChanged();}},Qt::QueuedConnection);},Qt::QueuedConnection);
    }
    void refresh() override {post([](auto *engine){engine->refresh();});}
    void selectNode(const QString &id) override {post([id](auto *engine){engine->selectNode(id);});}
    void probeNode(const QUrl &url) override {post([url](auto *engine){engine->probeNode(url);});}
    void setRoutingMode(const QString &mode) override {post([mode](auto *engine){engine->setRoutingMode(mode);});}
    Status status() const override{return m_status;}
    QString configurationSummary() const override{return m_summary;}
    QVariantList routingRules() const override{return m_rules;}
private:
    template<class F> void post(F action){QMetaObject::invokeMethod(m_context,[this,action]{action(m_engine);},Qt::QueuedConnection);}
    QThread m_thread;
    QObject *m_context=nullptr;
    SwirlEngineManager *m_engine=nullptr; // Worker thread only.
    Status m_status;
    QString m_summary;
    QVariantList m_rules;
    quint64 m_epoch=0,m_workerEpoch=0;
};
