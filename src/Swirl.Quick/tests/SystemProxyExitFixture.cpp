#include "SystemProxyExitFixture.h"
#include "SwirlBuildIdentity.h"
#include "app/StoragePaths.h"
#include "engine/EngineController.h"
#include <QCoreApplication>
#include <QDebug>
#include <QElapsedTimer>
#include <QFile>
#include <QJsonArray>
#include <QJsonDocument>
#include <QLocalServer>
#include <QLocalSocket>
#include <QNetworkProxy>
#include <QPointer>
#include <QQuickWindow>
#include <QSaveFile>
#include <QTcpServer>
#include <QTimer>

namespace {
bool writeReceipt(const QString &path,const QJsonObject &value) {
    QSaveFile file(path);file.setDirectWriteFallback(false);
    const auto bytes=QJsonDocument(value).toJson();
    return file.open(QIODevice::WriteOnly)&&file.write(bytes)==bytes.size()&&file.commit();
}

class ExitFixture final : public QObject {
public:
    ExitFixture(QQuickWindow *window,EngineController *controller,const QString &root)
        :QObject(QCoreApplication::instance()),m_window(window),m_controller(controller),m_root(root) {}

    bool start() {
        // Never substitute a memory adapter or open the normal user profile.
        if(m_controller->systemProxy()->backend()!=nullptr||m_root.isEmpty()
           ||SystemProxySession::journalPath()!=QDir(m_root).filePath("data/system-proxy.dpapi"))return false;
        m_initial=SystemProxySession::snapshot();
        if(m_initial.isEmpty()||m_controller->processAlive()||m_controller->policyBusy())return false;
        m_control.setSocketOptions(QLocalServer::UserAccessOption);
        if(!m_control.listen(SwirlSystemProxyExit::controlName(m_root)))return false;
        connect(&m_control,&QLocalServer::newConnection,this,[this]{
            while(auto *socket=m_control.nextPendingConnection()){
                socket->setReadBufferSize(16);
                connect(socket,&QLocalSocket::disconnected,socket,&QObject::deleteLater);
                const QPointer<QQuickWindow> window{m_window};
                connect(socket,&QLocalSocket::disconnected,this,[this,socket,window]{
                    if(!window||!socket->property("closeCommandAccepted").toBool())return;
                    m_closeAfterControlDisconnect=true;
                    // The client consumes CLOSING before closing its pipe.
                    // Keep the real root-window close/ShutdownCoordinator
                    // behind that boundary, not behind a nonblocking flush.
                    QTimer::singleShot(0,window.data(),[window]{if(window)window->close();});
                });
                connect(socket,&QLocalSocket::readyRead,socket,[this,socket]{
                    const auto bytes=socket->property("command").toByteArray()+socket->readAll();
                    if(bytes.size()>7||(!QByteArray("CLOSE\n").startsWith(bytes)
                        &&!QByteArray("STOP\n").startsWith(bytes)&&!QByteArray("STATUS\n").startsWith(bytes))){socket->abort();return;}
                    socket->setProperty("command",bytes);
                    if(bytes=="STATUS\n"){
                        const auto reply=QJsonDocument(normalStopState("normal-stop-status")).toJson(QJsonDocument::Compact)+"\n";
                        if(socket->write(reply)!=reply.size()){socket->abort();return;}
                        socket->flush();return;
                    }
                    if(bytes=="STOP\n"){
                        if(!m_ready||m_closeRequested||!m_controller->processAlive()||m_controller->systemProxyStopping()){
                            socket->abort();return;
                        }
                        if(socket->write("STOPPING\n")!=9){socket->abort();return;}
                        socket->flush();
                        QTimer::singleShot(0,this,[this]{
                            ++m_normalStopAttempts;m_normalStopLastReleaseFinished=false;
                            m_normalStopLastReleaseSucceeded=false;m_normalStopLastReleaseAlive=false;
                            m_normalStopElapsed.start();
                            // This is the same public command as the product's
                            // system-proxy capsule. The application stays alive.
                            m_controller->toggleSystemProxy();observeNormalStop();
                        });
                        return;
                    }
                    if(bytes!="CLOSE\n")return;
                    if(!m_ready||m_closeRequested){socket->abort();return;}
                    m_closeRequested=true;socket->setProperty("closeCommandAccepted",true);
                    // Server-side DisconnectNamedPipe may discard unread data,
                    // even after a successful Qt write/flush. All replies stay
                    // open until the client has consumed them and disconnects.
                    m_closeReplyWriteSucceeded=socket->write("CLOSING\n")==8;
                    if(!m_closeReplyWriteSucceeded){socket->abort();return;}
                    socket->flush();
                });
            }
        });
        connect(m_controller->systemProxy(),&SystemProxySession::releaseFinished,this,[this](bool success){
            if(m_normalStopAttempts&&!m_closeRequested){
                m_normalStopLastReleaseFinished=true;m_normalStopLastReleaseSucceeded=success;
                m_normalStopLastReleaseAlive=m_controller->processAlive()&&m_controller->apiHealthy();
                m_normalStopLastReleaseElapsed=m_normalStopElapsed.elapsed();
                m_normalStopRestoredAtRelease=SystemProxySession::snapshot()==m_initial;
                m_normalStopJournalAbsentAtRelease=!QFile::exists(SystemProxySession::journalPath());
                if(success)++m_normalStopReleaseSuccesses;else ++m_normalStopReleaseFailures;
                // EngineController queues its release continuation before this
                // observer. Record the retryable/finished state after it runs.
                QTimer::singleShot(0,this,[this]{observeNormalStop();});
            }
            if(!m_closeRequested)return;
            m_releaseFinished=true;m_releaseSucceeded=success;
            m_releaseWhileRuntimeAlive=m_controller->processAlive()&&m_controller->apiHealthy();
            m_restoredAtRelease=SystemProxySession::snapshot()==m_initial;
            m_journalAbsentAtRelease=!QFile::exists(SystemProxySession::journalPath());
        });
        connect(m_controller->systemProxy(),&SystemProxySession::changed,this,[this]{
            auto *proxy=m_controller->systemProxy();
            if(m_releaseWaitingObserved||!m_ready||!m_closeRequested||!proxy->owned()||!proxy->busy())return;
            m_releaseWaitingObserved=true;
            m_releaseWaitingRuntimeAlive=m_controller->processAlive();
            m_releaseWaitingRuntimeHealthy=m_controller->apiHealthy();
            auto report=common("release-waiting");
            report.insert("proxy_owned",proxy->owned());report.insert("proxy_busy",proxy->busy());
            report.insert("runtime_alive",m_releaseWaitingRuntimeAlive);
            report.insert("runtime_healthy",m_releaseWaitingRuntimeHealthy);
            report.insert("journal_present",QFile::exists(SystemProxySession::journalPath()));
            // An observer-only receipt lets the parent release its real file
            // lock after Pending actually occurred, without adding a sleep or
            // calling any production shutdown/recovery operation ourselves.
            if(!writeReceipt(SwirlSystemProxyExit::waitingPath(m_root),report))fail("release-waiting-receipt-write-failed");
        });
        connect(m_controller,&EngineController::statusChanged,this,[this]{observeReady();observeNormalStop();});
        connect(m_controller,&EngineController::policyApplyFinished,this,[this](const QString &,bool success){
            if(!success){fail("policy-save-failed");return;}
            if(m_requested)return;
            m_requested=true;m_controller->setSystemProxy(true);
        });
        connect(QCoreApplication::instance(),&QCoreApplication::aboutToQuit,this,[this]{finish();});
        m_watchdog.setSingleShot(true);
        connect(&m_watchdog,&QTimer::timeout,this,[this]{fail("fixture-watchdog");});
        m_watchdog.start(30000);

        QTcpServer reserve;reserve.setProxy(QNetworkProxy::NoProxy);
        if(!reserve.listen(QHostAddress::LocalHost))return false;
        const auto port=reserve.serverPort();reserve.close();
        m_controller->setProxyPort(port);
        // A fresh store has no committed V2 policy. Save the same explicit
        // direct-mode document accepted by the production policy coordinator;
        // an empty node selection must not grant an implicit DIRECT fallback.
        const QJsonObject policy{{"schema",2},{"mode","direct"},
            {"default_policy",QJsonObject{{"id","policy:default"},{"target",QJsonObject{{"kind","unconfigured"}}}}},
            {"service_policies",QJsonArray{}},{"groups",QJsonArray{}},{"explicit_direct_rules",QJsonArray{}},
            {"custom_rules",QJsonArray{}},{"missing_targets",QJsonArray{}}};
        if(!m_controller->applyPolicyDocument(policy.toVariantMap()))return false;
        return true;
    }
private:
    QJsonObject common(const char *phase) const {
        return {{"schema",1},{"source_sha",QStringLiteral(SWIRL_SOURCE_SHA)},
            {"phase",QString::fromLatin1(phase)},{"qt_version",QString::fromLatin1(qVersion())},
            {"pid",double(QCoreApplication::applicationPid())},
            {"runtime_pid",double(m_runtimePid)},{"rust_port",m_port},
            {"native_backend",m_controller->systemProxy()->backend()==nullptr},
            {"ready",m_ready},{"close_requested",m_closeRequested},
            {"fixture_failed",!m_failure.isEmpty()},{"failure_code",m_failure}};
    }
    QJsonObject normalStopState(const char *phase) const {
        auto report=common(phase);auto *proxy=m_controller->systemProxy();
        const auto snapshot=SystemProxySession::snapshot();
        report.insert("normal_stop_attempts",m_normalStopAttempts);
        report.insert("proxy_owned",proxy->owned());report.insert("proxy_busy",proxy->busy());
        report.insert("proxy_requested",m_controller->proxyRequested());
        report.insert("system_proxy_stopping",m_controller->systemProxyStopping());
        report.insert("system_proxy_busy",m_controller->systemProxyBusy());
        report.insert("runtime_alive",m_controller->processAlive());
        report.insert("runtime_healthy",m_controller->apiHealthy());
        report.insert("runtime_stopped",!m_controller->processAlive()&&!m_controller->busy());
        report.insert("initial_runtime_epoch",m_initialRuntimeEpoch);
        report.insert("runtime_epoch",m_controller->policyReceipt().value("engine_epoch").toString());
        report.insert("journal_present",QFile::exists(SystemProxySession::journalPath()));
        report.insert("native_snapshot_readable",!snapshot.isEmpty());
        report.insert("snapshot_restored",snapshot==m_initial);
        report.insert("window_visible",m_window->isVisible());
        report.insert("shutdown_coordinator_completed",QCoreApplication::instance()->property("shutdownDurationMs").isValid());
        report.insert("routing_error_present",!m_controller->routingError().isEmpty());
        report.insert("proxy_error_present",!proxy->error().isEmpty());
        report.insert("stop_release_finished",m_normalStopLastReleaseFinished);
        report.insert("stop_release_succeeded",m_normalStopLastReleaseSucceeded);
        report.insert("stop_release_while_runtime_alive",m_normalStopLastReleaseAlive);
        report.insert("stop_release_elapsed_ms",double(m_normalStopLastReleaseElapsed));
        report.insert("stop_release_successes",m_normalStopReleaseSuccesses);
        report.insert("stop_release_failures",m_normalStopReleaseFailures);
        report.insert("snapshot_restored_at_stop_release",m_normalStopRestoredAtRelease);
        report.insert("journal_absent_at_stop_release",m_normalStopJournalAbsentAtRelease);
        return report;
    }
    void observeNormalStop() {
        if(!m_normalStopAttempts||m_closeRequested||!m_failure.isEmpty())return;
        auto *proxy=m_controller->systemProxy();
        if(!m_normalStopWaitingRecorded&&proxy->owned()&&proxy->busy()){
            m_normalStopWaitingRecorded=true;
            if(!writeReceipt(SwirlSystemProxyExit::waitingPath(m_root),normalStopState("normal-stop-waiting")))
                fail("normal-stop-waiting-receipt-write-failed");
        }
        if(m_normalStopFailureRecorded<m_normalStopAttempts&&m_normalStopLastReleaseFinished
            &&!m_normalStopLastReleaseSucceeded&&proxy->owned()&&!proxy->busy()
            &&!m_controller->systemProxyStopping()&&!m_controller->systemProxyBusy()){
            m_normalStopFailureRecorded=m_normalStopAttempts;
            if(!writeReceipt(SwirlSystemProxyExit::failedPath(m_root),normalStopState("normal-stop-failed")))
                fail("normal-stop-failed-receipt-write-failed");
        }
        if(!m_normalStopCompleted&&!proxy->owned()&&!proxy->busy()
            &&!m_controller->processAlive()&&!m_controller->busy()){
            m_normalStopCompleted=true;
            if(!writeReceipt(SwirlSystemProxyExit::stoppedPath(m_root),normalStopState("normal-stopped")))
                fail("normal-stop-completed-receipt-write-failed");
        }
    }
    void observeReady() {
        if(m_ready||!m_failure.isEmpty()||!m_requested)return;
        auto *proxy=m_controller->systemProxy();
        if(!m_controller->processAlive()||!m_controller->apiHealthy()||!proxy->owned()
           ||!proxy->enabled()||proxy->busy()||m_controller->systemProxyBusy())return;
        const auto snapshot=SystemProxySession::snapshot();
        const auto port=m_controller->activeProxyPort();
        const bool nativeMatches=snapshot.value("flags").toInt()==3
            &&snapshot.value("server").toString()==QStringLiteral("127.0.0.1:%1").arg(port)
            &&snapshot.value("pac").toString().isEmpty();
        const bool receiptMatches=m_controller->policyV2Active()&&!m_controller->savedRevision().isEmpty()
            &&m_controller->savedRevision()==m_controller->appliedRevision();
        const bool guardReady=proxy->diagnosticState().value("guardAcknowledged").toBool();
        if(port<=0||m_controller->engineKind()!=QStringLiteral("rust")||!nativeMatches
           ||!receiptMatches||!guardReady||m_controller->processId().toLongLong()!=QCoreApplication::applicationPid()){
            fail("ready-identity-mismatch");return;
        }
        m_port=port;m_runtimePid=m_controller->processId().toLongLong();m_ready=true;
        m_initialRuntimeEpoch=m_controller->policyReceipt().value("engine_epoch").toString();
        auto report=common("ready");
        report.insert("initial_runtime_epoch",m_initialRuntimeEpoch);
        report.insert("runtime_alive",true);report.insert("runtime_healthy",true);
        report.insert("proxy_owned",true);report.insert("proxy_enabled",true);
        report.insert("native_listener_matches_rust",nativeMatches);
        report.insert("saved_applied_policy_matches",receiptMatches);
        report.insert("guard_acknowledged",guardReady);
        if(!writeReceipt(SwirlSystemProxyExit::readyPath(m_root),report))fail("ready-receipt-write-failed");
    }
    void fail(const char *code) {
        if(m_failure.isEmpty())m_failure=QString::fromLatin1(code);
        QTimer::singleShot(0,m_window,[this]{m_window->close();});
    }
    void finish() {
        m_watchdog.stop();
        auto *proxy=m_controller->systemProxy();
        const auto snapshot=SystemProxySession::snapshot();
        auto report=common("final");
        // Write acceptance and the observed disconnect are separate from the
        // parent's exact-reply assertion and production shutdown completion.
        report.insert("close_reply_write_succeeded",m_closeReplyWriteSucceeded);
        report.insert("close_after_control_disconnect",m_closeAfterControlDisconnect);
        report.insert("shutdown_coordinator_completed",QCoreApplication::instance()->property("shutdownDurationMs").isValid());
        report.insert("shutdown_ms",double(QCoreApplication::instance()->property("shutdownDurationMs").toLongLong()));
        report.insert("runtime_stopped",!m_controller->processAlive()&&!m_controller->busy());
        report.insert("proxy_owned",proxy->owned());report.insert("proxy_busy",proxy->busy());
        report.insert("journal_absent",!QFile::exists(SystemProxySession::journalPath()));
        report.insert("release_finished",m_releaseFinished);report.insert("release_succeeded",m_releaseSucceeded);
        report.insert("release_while_runtime_alive",m_releaseWhileRuntimeAlive);
        report.insert("release_waiting_observed",m_releaseWaitingObserved);
        report.insert("release_waiting_runtime_alive",m_releaseWaitingRuntimeAlive);
        report.insert("release_waiting_runtime_healthy",m_releaseWaitingRuntimeHealthy);
        report.insert("snapshot_restored_at_release",m_restoredAtRelease);
        report.insert("journal_absent_at_release",m_journalAbsentAtRelease);
        report.insert("native_snapshot_readable",!snapshot.isEmpty());
        report.insert("snapshot_restored_before_exit",snapshot==m_initial);
        // All native snapshots remain in memory. Reports contain no original
        // proxy/PAC/bypass strings, registry bytes, node values or credentials.
        if(!writeReceipt(SwirlSystemProxyExit::finalPath(m_root),report))
            qCritical("System proxy exit final receipt could not be written.");
    }
    QQuickWindow *m_window;
    EngineController *m_controller;
    QString m_root,m_failure;
    QJsonObject m_initial;
    QLocalServer m_control;
    QTimer m_watchdog;
    QElapsedTimer m_normalStopElapsed;
    QString m_initialRuntimeEpoch;
    qint64 m_normalStopLastReleaseElapsed=-1;
    int m_normalStopAttempts=0,m_normalStopReleaseSuccesses=0,m_normalStopReleaseFailures=0,m_normalStopFailureRecorded=0;
    bool m_normalStopWaitingRecorded=false,m_normalStopCompleted=false;
    bool m_normalStopLastReleaseFinished=false,m_normalStopLastReleaseSucceeded=false,m_normalStopLastReleaseAlive=false;
    bool m_normalStopRestoredAtRelease=false,m_normalStopJournalAbsentAtRelease=false;
    qint64 m_runtimePid=0;
    int m_port=0;
    bool m_requested=false,m_ready=false,m_closeRequested=false;
    bool m_closeReplyWriteSucceeded=false,m_closeAfterControlDisconnect=false;
    bool m_releaseFinished=false,m_releaseSucceeded=false,m_releaseWhileRuntimeAlive=false;
    bool m_releaseWaitingObserved=false,m_releaseWaitingRuntimeAlive=false,m_releaseWaitingRuntimeHealthy=false;
    bool m_restoredAtRelease=false,m_journalAbsentAtRelease=false;
};
}

bool SwirlSystemProxyExit::environmentIsValid() {
    const auto root=QDir::fromNativeSeparators(qEnvironmentVariable("SWIRL_TEST_ROOT"));
    const QFileInfo directory(root);
    return qEnvironmentVariable("SWIRL_SYSTEM_PROXY_TEST")==QStringLiteral("1")
        &&qEnvironmentVariable("SWIRL_LIFECYCLE_SYSTEM_PROXY")==QStringLiteral("1")
        &&qEnvironmentVariable("SWIRL_LIFECYCLE_ENGINE")==QStringLiteral("rust")
        &&root.size()>=3&&root[0].isLetter()&&root[1]==':'&&root[2]=='/'
        &&QDir::isAbsolutePath(root)&&directory.isDir()&&!directory.canonicalFilePath().isEmpty()
        &&QDir(root).entryList(QDir::AllEntries|QDir::NoDotAndDotDot|QDir::Hidden|QDir::System).isEmpty();
}
bool SwirlSystemProxyExit::start(QQuickWindow *window,EngineController *controller) {
    auto *fixture=new ExitFixture(window,controller,SwirlPaths::testRoot());
    if(fixture->start())return true;
    delete fixture;return false;
}
