#include <QString>
#include "RuntimeEvidence.h"
#include "engine/EngineController.h"
#include "app/SystemDataProvider.h"
#include "app/DiagnosticService.h"
#include <QQuickWindow>
#include <QImage>
#include <QQmlExpression>
#include <QQmlContext>
#include <QTimer>
#include <QFile>
#include <QSaveFile>
#include <QJsonDocument>
#include <QJsonObject>
#include <QDateTime>
#include <QCoreApplication>
#include <QSGRendererInterface>
#include <rhi/qrhi.h>
#include <QtCore/qfloat16.h>
#include <memory>
#include <atomic>
#include <cmath>
#include <cstring>
#include <limits>
#include "engine/RustCoreLibrary.h"
#include "network/HttpRequestPolicy.h"
#include <QDir>
#include <QFileInfo>
#include <QJsonArray>
#include <QNetworkAccessManager>
#include <QNetworkProxy>
#include <QNetworkReply>
#include <QNetworkRequest>
#include <QRegularExpression>
#include <QCryptographicHash>
#include <QMessageAuthenticationCode>
#include <QRandomGenerator>
#include <QTcpSocket>
#include <QHostAddress>
#include <QUuid>
#include <QSet>
#include <QSslSocket>
#include <QSslCertificate>
#include <QSslConfiguration>
#include <QElapsedTimer>
#include <chrono>
#ifdef Q_OS_WIN
#include <windows.h>
#include <wincrypt.h>
#endif

static void captureRenderedFrame(QQuickWindow *window,const QString &path){
 // QQuickWindow::grabWindow assumes 8-bit pixels on this Qt version. The
 // actual HDR swapchain is FP16; read it through RHI and explicitly map its
 // linear colors to an SDR PNG instead of interpreting half floats as bytes.
 auto result=std::make_shared<QRhiReadbackResult>();auto pending=std::make_shared<std::atomic_bool>(true);auto connection=std::make_shared<QMetaObject::Connection>();
 *connection=QObject::connect(window,&QQuickWindow::afterRendering,window,[window,path,result,pending,connection]{
  if(!pending->exchange(false))return;QObject::disconnect(*connection);
  auto rhi=window->rhi();auto chain=static_cast<QRhiSwapChain *>(window->rendererInterface()->getResource(window,QSGRendererInterface::RhiSwapchainResource));
  if(!rhi||!chain){qWarning()<<"Runtime frame capture requires an actual GPU swapchain";return;}
  const bool invert=rhi->isYUpInFramebuffer();const auto hdrInfo=chain->hdrInfo();const double white=hdrInfo.luminanceBehavior==QRhiSwapChainHdrInfo::SceneReferred?qMax(1.0,double(hdrInfo.sdrWhiteLevel)/80.0):1.0;
  result->completed=[window,path,result,invert,white]{
   const auto data=result->data;const auto size=result->pixelSize;const auto format=result->format;
   QMetaObject::invokeMethod(window,[path,result,data,size,format,invert,white]{
    if(format!=QRhiTexture::RGBA16F&&format!=QRhiTexture::RGBA8&&format!=QRhiTexture::BGRA8){qWarning()<<"Unsupported runtime capture format";result->completed={};return;}
    QImage image(size,QImage::Format_RGBA8888);image.fill(Qt::transparent);
    for(int y=0;y<size.height();++y){auto output=image.scanLine(invert?size.height()-1-y:y);for(int x=0;x<size.width();++x){
     if(format==QRhiTexture::RGBA16F){qfloat16 pixel[4];std::memcpy(pixel,data.constData()+(y*size.width()+x)*8,8);const double alpha=qBound(0.0,double(float(pixel[3])),1.0);for(int c=0;c<3;++c){const auto linear=alpha>0?qBound(0.0,double(float(pixel[c]))/(alpha*white),1.0):0.0;const auto srgb=linear<=0.0031308?12.92*linear:1.055*std::pow(linear,1.0/2.4)-0.055;output[x*4+c]=qRound(srgb*255);}output[x*4+3]=qRound(alpha*255);}
     else {const auto pixel=reinterpret_cast<const unsigned char *>(data.constData()+(y*size.width()+x)*4);output[x*4]=pixel[format==QRhiTexture::BGRA8?2:0];output[x*4+1]=pixel[1];output[x*4+2]=pixel[format==QRhiTexture::BGRA8?0:2];output[x*4+3]=pixel[3];}
    }}image.save(path);result->completed={};
   },Qt::QueuedConnection);
  };
  auto updates=rhi->nextResourceUpdateBatch();updates->readBackTexture(QRhiReadbackDescription(),result.get());chain->currentFrameCommandBuffer()->resourceUpdate(updates);
 },Qt::DirectConnection);
 auto frames=new QTimer(window);frames->setInterval(16);QObject::connect(frames,&QTimer::timeout,window,&QQuickWindow::update);frames->start();QTimer::singleShot(2500,frames,&QObject::deleteLater);window->update();
}

// Test-build-only harness. It drives THIS Swirl window with the real encrypted
// node store copy and real engine. It has no fixtures or access to other apps.
void startRuntimeEvidence(QQuickWindow *window,EngineController *controller,SystemDataProvider *system,DiagnosticService *diagnostics,const QString &commandPath,const QString &statePath){
 controller->setProxyPort(17988);
 // Set an isolated global route before the first engine start.
 // A saved production rule or DIRECT mode must never leak into this run.
 if(!controller->prepareRealAcceptance()||controller->routingMode()!=QStringLiteral("global")){
  qWarning()<<"Runtime acceptance refused non-global routing";QTimer::singleShot(0,qApp,&QCoreApplication::quit);return;
 }
 controller->connectNode(controller->selectedNodeId());
 auto timer=new QTimer(window);timer->setInterval(500);
 QObject::connect(timer,&QTimer::timeout,window,[=]{
  auto status=system->diagnosticSnapshot();status["testsBusy"]=controller->tests()->busy();status["testsCompleted"]=controller->tests()->completed();status["testsTotal"]=controller->tests()->total();status["testsSucceeded"]=controller->tests()->succeeded();status["testsFailed"]=controller->tests()->failed();status["hasExternalIp"]=!controller->telemetry()->externalIp().isEmpty();
  // Numeric Rust counters are safe to inspect in memory per request. The full
  // state file also contains node details and must never be copied to reports.
  const auto rustTraffic=controller->rustTrafficTotals();
  status["rustUploadTotal"]=rustTraffic.first;status["rustDownloadTotal"]=rustTraffic.second;
  status["rustAccepted"]=controller->rustAccepted();status["rustFailed"]=controller->rustFailed();
  status["rustLastErrorStage"]=controller->rustLastErrorStage();
  status["proxyMeasurement"]=controller->telemetry()->proxyDiagnostic();status["latencies"]=controller->telemetry()->latencies();
  QVariantList subscriptions;for(const auto &value:controller->imports()->providers()){const auto row=value.toMap();subscriptions.append(QVariantMap{{"name",row.value("name")},{"nodeCount",row.value("nodes")},{"status",row.value("status")},{"error",DiagnosticService::redact(row.value("error").toString())},{"updated",row.value("update")},{"nextUpdate",row.value("nextUpdate")}});}status["subscriptions"]=subscriptions;status["selectedNode"]=controller->selectedNodeName();status["activeNode"]=controller->activeNodeId();
  QSaveFile state(statePath);if(state.open(QIODevice::WriteOnly)){state.write(QJsonDocument(QJsonObject::fromVariantMap(status)).toJson());state.commit();}
  QFile command(commandPath);if(!command.open(QIODevice::ReadOnly))return;const auto request=QJsonDocument::fromJson(command.read(8192)).object();command.close();QFile::remove(commandPath);const auto action=request.value("action").toString();
  if(action=="stop"){controller->stop();QTimer::singleShot(1800,qApp,&QCoreApplication::quit);}
  else if(action=="proxy")controller->setSystemProxy(request.value("enabled").toBool());
  else if(action=="measure"){controller->telemetry()->measureNetwork();controller->testSelectedNode(controller->selectedNodeId(),QUrl("https://www.gstatic.com/generate_204"));}
  else if(action=="test-all")controller->testAllNodes(QUrl("https://www.gstatic.com/generate_204"));
  else if(action=="test-one")controller->testSelectedNode(controller->selectedNodeId(),QUrl("https://www.gstatic.com/generate_204"));
  else if(action=="refresh-subscriptions")controller->imports()->refreshAll();
  else if(action=="acknowledge")diagnostics->acknowledge();
  else if(action=="diagnostic")diagnostics->exportReport(QUrl::fromLocalFile(request.value("file").toString()),system->diagnosticSnapshot());
  else if(action=="mode")controller->setRoutingMode(request.value("mode").toString());
  else if(action=="page"){
   const auto page=request.value("page").toString();if(QStringList{"overview","subscriptions","proxies","traffic","processes","connections","logs","toolbox"}.contains(page)){
    QQmlExpression expression(qmlContext(window),window,QString("AppState.navigate('%1')").arg(page));expression.evaluate();
   }
  }else if(action=="capture"){
   const auto path=request.value("file").toString();QTimer::singleShot(300,window,[window,path]{captureRenderedFrame(window,path);});
  }else if(action=="results"){
   QVariantList results;for(const auto &node:controller->nodes()){auto row=node.toMap();const auto test=controller->tests()->result(row.value("id").toString());if(test.isEmpty())continue;results.append(QVariantMap{{"name",row.value("name")},{"latencyMs",test.value("latency")},{"http",test.value("http")},{"success",test.value("success")},{"error",test.value("error")}});}
   QSaveFile file(request.value("file").toString());if(file.open(QIODevice::WriteOnly)){file.write(QJsonDocument::fromVariant(results).toJson());file.commit();}
  }
 });timer->start();
 QTimer::singleShot(30*60*1000,window,[controller]{controller->stop();qApp->quit();});
}

namespace {
std::atomic<std::int64_t> controlledRequestStartedNs{0};
std::int64_t controlledStartedNs=0,controlledAbsoluteNs=0;
std::int64_t controlledNowNs() {
    return std::chrono::duration_cast<std::chrono::nanoseconds>(std::chrono::steady_clock::now().time_since_epoch()).count();
}
std::int64_t controlledDeadlineFor(std::int64_t requestStarted) {
    return requestStarted?std::min<std::int64_t>(controlledAbsoluteNs,requestStarted+8'000'000'000LL)
        :controlledStartedNs+20'000'000'000LL;
}
#ifdef Q_OS_WIN
std::atomic<unsigned char *> controlledStopReceipt{nullptr};
bool controlledAttachStopReceipt(const ControlledNodeSession &session,const QByteArray &handleBytes) {
    if(handleBytes.size()!=8||controlledStopReceipt.load(std::memory_order_acquire))return false;
    quint64 encoded=0;std::memcpy(&encoded,handleBytes.constData(),8);
    if(!encoded||encoded>std::numeric_limits<quintptr>::max())return false;
    const auto handle=reinterpret_cast<HANDLE>(quintptr(encoded));
    auto *view=static_cast<unsigned char *>(MapViewOfFile(handle,FILE_MAP_WRITE,0,0,256));
    const bool closed=CloseHandle(handle);
    if(!view)return false;
    const auto read64=[view](int offset){quint64 result=0;std::memcpy(&result,view+offset,8);return result;};
    DWORD version=0,pid=0;std::memcpy(&version,view+16,4);std::memcpy(&pid,view+20,4);
    LARGE_INTEGER frequency{},now{};
    bool valid=closed&&std::memcmp(view,"SWIRL-STOP-V1\0\0\0",16)==0&&version==1&&pid==GetCurrentProcessId()
        &&session.nonce.toLatin1()==QByteArray(reinterpret_cast<const char *>(view+24),64)
        &&session.sourceSha.toLatin1()==QByteArray(reinterpret_cast<const char *>(view+88),40)
        &&QueryPerformanceFrequency(&frequency)&&QueryPerformanceCounter(&now)
        &&frequency.QuadPart>0&&read64(184)==quint64(frequency.QuadPart)
        &&read64(168)>0&&read64(168)<=quint64(now.QuadPart);
    for(int offset=128;offset<256;++offset){
        if((offset>=168&&offset<176)||(offset>=184&&offset<192))continue;
        valid=valid&&view[offset]==0;
    }
    if(!valid){UnmapViewOfFile(view);return false;}
    // Touch the already committed page before any request. The hard-stop path
    // below performs only bounded memory stores, QPC and TerminateProcess.
    controlledStopReceipt.store(view,std::memory_order_release);return true;
}
void controlledRecordHardStop(std::int64_t requestStarted,std::int64_t deadline,std::int64_t fired) {
    auto *view=controlledStopReceipt.load(std::memory_order_acquire);
    if(!view)return;
    LARGE_INTEGER qpc{};if(!QueryPerformanceCounter(&qpc))return;
    const auto write64=[view](int offset,quint64 value){std::memcpy(view+offset,&value,8);};
    write64(128,quint64(controlledStartedNs));write64(136,quint64(controlledAbsoluteNs));
    write64(144,quint64(requestStarted));write64(152,quint64(deadline));write64(160,quint64(fired));
    write64(176,quint64(qpc.QuadPart));
    const DWORD phase=requestStarted?2:1;std::memcpy(view+192,&phase,4);
    // The release barrier makes a complete record visible before native exit.
    InterlockedExchange(reinterpret_cast<volatile LONG *>(view+196),1);
}
#endif
bool controlledPath(const QString &path,bool directory=false) {
    const QFileInfo file(path);
    if(!file.isAbsolute()||!file.exists()||file.isSymLink()||(directory?!file.isDir():!file.isFile()))return false;
    for(auto parent=file.absoluteFilePath();;){
        const QFileInfo item(parent);
        if(item.isSymLink())return false;
        const auto next=item.absolutePath();if(next==parent)break;parent=next;
    }
    return true;
}
bool controlledJson(const QString &path,const QJsonObject &value) {
    QSaveFile file(path);
    const auto bytes=QJsonDocument(value).toJson(QJsonDocument::Compact);
    return file.open(QIODevice::WriteOnly)&&file.write(bytes)==bytes.size()&&file.commit();
}
bool controlledSeal(const QString &path,QByteArray bytes) {
#ifdef Q_OS_WIN
    DATA_BLOB input{DWORD(bytes.size()),reinterpret_cast<BYTE *>(bytes.data())},output{};
    if(!CryptProtectData(&input,L"Swirl bounded node acceptance",nullptr,nullptr,nullptr,CRYPTPROTECT_UI_FORBIDDEN,&output))return false;
    bytes.fill('\0');QSaveFile file(path);
    const bool written=file.open(QIODevice::WriteOnly)&&file.write(reinterpret_cast<char *>(output.pbData),output.cbData)==output.cbData&&file.commit();
    SecureZeroMemory(output.pbData,output.cbData);LocalFree(output.pbData);return written;
#else
    Q_UNUSED(path);bytes.fill('\0');return false;
#endif
}

bool controlledKeys(const QJsonObject &object,const QStringList &keys) {
    if(object.size()!=keys.size())return false;
    for(const auto &key:keys)if(!object.contains(key))return false;
    return true;
}
bool controlledPort(const QJsonValue &value,int *port) {
    if(!value.isDouble()||value.toDouble()!=value.toInt()||value.toInt()<1||value.toInt()>65535)return false;
    *port=value.toInt();return true;
}
bool controlledFixtureCatalog(const ControlledNodeSession &session,QString *nodeId=nullptr) {
    // This store was created below from fixed data after the live fixture proof;
    // no caller-supplied ciphertext, subscription or native document is loaded.
    NodeStore store(session.storePath);
    const auto nodes=store.nodes();
    if(!store.error().isEmpty()||store.saving()||!store.configurationAvailable()||store.configurationV2()
        ||!store.subscriptions().isEmpty()||!store.networkConfiguration().isEmpty()||nodes.size()!=1)return false;
    const auto &node=nodes.first();
    if(QUuid(node.id).isNull()||(!session.fixtureNodeId.isEmpty()&&node.id!=session.fixtureNodeId)
        ||(!store.selectedId().isEmpty()&&store.selectedId()!=node.id)
        ||node.name!=QStringLiteral("Synthetic controlled SOCKS5")||node.protocol!=QStringLiteral("socks5")
        ||node.host!=QStringLiteral("127.0.0.1")||node.port!=session.fixtureSocksPort
        ||node.username!=QStringLiteral("fixture")||node.password!=session.fixturePassword
        ||!node.cipher.isEmpty()||!node.serverName.isEmpty()||!node.sourceId.isEmpty()
        ||!node.parameters.isEmpty()||!node.originalConfiguration.isEmpty()||!node.sourceFormat.isEmpty()
        ||!node.providerAlias.isEmpty()||!node.conversionIssues.isEmpty()||node.certificateVerificationEnforced
        ||!node.sourceDocument.isEmpty()||node.sourceNodeIndex!=-1||node.importSource!=QStringLiteral("manual")
        ||!node.parameterState.isEmpty()||!node.transportType.isEmpty()||!node.securityType.isEmpty()
        ||!node.sourceFingerprint.isEmpty()||!node.nativeOutbound.isEmpty()||!node.runtimeIssues.isEmpty()
        ||node.nativeExecutable)return false;
    if(nodeId)*nodeId=node.id;
    return true;
}
bool controlledCreateFixtureCatalog(ControlledNodeSession *session) {
    // An atomically new subdirectory avoids ever opening a supplied node store
    // or its selection/network/recovery sidecars, including during reload.
    const auto name=QStringLiteral("fixture-store-")+QUuid::createUuid().toString(QUuid::WithoutBraces);
    if(!QDir(session->root).mkdir(name))return false;
    session->storePath=QDir(session->root).filePath(name+QStringLiteral("/nodes.dpapi"));
    {
        NodeStore store(session->storePath);
        if(!store.error().isEmpty()||!store.nodes().isEmpty()||!store.subscriptions().isEmpty()
            ||!store.networkConfiguration().isEmpty()||store.configurationV2()
            ||!store.saveNode({{"name",QStringLiteral("Synthetic controlled SOCKS5")},{"protocol",QStringLiteral("socks5")},
                {"host",QStringLiteral("127.0.0.1")},{"port",session->fixtureSocksPort},
                {"username",QStringLiteral("fixture")},{"password",session->fixturePassword},{"options",QVariantMap{}}}))return false;
    }
    return controlledFixtureCatalog(*session,&session->fixtureNodeId);
}
#ifdef Q_OS_WIN
bool controlledPrivateProof(QByteArray *proof) {
    const auto input=GetStdHandle(STD_INPUT_HANDLE);
    if(input==nullptr||input==INVALID_HANDLE_VALUE||GetFileType(input)!=FILE_TYPE_PIPE)return false;
    const QByteArray prefix("SWIRL-FIXTURE-PROOF-2\n");
    const auto expected=prefix.size()+104;
    const auto deadline=std::min<std::int64_t>(controlledDeadlineFor(controlledRequestStartedNs.load(std::memory_order_acquire)),controlledNowNs()+2'000'000'000LL);
    QByteArray data;
    while(controlledNowNs()<deadline){
        DWORD available=0;
        if(!PeekNamedPipe(input,nullptr,0,nullptr,&available,nullptr)){
            if(GetLastError()!=ERROR_BROKEN_PIPE)break;
            if(data.size()==expected&&data.startsWith(prefix)){*proof=data.mid(prefix.size());data.fill('\0');return true;}
            break;
        }
        if(available){
            char buffer[256];DWORD received=0;
            if(!ReadFile(input,buffer,std::min<DWORD>(available,sizeof(buffer)),&received,nullptr)||!received)break;
            data.append(buffer,int(received));SecureZeroMemory(buffer,sizeof(buffer));
            if(data.size()>expected)break;
        }else Sleep(1);
    }
    data.fill('\0');return false;
}
bool controlledProveFixture(const ControlledNodeSession &session,const QByteArray &manifestDigest,const QByteArray &key) {
    const QByteArray prefix("SWIRL-OWNED-FIXTURE-1\n");
    const auto deadline=std::min<std::int64_t>(controlledDeadlineFor(controlledRequestStartedNs.load(std::memory_order_acquire)),controlledNowNs()+2'000'000'000LL);
    const auto remaining=[&]{return int(std::max<std::int64_t>(0,(deadline-controlledNowNs())/1'000'000));};
    QByteArray challenge(32,Qt::Uninitialized);
    for(qsizetype offset=0;offset<challenge.size();offset+=sizeof(quint32)){
        const auto random=QRandomGenerator::system()->generate();std::memcpy(challenge.data()+offset,&random,sizeof(random));
    }
    const auto request=prefix+manifestDigest+challenge;
    const auto expected=QMessageAuthenticationCode::hash(request,key,QCryptographicHash::Sha256);
    QTcpSocket socket;socket.setProxy(QNetworkProxy::NoProxy);
    socket.connectToHost(QHostAddress::LocalHost,quint16(session.fixtureSocksPort));
    if(remaining()<=0||!socket.waitForConnected(remaining())||socket.write(request)!=request.size())return false;
    while(socket.bytesToWrite()>0)if(remaining()<=0||!socket.waitForBytesWritten(remaining()))return false;
    QByteArray reply;
    while(reply.size()<expected.size()){
        if(!socket.bytesAvailable()&&(remaining()<=0||!socket.waitForReadyRead(remaining())))return false;
        reply+=socket.read(expected.size()+1-reply.size());
    }
    socket.abort();
    if(reply.size()!=expected.size())return false;
    unsigned char mismatch=0;
    for(qsizetype index=0;index<expected.size();++index)mismatch|=static_cast<unsigned char>(reply[index]^expected[index]);
    return mismatch==0;
}
#endif

class ControlledNodeRun final : public QObject {
public:
    ControlledNodeRun(QQuickWindow *window,EngineController *controller,ControlledNodeSession session)
        :QObject(window),m_window(window),m_controller(controller),m_session(std::move(session)),m_network(this) {
        m_clock.start();m_timer.setInterval(25);
        connect(&m_timer,&QTimer::timeout,this,[this]{tick();});
        connect(controller,&EngineController::statusChanged,this,[this]{tick();});
        connect(controller->tests(),&NodeTestService::changed,this,[this]{tick();});
    }
    void begin() {
        // No background subscriptions or telemetry are admitted by this run.
        m_controller->imports()->shutdown();
        auto &library=RustCoreLibrary::instance();
        if(!library.load()||library.expectedSourceSha()!=m_session.sourceSha){fail("PairedCoreIdentityRequired");return;}
        const auto nodes=m_controller->nodes();
        if(m_session.nodeOrdinal!=1||nodes.size()!=1||!controlledFixtureCatalog(m_session)){
            fail("OwnedSyntheticCatalogRequired");return;
        }
        m_id=nodes.first().toMap().value("id").toString();
        if(m_id!=m_session.fixtureNodeId||!m_controller->prepareRealAcceptance()){fail("IsolatedSessionUnavailable");return;}
        m_controller->setProxyPort(m_session.proxyPort);
        if(!m_controller->chooseNode(m_id)){fail("NodeConfigurationRejected");return;}
        if(!publish("starting")){fail("PrivateReceiptWriteFailed");return;}
        // Navigation uses the actual window's page/controller bindings.
        QQmlExpression expression(qmlContext(m_window),m_window,QStringLiteral("AppState.navigate('proxies')"));
        expression.evaluate();
        if(expression.hasError()){fail("NodeUiNavigationFailed");return;}
        m_begun=true;m_timer.start();QTimer::singleShot(0,this,[this]{tick();});
    }
private:
    QQuickWindow *m_window;
    EngineController *m_controller;
    ControlledNodeSession m_session;
    QNetworkAccessManager m_network;
    QTimer m_timer;
    QElapsedTimer m_clock,m_requestsClock;
    QString m_id,m_error,m_probePhase,m_probeFailureCode;
    QJsonArray m_http;
    QList<QNetworkReply *> m_replies;
    bool m_begun=false,m_connectRequested=false,m_requestsStarted=false,m_stopping=false,m_done=false;
    bool m_probeCompleted=false,m_probeSuccess=false;
    qint64 m_uiLatency=-1;
    qint64 m_outboundConnectMs=-1,m_originTlsMs=-1;
    int m_probeHttp=0;
    int m_completed=0;
    bool publish(const QString &phase) {
        return controlledJson(m_session.root+"/state.json",{{"schema",1},{"nonce",m_session.nonce},{"sourceSha",m_session.sourceSha},
            {"nodeOrdinal",m_session.nodeOrdinal},{"phase",phase},{"requestsStarted",m_requestsStarted},{"elapsedMs",m_clock.elapsed()}});
    }
    void fail(const QString &code) {
        if(m_error.isEmpty())m_error=code;
        stop();
    }
    void request(const char *scheme,const QUrl &url) {
        QNetworkRequest input(url);SwirlNetwork::applyHttp1OnlyPolicy(input);
        input.setTransferTimeout(8000);input.setRawHeader("Connection","close");
        input.setAttribute(QNetworkRequest::RedirectPolicyAttribute,QNetworkRequest::ManualRedirectPolicy);
        input.setAttribute(QNetworkRequest::CacheLoadControlAttribute,QNetworkRequest::AlwaysNetwork);
        if(!m_session.fixtureCa.isEmpty()&&url.scheme()==QStringLiteral("https")){
            auto ssl=input.sslConfiguration();
            ssl.setCaCertificates(QSslCertificate::fromData(m_session.fixtureCa));
            ssl.setPeerVerifyMode(QSslSocket::VerifyPeer);input.setSslConfiguration(ssl);
        }
        auto *reply=m_network.get(input);m_replies.append(reply);
        auto body=std::make_shared<QByteArray>();auto elapsed=std::make_shared<QElapsedTimer>();elapsed->start();
        auto tlsRejected=std::make_shared<bool>(false);
        auto limitExceeded=std::make_shared<bool>(false);
        const auto drain=[reply,body,limitExceeded]{
            body->append(reply->read(65537-body->size()));
            if(body->size()>65536){*limitExceeded=true;reply->abort();}
        };
        connect(reply,&QNetworkReply::readyRead,this,drain);
        connect(reply,&QNetworkReply::sslErrors,this,[reply,tlsRejected](const QList<QSslError> &){*tlsRejected=true;reply->abort();});
        connect(reply,&QNetworkReply::finished,this,[this,reply,body,elapsed,tlsRejected,limitExceeded,drain,scheme]{
            drain();m_replies.removeOne(reply);++m_completed;
            const int status=reply->attribute(QNetworkRequest::HttpStatusCodeAttribute).toInt();
            const bool succeeded=reply->error()==QNetworkReply::NoError&&status>=200&&status<300&&!*tlsRejected&&!*limitExceeded;
            QString exitHash;
            // The fixed HTTPS trace endpoint supplies exit evidence. Original
            // response bytes stay DPAPI-encrypted in the private session.
            if(QByteArray(scheme)=="https"&&succeeded){
                const auto match=QRegularExpression(QStringLiteral("(?:^|\\n)ip=([^\\r\\n]+)"))
                    .match(QString::fromUtf8(*body));
                if(match.hasMatch())exitHash=QString::fromLatin1(QCryptographicHash::hash(match.captured(1).toUtf8(),QCryptographicHash::Sha256).toHex());
            }
            const bool sealed=controlledSeal(m_session.root+"/"+QString::fromLatin1(scheme)+"-response.dpapi",*body);
            body->fill('\0');
            m_http.append(QJsonObject{{"scheme",QString::fromLatin1(scheme)},{"httpStatus",status},{"success",succeeded&&sealed},
                {"qtError",int(reply->error())},{"tlsRejected",*tlsRejected},{"bodyLimitExceeded",*limitExceeded},
                {"elapsedMs",elapsed->elapsed()},{"exitIpSha256",exitHash},{"responseEncrypted",sealed}});
            reply->deleteLater();
            if(!sealed&&m_error.isEmpty())m_error="PrivateReceiptWriteFailed";
            tick();
        });
    }
    void tick() {
        if(m_done||(!m_begun&&!m_stopping))return;
        if(m_stopping){
            if(m_replies.isEmpty()&&!m_controller->tests()->busy()&&!m_controller->processAlive()&&!m_controller->busy())finish();
            return;
        }
        if(!m_requestsStarted){
            if(m_clock.elapsed()>=20000){fail("StartupDeadlineExceeded");return;}
            if(!m_connectRequested&&!m_controller->busy()){
                if(m_controller->selectedNodeId()!=m_id){fail("NodeSelectionUnconfirmed");return;}
                m_connectRequested=true;m_controller->connectNode(m_id);return;
            }
            if(!m_controller->apiHealthy())return;
            if(m_controller->activeNodeId()!=m_id||m_controller->routingMode()!=QStringLiteral("global")
                ||m_controller->activeProxyPort()!=m_session.proxyPort||m_controller->tunRequested()||m_controller->proxyRequested()){
                fail("SelectedProxyRouteUnconfirmed");return;
            }
            const auto requestStarted=controlledNowNs();
            if(requestStarted>=controlledStartedNs+20'000'000'000LL){fail("StartupDeadlineExceeded");return;}
            m_requestsStarted=true;m_requestsClock.start();
            controlledRequestStartedNs.store(requestStarted,std::memory_order_release);
            if(!publish("requests")){fail("PrivateReceiptWriteFailed");return;}
            m_network.setProxy(QNetworkProxy(QNetworkProxy::HttpProxy,QStringLiteral("127.0.0.1"),quint16(m_session.proxyPort)));
            // All three requests use the same explicit selected node. There is
            // no direct-mode or alternative-node retry on any failed response.
            // The Rust HEAD fixture is HTTP on loopback; HTTPS is independently
            // exercised below with a fixture-only, peer-verified Qt trust set.
            const auto probe=QUrl(QString("http://127.0.0.1:%1/generate_204").arg(m_session.fixtureHttpPort));
            m_controller->testSelectedNode(m_id,probe);
            request("http",QUrl(QString("http://127.0.0.1:%1/").arg(m_session.fixtureHttpPort)));
            request("https",QUrl(QString("https://127.0.0.1:%1/trace").arg(m_session.fixtureHttpsPort)));
        }
        if(!m_probeCompleted&&!m_controller->tests()->busy()){
            const auto probe=m_controller->tests()->result(m_id);
            if(!probe.isEmpty()){
                m_probeCompleted=true;m_probeSuccess=probe.value("success").toBool();m_uiLatency=probe.value("latency",-1).toLongLong();
                m_probeHttp=probe.value("http").toInt();m_probePhase=probe.value("phase").toString();
                m_probeFailureCode=probe.value("failureCode").toString();
                m_outboundConnectMs=probe.value("outboundConnectMs",-1).toLongLong();m_originTlsMs=probe.value("originTlsMs",-1).toLongLong();
            }
        }
        if(m_probeCompleted&&m_completed==2){stop();return;}
        if(m_requestsClock.elapsed()>=8000)fail("RequestDeadlineExceeded");
    }
    void stop() {
        if(m_stopping||m_done)return;
        m_stopping=true;publish("stopping");
        const auto replies=m_replies;
        for(auto *reply:replies)reply->abort();
        m_controller->tests()->cancel();m_controller->stop();
        m_timer.start();QTimer::singleShot(0,this,[this]{tick();});
    }
    void finish() {
        m_done=true;m_timer.stop();
        bool httpPassed=m_http.size()==2;
        bool exitObserved=false;
        for(const auto &entry:m_http){const auto row=entry.toObject();httpPassed=httpPassed&&row.value("success").toBool();exitObserved=exitObserved||!row.value("exitIpSha256").toString().isEmpty();}
        const bool passed=m_error.isEmpty()&&m_probeCompleted&&m_probeSuccess&&httpPassed&&exitObserved;
        const QJsonObject result{{"schema",1},{"nonce",m_session.nonce},{"sourceSha",m_session.sourceSha},
            {"nodeOrdinal",m_session.nodeOrdinal},{"passed",passed},{"failureCode",m_error},
            {"selectedNodeReference",NodeTestService::nodeReference(m_id)},{"probeCompleted",m_probeCompleted},
            {"probeSuccess",m_probeSuccess},{"uiHeadersMs",m_uiLatency},{"proxyRequests",m_http},
            {"probeHttpStatus",m_probeHttp},{"probePhase",m_probePhase},{"probeFailureCode",m_probeFailureCode},
            {"outboundConnectMs",m_outboundConnectMs},{"originTlsMs",m_originTlsMs},
            {"fixtureOnly",true},{"liveReady",false},{"persistentBudgetGuardExercised",false},
            {"uiSubscriptionImportExercised",false},{"uiPolicySelectionExercised",false},
            {"tasksReleased",true},{"systemNetworkChanged",false},{"requestDeadlineMs",8000},{"elapsedMs",m_clock.elapsed()}};
        const bool saved=controlledJson(m_session.root+"/result.json",result);publish("finished");
        QCoreApplication::exit(saved&&passed?0:2);
    }
};
}

bool loadControlledNodeSession(const QString &root,ControlledNodeSession *session) {
#ifdef Q_OS_WIN
    BOOL member=FALSE;
    JOBOBJECT_EXTENDED_LIMIT_INFORMATION limits{};
    if(!session||!IsProcessInJob(GetCurrentProcess(),nullptr,&member)||!member||!controlledPath(root,true)
        ||!QueryInformationJobObject(nullptr,JobObjectExtendedLimitInformation,&limits,sizeof(limits),nullptr)
        ||(limits.BasicLimitInformation.LimitFlags&(JOB_OBJECT_LIMIT_ACTIVE_PROCESS|JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE))
            !=(JOB_OBJECT_LIMIT_ACTIVE_PROCESS|JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE)||limits.BasicLimitInformation.ActiveProcessLimit!=1
        ||QString::fromLatin1(qVersion())!=QStringLiteral("6.12.0")
        ||QDir::cleanPath(qEnvironmentVariable("SWIRL_TEST_ROOT"))!=QDir::cleanPath(root))return false;
    QFile manifest(root+"/session.json");
    if(!controlledPath(manifest.fileName())||!manifest.open(QIODevice::ReadOnly)||manifest.size()>4096)return false;
    const auto bytes=manifest.read(4097);
    QJsonParseError parse;
    const auto document=QJsonDocument::fromJson(bytes,&parse);
    if(parse.error!=QJsonParseError::NoError||!document.isObject())return false;
    const auto input=document.object();
    if(!controlledKeys(input,{"schema","sourceSha","nonce","nodeOrdinal","proxyPort","fixture"})
        ||input.value("schema")!=QJsonValue(2)||input.value("nodeOrdinal")!=QJsonValue(1)
        ||input.value("sourceSha").toString()!=RustCoreLibrary::expectedSourceSha()
        ||!QRegularExpression("^[0-9a-f]{64}$").match(input.value("nonce").toString()).hasMatch())return false;
    if(!input.value("fixture").isObject())return false;
    const auto settings=input.value("fixture").toObject();
    if(!controlledKeys(settings,{"httpPort","httpsPort","socksPort","caSha256"}))return false;
    ControlledNodeSession candidate;
    candidate.root=QDir::cleanPath(root);candidate.sourceSha=input.value("sourceSha").toString();
    candidate.nonce=input.value("nonce").toString();candidate.nodeOrdinal=1;
    if(!controlledPort(input.value("proxyPort"),&candidate.proxyPort)
        ||!controlledPort(settings.value("httpPort"),&candidate.fixtureHttpPort)
        ||!controlledPort(settings.value("httpsPort"),&candidate.fixtureHttpsPort)
        ||!controlledPort(settings.value("socksPort"),&candidate.fixtureSocksPort)
        ||QSet<int>{candidate.proxyPort,candidate.fixtureHttpPort,candidate.fixtureHttpsPort,candidate.fixtureSocksPort}.size()!=4
        ||!QDir(root).entryList(QStringList{"nodes.dpapi*","fixture-store-*"},QDir::AllEntries|QDir::Hidden|QDir::System|QDir::NoDotAndDotDot).isEmpty()
        ||QFileInfo::exists(root+"/result.json")||QFileInfo::exists(root+"/state.json"))return false;
    const auto caHash=settings.value("caSha256").toString();
    if(caHash!=QStringLiteral("a2fd461d4090889bd26e0eaea5bc974cffbdcced8d7aa0198221e5b9f5b05311")
        &&caHash!=QStringLiteral("e1075d330aab28049a89ba8e64f5f93f8ddbe2573c022c28508bb2ac2df26f1b"))return false;
    const auto caPath=root+"/fixture-ca.pem";
    QFile ca(caPath);
    if(!controlledPath(caPath)||!ca.open(QIODevice::ReadOnly)||ca.size()>16384)return false;
    candidate.fixtureCa=ca.read(16385);
    if(QString::fromLatin1(QCryptographicHash::hash(candidate.fixtureCa,QCryptographicHash::Sha256).toHex())!=caHash)return false;
    QByteArray proof;
    if(!controlledPrivateProof(&proof))return false;
    const auto digest=QCryptographicHash::hash(bytes,QCryptographicHash::Sha256);
    if(proof.left(32)!=digest){proof.fill('\0');return false;}
    auto key=proof.mid(32,32);
    const bool owned=controlledProveFixture(candidate,digest,key);
    key.fill('\0');
    if(!owned){proof.fill('\0');return false;}
    if(!controlledAttachStopReceipt(candidate,proof.mid(96,8))){proof.fill('\0');return false;}
    candidate.fixturePassword=QString::fromLatin1(proof.mid(64,32).toHex());proof.fill('\0');
    if(!controlledCreateFixtureCatalog(&candidate))return false;
    *session=std::move(candidate);return true;
#else
    Q_UNUSED(root);Q_UNUSED(session);return false;
#endif
}
void startControlledNodeSession(QQuickWindow *window,EngineController *controller,const ControlledNodeSession &session) {
    auto *run=new ControlledNodeRun(window,controller,session);
    QTimer::singleShot(0,run,[run]{run->begin();});
}
std::jthread startControlledNodeWatchdog(bool enabled) {
#ifdef Q_OS_WIN
    if(!enabled)return {};
    const auto now=controlledNowNs();controlledStartedNs=now;controlledAbsoluteNs=now+28'000'000'000LL;
    controlledRequestStartedNs.store(0,std::memory_order_release);
    return std::jthread([](std::stop_token stop){
        while(!stop.stop_requested()){
            const auto requestStarted=controlledRequestStartedNs.load(std::memory_order_acquire);
            const auto deadline=controlledDeadlineFor(requestStarted);const auto now=controlledNowNs();
            if(now>=deadline){
                // This QA process has no system-network ownership. Even a
                // completely stalled Qt/Rust event loop cannot keep its sockets.
                controlledRecordHardStop(requestStarted,deadline,now);
                TerminateProcess(GetCurrentProcess(),124);return;
            }
            std::this_thread::sleep_for(std::chrono::milliseconds(10));
        }
        if(auto *view=controlledStopReceipt.exchange(nullptr,std::memory_order_acq_rel))UnmapViewOfFile(view);
    });
#else
    Q_UNUSED(enabled);return {};
#endif
}
