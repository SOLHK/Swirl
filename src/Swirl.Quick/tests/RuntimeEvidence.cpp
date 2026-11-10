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
#include <QScopeGuard>
#include <QJsonDocument>
#include <QJsonObject>
#include <QDateTime>
#include <QCoreApplication>
#include <QSGRendererInterface>
#include <rhi/qrhi.h>
#include <QtCore/qfloat16.h>
#include <memory>
#include <atomic>
#include <algorithm>
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
#ifdef SWIRL_PRIVATE_UI_QUOTA
#include "engine/NodeImporter.h"
#include "engine/NativeNodeBridge.h"
#include <QQuickItem>
#include <QJSValue>
#include <QPointer>
#include <QScopedValueRollback>
#include <QTemporaryDir>
#include <QTest>
#endif
#ifdef Q_OS_WIN
#include <windows.h>
#include <wincrypt.h>
#include <sddl.h>
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

QString ControlledNodeSession::originHost() const {
    return uiImportPolicy?QStringLiteral("203.0.113.1"):QStringLiteral("127.0.0.1");
}
QUrl ControlledNodeSession::subscriptionUrl() const {
    return QUrl(QStringLiteral("https://%1:%2/swirl-private-subscription/%3.yaml")
        .arg(originHost()).arg(fixtureHttpsPort).arg(nonce));
}
QByteArray ControlledNodeSession::subscriptionBody() const {
    return QByteArray("proxies:\n  - name: Synthetic imported SOCKS5\n    type: socks5\n    server: ")
        +(uiDnsPolicy?QByteArray("swirl-node.fixture.invalid"):QByteArray("127.0.0.1"))+"\n    port: "
        +QByteArray::number(fixtureSocksPort)+"\n    username: fixture\n    password: \""+fixturePassword.toLatin1()+"\"\n";
}
QVariantMap ControlledNodeSession::dnsConfiguration() const {
    return {{"mode",0},{"servers",QString{}},{"encrypted",QStringLiteral("tls://127.0.0.1:%1").arg(fixtureSocksPort)},
        {"hosts",QVariantList{}},{"useHosts",false},{"respectRules",false},{"queryFamily",QStringLiteral("ipv4_only")}};
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
std::atomic<bool> controlledNativeWatchdog500ms{false};
bool controlledAttachStopReceipt(const ControlledNodeSession &session,const QByteArray &handleBytes) {
    if(handleBytes.size()!=8||controlledStopReceipt.load(std::memory_order_acquire))return false;
    quint64 encoded=0;std::memcpy(&encoded,handleBytes.constData(),8);
    if(!encoded||encoded>std::numeric_limits<quintptr>::max())return false;
    const auto handle=reinterpret_cast<HANDLE>(quintptr(encoded));
    auto *view=static_cast<unsigned char *>(MapViewOfFile(handle,FILE_MAP_WRITE,0,0,256));
    const bool closed=CloseHandle(handle);
    if(!view)return false;
    const auto read64=[view](int offset){quint64 result=0;std::memcpy(&result,view+offset,8);return result;};
    DWORD version=0,pid=0,control=0;std::memcpy(&version,view+16,4);std::memcpy(&pid,view+20,4);
    std::memcpy(&control,view+200,4);
    LARGE_INTEGER frequency{},now{};
    bool valid=closed&&std::memcmp(view,"SWIRL-STOP-V1\0\0\0",16)==0&&version==1&&pid==GetCurrentProcessId()
        &&session.nonce.toLatin1()==QByteArray(reinterpret_cast<const char *>(view+24),64)
        &&session.sourceSha.toLatin1()==QByteArray(reinterpret_cast<const char *>(view+88),40)
        &&QueryPerformanceFrequency(&frequency)&&QueryPerformanceCounter(&now)
        &&frequency.QuadPart>0&&read64(184)==quint64(frequency.QuadPart)
        &&read64(168)>0&&read64(168)<=quint64(now.QuadPart)
        &&control==(session.nativeWatchdog500msControl?1u:0u);
    for(int offset=128;offset<256;++offset){
        if((offset>=168&&offset<176)||(offset>=184&&offset<192)||(offset>=200&&offset<204))continue;
        valid=valid&&view[offset]==0;
    }
    if(!valid){UnmapViewOfFile(view);return false;}
    // Touch the already committed page before any request. The hard-stop path
    // below performs only bounded memory stores, QPC and TerminateProcess.
    // Offset 200 is the parent's initial bound contract, not read-only memory.
    // It matches the HMAC-proved manifest and remains untouched by the child.
    controlledNativeWatchdog500ms.store(session.nativeWatchdog500msControl,std::memory_order_release);
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
    const auto bytes=QJsonDocument(value).toJson(QJsonDocument::Compact);
#ifdef Q_OS_WIN
    // QSaveFile's FileRenameInfo replacement rejects an open destination even
    // when the parent's read-only snapshot handle shares deletion.
    HANDLE token=nullptr;
    if(!OpenProcessToken(GetCurrentProcess(),TOKEN_QUERY,&token))return false;
    DWORD size=0;GetTokenInformation(token,TokenUser,nullptr,0,&size);
    QByteArray user(int(size),Qt::Uninitialized);
    const bool read=size&&GetTokenInformation(token,TokenUser,user.data(),size,&size);
    CloseHandle(token);
    LPWSTR sid=nullptr;
    if(!read||!ConvertSidToStringSidW(reinterpret_cast<TOKEN_USER *>(user.data())->User.Sid,&sid))return false;
    // An elevated token's default owner can be Administrators. Set both owner
    // and DACL at creation instead of changing process token defaults or ACLs.
    const auto sddl=QStringLiteral("O:%1D:P(A;;FA;;;%1)").arg(QString::fromWCharArray(sid));
    LocalFree(sid);
    PSECURITY_DESCRIPTOR descriptor=nullptr;
    if(!ConvertStringSecurityDescriptorToSecurityDescriptorW(reinterpret_cast<LPCWSTR>(sddl.utf16()),
        SDDL_REVISION_1,&descriptor,nullptr))return false;
    const auto releaseDescriptor=qScopeGuard([&]{LocalFree(descriptor);});
    SECURITY_ATTRIBUTES attributes{sizeof(SECURITY_ATTRIBUTES),descriptor,FALSE};
    const auto target=QDir::toNativeSeparators(path);
    const auto temporary=target+QStringLiteral(".pending-")+QUuid::createUuid().toString(QUuid::WithoutBraces);
    HANDLE file=CreateFileW(reinterpret_cast<LPCWSTR>(temporary.utf16()),GENERIC_WRITE,0,&attributes,
        CREATE_NEW,FILE_ATTRIBUTE_NORMAL|FILE_FLAG_OPEN_REPARSE_POINT,nullptr);
    if(file==INVALID_HANDLE_VALUE)return false;
    bool published=false;
    const auto releaseTemporary=qScopeGuard([&]{
        if(file!=INVALID_HANDLE_VALUE)CloseHandle(file);
        if(!published)DeleteFileW(reinterpret_cast<LPCWSTR>(temporary.utf16()));
    });
    DWORD written=0;
    const bool complete=WriteFile(file,bytes.constData(),DWORD(bytes.size()),&written,nullptr)
        &&written==bytes.size()&&FlushFileBuffers(file);
    const bool closed=CloseHandle(file);file=INVALID_HANDLE_VALUE;
    if(!complete||!closed)return false;
    published=ReplaceFileW(reinterpret_cast<LPCWSTR>(target.utf16()),reinterpret_cast<LPCWSTR>(temporary.utf16()),
        nullptr,0,nullptr,nullptr);
    if(!published&&GetLastError()==ERROR_FILE_NOT_FOUND)
        published=MoveFileExW(reinterpret_cast<LPCWSTR>(temporary.utf16()),reinterpret_cast<LPCWSTR>(target.utf16()),
            MOVEFILE_WRITE_THROUGH);
    return published;
#else
    QSaveFile file(path);
    return file.open(QIODevice::WriteOnly)&&file.write(bytes)==bytes.size()&&file.commit();
#endif
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

#ifdef SWIRL_PRIVATE_UI_QUOTA
// This is a Qt-input driver, not a second importer or policy implementation.
// Each mutation below originates in an existing visible control; its receipt
// and a separately decrypted NodeStore are observed before the next action.
class ControlledImportUi final : public QObject {
public:
    ControlledImportUi(QQuickWindow *window,EngineController *controller,const ControlledNodeSession &session,
                       std::function<bool()> networkPhase,QObject *parent)
        :QObject(parent),m_window(window),m_controller(controller),m_session(session),m_networkPhase(std::move(networkPhase)) {
        connect(controller,&EngineController::policyApplyFinished,this,[this](const QString &id,bool success){m_completions.insert(id,success);});
    }
    bool begin(){return navigate("policies");}
    QString error() const{return m_error;}
    QString importedId() const{return m_importedId;}
    bool importExercised() const{return m_imported;}
    bool policyExercised() const{return m_policySelected;}
    bool probeClicked() const{return m_probeClicked;}
    bool ready() const{return m_phase==Ready;}
    QJsonObject evidence() const {
        return {{"workflow","subscription-policy-v1"},{"control",m_session.uiImportControl},
            {"phase",int(m_phase)},{"inputEvents",m_inputs},{"committedReceipts",m_receipts},
            {"readbacks",m_readbacks},{"routeWitnesses",m_routes},{"probePresentation",probePresentation()},
            {"coreRouting",QJsonObject{{"scope","actual-main-core-records-v1"},{"receipt",m_coreReceipt},{"requests",m_coreRoutes}}},
            {"sourceId",m_sourceId},{"importedNodeId",m_importedId},
            {"bootstrapNodeId",m_session.fixtureNodeId},{"probeButtonClicked",m_probeClicked},
            {"download",QJsonObject::fromVariantMap(m_controller->imports()->privateUiImportEvidence())}};
    }
    QJsonArray dnsSnapshots() const{return m_dnsSnapshots;}
    bool prepareCoreRequests() {
        if(m_corePrepared)return coreReceiptUnchanged();
        if(!m_coreBaselineRequested){
            m_coreBaselineRequested=true;
            m_coreBaselineRevision=m_controller->telemetry()->connectionRevision();
            m_controller->refresh();return false;
        }
        if(m_controller->telemetry()->connectionRevision()<=m_coreBaselineRevision)return false;
        if(!m_controller->telemetry()->connectionsSampled()||!routeMatches(m_importedId)){
            m_error="PrivateUiCoreRouteBaselineRejected";return false;
        }
        const auto receipt=m_controller->policyReceipt();
        const auto number=[](const QString &value){bool valid=false;const auto n=value.toULongLong(&valid);
            return valid&&n>0&&QRegularExpression("^[1-9][0-9]{0,19}$").match(value).hasMatch();};
        for(const auto &key:QStringList{"engine_epoch","generation","applied_revision"})
            if(!number(receipt.value(key).toString())){m_error="PrivateUiCoreRouteReceiptRejected";return false;}
        if(receipt.value("request_id").toString()!=m_recordedRequest||QUuid(receipt.value("store_id").toString()).isNull()
            ||receipt.value("applied_revision").toString()!=m_controller->savedRevision()
            ||!QRegularExpression("^[0-9a-f]{64}$").match(receipt.value("plan_digest").toString()).hasMatch()){
            m_error="PrivateUiCoreRouteReceiptRejected";return false;
        }
        for(const auto &key:QStringList{"engine_epoch","generation","store_id","request_id","applied_revision","plan_digest"})
            m_coreReceipt.insert(key,receipt.value(key).toString());
        m_corePrepared=true;return true;
    }
    bool beginCoreRequest(const QString &scheme,const QUrl &url) {
        if(!m_corePrepared||!coreReceiptUnchanged()||m_coreRequests.contains(scheme)
            ||(scheme!=QStringLiteral("http")&&scheme!=QStringLiteral("https"))
            ||url.host()!=m_session.originHost()||url.scheme()!=scheme
            ||url.port()!=(scheme==QStringLiteral("http")?m_session.fixtureHttpPort:m_session.fixtureHttpsPort))return false;
        CoreRequest request;request.port=url.port();request.beforeRevision=m_controller->telemetry()->connectionRevision();
        for(const auto &value:m_controller->connections())request.beforeIds.insert(value.toMap().value("id").toString());
        request.beforeIds.remove(QString{});m_coreRequests.insert(scheme,std::move(request));return true;
    }
    bool coreResponseFinished(const QString &scheme) {
        auto found=m_coreRequests.find(scheme);
        if(found==m_coreRequests.end()||found->finished||!coreReceiptUnchanged())return false;
        found->finished=true;found->responseRevision=m_controller->telemetry()->connectionRevision();
        // ThreadedEngine refresh is queued. Its return is not a new sample.
        m_controller->refresh();return true;
    }
    bool collectCoreRoutes() {
        if(!m_corePrepared||!coreReceiptUnchanged())return false;
        const auto revision=m_controller->telemetry()->connectionRevision();
        for(auto it=m_coreRequests.begin();it!=m_coreRequests.end();++it){
            auto &request=it.value();if(!request.finished||request.verified||revision<=request.responseRevision)continue;
            QVariantList candidates;
            for(const auto &value:m_controller->connections()){
                const auto row=value.toMap();
                if(!request.beforeIds.contains(row.value("id").toString())&&row.value("host")==m_session.originHost()
                    &&row.value("port").toInt()==request.port)candidates.append(value);
            }
            if(candidates.isEmpty()){m_controller->refresh();continue;}
            if(candidates.size()!=1){m_error="PrivateUiCoreRouteAmbiguous";return false;}
            const auto row=candidates.first().toMap(),route=row.value("route").toMap();
            const auto id=row.value("id").toString();bool idValid=false;const auto numericId=id.toULongLong(&idValid);
            if(!idValid||!numericId||QString::number(numericId)!=id||row.value("policy")!=m_importedId
                ||row.value("category")!=QStringLiteral("proxy")||row.value("rule")!=QStringLiteral("policy:default")
                ||route.value("leaf_node_id")!=m_importedId||route.value("source_id")!=m_sourceId
                ||route.value("mode")!=QStringLiteral("global")||route.value("rule_id")!=QStringLiteral("policy:default")
                ||route.value("tier").toInt()!=5||route.value("revision").toString()!=m_coreReceipt.value("applied_revision").toString()
                ||route.value("generation").toString()!=m_coreReceipt.value("generation").toString()){
                m_error="PrivateUiActualCoreRouteMismatch";return false;
            }
            auto old=request.beforeIds.values();std::sort(old.begin(),old.end());QJsonArray before;
            for(const auto &value:old)before.append(value);
            m_coreRoutes.append(QJsonObject{{"scheme",it.key()},{"id",id},{"host",row.value("host").toString()},{"port",request.port},
                {"category",row.value("category").toString()},{"nodeReference",NodeTestService::nodeReference(row.value("policy").toString())},
                {"leafNodeReference",NodeTestService::nodeReference(route.value("leaf_node_id").toString())},
                {"sourceReference",NodeTestService::nodeReference(route.value("source_id").toString())},
                {"rule",row.value("rule").toString()},{"ruleId",route.value("rule_id").toString()},{"mode",route.value("mode").toString()},
                {"tier",route.value("tier").toInt()},{"revision",route.value("revision").toString()},{"generation",route.value("generation").toString()},
                {"beforeConnectionRevision",QString::number(request.beforeRevision)},
                {"responseConnectionRevision",QString::number(request.responseRevision)},
                {"observedConnectionRevision",QString::number(revision)},{"preexistingConnectionIds",before},{"closed",row.value("closed").toBool()}});
            request.verified=true;
        }
        return m_coreRoutes.size()==2;
    }
    bool displayedProbe(qint64 latency,int status,qint64 outboundMs) const {
        auto *label=item("nodeRequestState");
        return m_probeClicked&&label&&label->isVisible()&&value("pageLoader.item.selectedId").toString()==m_importedId
            &&value("pageLoader.item.tested.latency").toLongLong()==latency
            &&value("pageLoader.item.tested.http").toInt()==status
            &&outboundMs>=0&&value("pageLoader.item.tested.outboundConnectMs").toLongLong()==outboundMs
            &&label->property("text").toString().contains(QStringLiteral("HTTP %1").arg(status))
            &&label->property("text").toString().contains(QStringLiteral("%1 ms").arg(outboundMs));
    }
    QJsonObject probePresentation() const {
        auto *label=m_probeClicked?item("nodeRequestState"):nullptr;
        const auto id=m_probeClicked?value("pageLoader.item.selectedId").toString():QString{};
        const auto latency=m_probeClicked?value("pageLoader.item.tested.latency"):QVariant{};
        const auto outbound=m_probeClicked?value("pageLoader.item.tested.outboundConnectMs"):QVariant{};
        return {{"visible",label&&label->isVisible()},{"text",label?label->property("text").toString():QString{}},
            {"nodeReference",id.isEmpty()?QString{}:NodeTestService::nodeReference(id)},
            {"latency",latency.isValid()?latency.toLongLong():-1},{"outboundConnectMs",outbound.isValid()?outbound.toLongLong():-1},
            {"httpStatus",m_probeClicked?value("pageLoader.item.tested.http").toInt():0}};
    }
    bool witnessRoute(const QString &stage,const QString &resultReference={}) {
        const auto receipt=m_controller->policyReceipt();
        const auto target=m_controller->policyDocument().value("default_policy").toMap().value("target").toMap();
        const auto reference=NodeTestService::nodeReference(m_importedId);
        if(m_importedId.isEmpty()||!routeMatches(m_importedId)||target.value("kind")!=QStringLiteral("node")
            ||target.value("id")!=m_importedId||receipt.value("request_id").toString()!=m_recordedRequest
            ||(stage==QStringLiteral("probe-result")?resultReference!=reference:!resultReference.isEmpty()))return false;
        for(const auto &entry:m_routes)if(entry.toObject().value("stage")==stage)return false;
        if(m_session.uiDnsPolicy){
            QJsonObject guard;
            if(!m_session.dnsTrust||!m_session.dnsTrust->snapshot(&guard))return false;
            m_dnsSnapshots.append(QJsonObject{{"stage",stage},{"guard",guard}});
        }
        m_routes.append(QJsonObject{{"stage",stage},{"selectedNodeReference",NodeTestService::nodeReference(m_controller->selectedNodeId())},
            {"activeNodeReference",NodeTestService::nodeReference(m_controller->activeNodeId())},
            {"defaultNodeReference",NodeTestService::nodeReference(target.value("id").toString())},
            {"resultNodeReference",resultReference},{"request_id",receipt.value("request_id").toString()},
            {"saved_revision",m_controller->savedRevision()},{"applied_revision",m_controller->appliedRevision()},
            {"plan_digest",receipt.value("plan_digest").toString()},{"proxyPort",m_controller->activeProxyPort()},
            {"routingMode",m_controller->routingMode()}});
        return true;
    }
    void advance() {
        if(!m_error.isEmpty()||ready())return;
        const auto failure=m_controller->imports()->privateUiImportEvidence().value("failureCode").toString();
        if(!failure.isEmpty()){m_error=failure;return;}
        if(!m_controller->policyError().isEmpty()){m_error="PrivateUiPolicyTransactionFailed";return;}
        switch(m_phase){
        case PolicyPage:
            if(pageSettled("policies")){if(!m_controller->policyMigrationRequired()){m_error="PrivateUiMigrationExpected";return;}m_phase=MigrationReview;}break;
        case MigrationReview: if(click("reviewPolicyMigration","review-migration"))m_phase=MigrationConfirm;break;
        case MigrationConfirm: if(commitClick("confirmPolicyMigration","confirm-migration"))m_phase=MigrationWait;break;
        case MigrationWait: if(committed("migration")&&!modalVisible("policyMigrationDialog"))m_phase=BootstrapPicker;break;
        case BootstrapPicker: if(click("defaultPolicyTarget","bootstrap-picker"))m_phase=BootstrapNode;break;
        case BootstrapNode: if(click("policyNode-"+m_session.fixtureNodeId,"bootstrap-node"))m_phase=BootstrapConfirm;break;
        case BootstrapConfirm: if(commitClick("confirmPolicyTarget","bootstrap-confirm"))m_phase=BootstrapWait;break;
        case BootstrapWait:
            if(committed("bootstrap-target")&&!modalVisible("policyTargetPicker")){
                if(m_controller->selectedNodeId()!=m_session.fixtureNodeId){m_error="PrivateUiBootstrapPolicyMismatch";return;}
                m_phase=ModePicker;
            }break;
        case ModePicker: if(click("routingModePicker","mode-picker"))m_phase=ModeOption;break;
        case ModeOption: if(commitClick("swirlComboOption-1","global-mode"))m_phase=ModeWait;break;
        case ModeWait:
            if(committed("global-mode")&&m_controller->policyDocument().value("mode")==QStringLiteral("global")){
                if(!m_controller->canStart()){m_error="PrivateUiBootstrapStartRejected";return;}
                // Connection startup has no external request. Its exit choice
                // was committed by the real policy controls above.
                m_controller->connectNode(m_session.fixtureNodeId);m_phase=BootstrapRunning;
            }break;
        case BootstrapRunning:
            if(m_controller->apiHealthy()){
                if(!routeMatches(m_session.fixtureNodeId)){m_error="PrivateUiBootstrapRouteMismatch";return;}
                if(navigate("subscriptions"))m_phase=SubscriptionsPage;
            }break;
        case SubscriptionsPage: if(pageSettled("subscriptions"))m_phase=AddSource;break;
        case AddSource: if(click("addSubscription","add-subscription"))m_phase=NameField;break;
        case NameField: if(fill("subscriptionName",QStringLiteral("Synthetic owned subscription"),"subscription-name"))m_phase=UrlField;break;
        case UrlField: {
            auto url=m_session.subscriptionUrl();
            if(m_session.uiImportControl==QStringLiteral("wrong-url"))url.setPath(url.path()+QStringLiteral(".unexpected"));
            if(fill("subscriptionUrl",url.toString(QUrl::FullyEncoded),"subscription-url"))m_phase=AutoFocus;
            break;
        }
        case AutoFocus:
            // Focus traversal uses the actual adjacent form controls. Setting a
            // read-only QML property or invoking saveSource() would not prove UI.
            if(auto *interval=item("subscriptionInterval")){
                interval->forceActiveFocus(Qt::TabFocusReason);m_interval=interval;
                QTest::keyClick(m_window,Qt::Key_Tab,Qt::NoModifier,0);m_phase=AutoToggle;
            }break;
        case AutoToggle: {
            auto *toggle=m_window->activeFocusItem();auto *dialog=object("subscriptionDialog");
            if(!toggle||!m_interval||toggle->parentItem()!=m_interval->parentItem()
                ||!toggle->property("checked").isValid()||!dialog){m_error="PrivateUiAutomaticRefreshInputMissing";return;}
            if(!stable(toggle))break;
            if(!dialog->property("autoUpdate").toBool()){m_error="PrivateUiAutomaticRefreshUnexpected";return;}
            QTest::keyClick(m_window,Qt::Key_Space,Qt::NoModifier,0);
            m_inputs.append("disable-automatic-refresh");m_phase=AutoVerify;break;
        }
        case AutoVerify:
            if(auto *dialog=object("subscriptionDialog")){
                if(dialog->property("autoUpdate").toBool()){m_error="PrivateUiAutomaticRefreshStillEnabled";return;}
                m_phase=SaveSource;
            }break;
        case SaveSource:
            if(auto *button=item("saveSubscription");stable(button)){
                // Starts the existing request-phase clock once, before the
                // form can issue its automatic single post-save refresh.
                if(!m_networkPhase()){m_error="PrivateUiRequestPhaseRejected";return;}
                m_beforeRequest=m_controller->policyReceipt().value("request_id").toString();
                press(button,"save-subscription");m_phase=ImportWait;
            }break;
        case ImportWait:
            if(!m_controller->imports()->busy()&&!m_controller->policyBusy()&&!modalVisible("subscriptionDialog")
                &&m_controller->imports()->privateUiImportEvidence().value("responseVerified").toBool()){
                if(!captureCurrentReceipt("subscription-import")||!readback(false)){m_error="PrivateUiImportedStoreMismatch";return;}
                m_imported=true;m_phase=SelectSource;
            }break;
        case SelectSource: if(commitClick("useSubscription-"+m_sourceId,"use-subscription"))m_phase=SourceWait;break;
        case SourceWait:
            if(committed("subscription-scope")){
                if(!m_controller->subscriptionScopeEnabled()||m_controller->activeSubscriptionId()!=m_sourceId){m_error="PrivateUiSourceScopeMismatch";return;}
                if(navigate("policies"))m_phase=ImportedPolicyPage;
            }break;
        case ImportedPolicyPage: if(pageSettled("policies"))m_phase=ImportedPicker;break;
        case ImportedPicker: if(click("defaultPolicyTarget","imported-picker"))m_phase=ImportedNode;break;
        case ImportedNode: if(click("policyNode-"+m_importedId,"imported-node"))m_phase=ImportedConfirm;break;
        case ImportedConfirm: if(commitClick("confirmPolicyTarget","imported-confirm"))m_phase=ImportedWait;break;
        case ImportedWait:
            if(committed("imported-target")&&!modalVisible("policyTargetPicker")){
                // The finish reply and its status snapshot are queued separately.
                // Wait under the existing request deadline before admitting probes.
                if(!routeMatches(m_importedId))break;
                if(!readback(true)||!witnessRoute("policy-applied")){m_error="PrivateUiImportedPolicyMismatch";return;}
                m_policySelected=true;if(navigate("proxies"))m_phase=NodesPage;
            }break;
        case NodesPage: if(pageSettled("proxies"))m_phase=NodeDetail;break;
        case NodeDetail:
            if(auto *row=nodeRow(m_window->contentItem(),m_importedId);stable(row)){
                const auto point=row->mapToScene(QPointF(qMin(70.0,row->width()/2),row->height()/2)).toPoint();
                QTest::mouseClick(m_window,Qt::LeftButton,Qt::NoModifier,point,0);
                QTest::mouseDClick(m_window,Qt::LeftButton,Qt::NoModifier,point,0);
                m_inputs.append("open-imported-node-details");m_phase=ProbeField;
            }break;
        case ProbeField:
            if(auto *hero=item("nodeHero");hero&&hero->property("opened").toBool()&&!hero->property("moving").toBool()){
                if(value("pageLoader.item.selectedId").toString()!=m_importedId||!routeMatches(m_importedId)){m_error="PrivateUiInspectedNodeMismatch";return;}
                if(fill("nodeTestUrl",QStringLiteral("http://%1:%2/generate_204").arg(m_session.originHost()).arg(m_session.fixtureHttpPort),"probe-url"))m_phase=ProbeButton;
            }break;
        case ProbeButton:
            if(auto *button=item("nodeTestButton");stable(button)){
                if(!witnessRoute("probe-click")){m_error="PrivateUiProbeRouteMismatch";return;}
                press(button,"probe-button");m_probeClicked=true;m_phase=Ready;
            }break;
        case Ready:break;
        }
    }
private:
    enum Phase {PolicyPage,MigrationReview,MigrationConfirm,MigrationWait,BootstrapPicker,BootstrapNode,BootstrapConfirm,
        BootstrapWait,ModePicker,ModeOption,ModeWait,BootstrapRunning,SubscriptionsPage,AddSource,NameField,UrlField,
        AutoFocus,AutoToggle,AutoVerify,SaveSource,ImportWait,SelectSource,SourceWait,ImportedPolicyPage,ImportedPicker,
        ImportedNode,ImportedConfirm,ImportedWait,NodesPage,NodeDetail,ProbeField,ProbeButton,Ready};
    QQuickWindow *m_window;EngineController *m_controller;ControlledNodeSession m_session;
    std::function<bool()> m_networkPhase;Phase m_phase=PolicyPage;
    QString m_error,m_sourceId,m_importedId,m_beforeRequest,m_recordedRequest;
    QHash<QString,bool> m_completions;QJsonArray m_inputs,m_receipts,m_readbacks,m_routes,m_dnsSnapshots;
    struct CoreRequest {int port=0;quint64 beforeRevision=0,responseRevision=0;QSet<QString> beforeIds;bool finished=false,verified=false;};
    QHash<QString,CoreRequest> m_coreRequests;QJsonObject m_coreReceipt;QJsonArray m_coreRoutes;
    quint64 m_coreBaselineRevision=0;bool m_coreBaselineRequested=false,m_corePrepared=false;
    QPointer<QQuickItem> m_lastTarget,m_interval;QRectF m_lastRect;
    bool m_imported=false,m_policySelected=false,m_probeClicked=false;
    QVariant value(const QString &expression) const {
        QQmlExpression query(qmlContext(m_window),m_window,expression);const auto result=query.evaluate();
        return query.hasError()?QVariant{}:result;
    }
    bool navigate(const char *route) {
        QQmlExpression query(qmlContext(m_window),m_window,QStringLiteral("AppState.navigate('%1')").arg(QString::fromLatin1(route)));
        query.evaluate();if(query.hasError()){m_error="PrivateUiNavigationFailed";return false;}return true;
    }
    bool pageSettled(const char *route) const {
        auto *host=m_window->findChild<QObject *>("pageLoader");
        auto *active=host?qvariant_cast<QObject *>(host->property("activeLoader")):nullptr;
        return active&&active->property("routeId").toString()==QString::fromLatin1(route)
            &&!host->property("moving").toBool()&&!host->property("pendingGrab").toBool();
    }
    static QQuickItem *findItem(QQuickItem *parent,const QString &name) {
        if(parent->objectName()==name&&parent->isVisible())return parent;
        for(auto *child:parent->childItems())if(auto *found=findItem(child,name))return found;
        return nullptr;
    }
    QQuickItem *item(const QString &name) const {
        if(auto *found=findItem(m_window->contentItem(),name))return found;
        for(auto *candidate:m_window->findChildren<QQuickItem *>(name))if(candidate->isVisible()&&candidate->window())return candidate;
        return nullptr;
    }
    QObject *object(const QString &name) const {
        for(auto *candidate:m_window->findChildren<QObject *>(name))if(candidate->property("visible").toBool())return candidate;
        std::function<QObject *(QQuickItem *)> visual=[&](QQuickItem *parent)->QObject *{
            for(auto *candidate:parent->findChildren<QObject *>(name))if(candidate->property("visible").toBool())return candidate;
            for(auto *child:parent->childItems())if(auto *found=visual(child))return found;
            return nullptr;
        };
        if(auto *found=visual(m_window->contentItem()))return found;
        return nullptr;
    }
    bool modalVisible(const QString &name) const {return object(name)!=nullptr;}
    bool stable(QQuickItem *target) {
        if(!target||!target->isVisible()||!target->isEnabled()||target->width()<=0||target->height()<=0)return false;
        const auto rect=target->mapRectToScene(QRectF(QPointF(),target->size()));const auto point=rect.center();qreal opacity=1;
        for(auto *ancestor=target;ancestor;ancestor=ancestor->parentItem()){
            opacity*=ancestor->opacity();if(ancestor->clip()&&!ancestor->mapRectToScene(QRectF(QPointF(),ancestor->size())).contains(point))return false;
        }
        if(opacity<=0.95||!target->window()||!QRectF(0,0,m_window->width(),m_window->height()).contains(point))return false;
        const bool settled=m_lastTarget==target&&qAbs(rect.x()-m_lastRect.x())<0.5&&qAbs(rect.y()-m_lastRect.y())<0.5
            &&qAbs(rect.width()-m_lastRect.width())<0.5&&qAbs(rect.height()-m_lastRect.height())<0.5;
        m_lastTarget=target;m_lastRect=rect;return settled;
    }
    void press(QQuickItem *target,const char *label) {
        QTest::mouseClick(target->window(),Qt::LeftButton,Qt::NoModifier,
            target->mapToScene(QPointF(target->width()/2,target->height()/2)).toPoint(),0);
        m_inputs.append(QString::fromLatin1(label));m_lastTarget.clear();
    }
    bool click(const QString &name,const char *label) {
        auto *target=item(name);if(!stable(target))return false;press(target,label);return true;
    }
    bool commitClick(const QString &name,const char *label) {
        auto *target=item(name);if(!stable(target))return false;
        m_beforeRequest=m_controller->policyReceipt().value("request_id").toString();press(target,label);return true;
    }
    bool fill(const QString &name,const QString &text,const char *label) {
        auto *field=item(name);if(!field)return false;
        field->forceActiveFocus(Qt::TabFocusReason);if(!stable(field))return false;
        for(const auto ch:text)if(ch.unicode()>=128){m_error="PrivateUiKeyboardInputRejected";return false;}
        QTest::keyClick(m_window,Qt::Key_A,Qt::ControlModifier,0);
        for(const auto ch:text)QTest::keyClick(m_window,ch.toLatin1(),Qt::NoModifier,0);
        if(field->property("text").toString()!=text){m_error="PrivateUiKeyboardInputUnconfirmed";return false;}
        m_inputs.append(QString::fromLatin1(label));m_lastTarget.clear();return true;
    }
    bool captureCurrentReceipt(const char *label) {
        const auto receipt=QJsonObject::fromVariantMap(m_controller->policyReceipt());const auto id=receipt.value("request_id").toString();
        const bool online=m_controller->processAlive();const auto savedRevision=m_controller->savedRevision();
        // Online Core receipts expose applied_revision; saved_revision belongs
        // to the durable NodeStore receipt. Select by the actual engine state,
        // never by whichever field happens to be present in the response.
        const auto revision=receipt.value(online?QStringLiteral("applied_revision"):QStringLiteral("saved_revision"));
        if(id.isEmpty()||id==m_beforeRequest||QUuid(id).isNull()||!m_completions.value(id,false)
            ||m_controller->policyBusy()||m_controller->policyApplyState()!=QStringLiteral("idle")
            ||savedRevision.isEmpty()||!revision.isString()||revision.toString()!=savedRevision
            ||(online&&!m_controller->apiHealthy())
            ||QUuid(receipt.value("store_id").toString()).isNull()
            ||!QRegularExpression("^[0-9a-f]{64}$").match(receipt.value("plan_digest").toString()).hasMatch())return false;
        if(id!=m_recordedRequest){
            // saved_revision below is the observed controller NodeStore value,
            // not an added field or a replacement for the actual Core receipt.
            m_receipts.append(QJsonObject{{"stage",QString::fromLatin1(label)},{"request_id",id},{"store_id",receipt.value("store_id")},
                {"saved_revision",savedRevision},{"applied_revision",receipt.value("applied_revision").toString()},
                {"plan_digest",receipt.value("plan_digest")}});m_recordedRequest=id;
        }
        return true;
    }
    bool committed(const char *label) {
        if(m_controller->policyBusy())return false;
        const auto issued=m_controller->policyRequestId();
        if(!issued.isEmpty()&&issued!=m_beforeRequest&&m_completions.contains(issued)&&!m_completions.value(issued)){
            m_error="PrivateUiPolicyCommitRejected";return false;
        }
        return captureCurrentReceipt(label);
    }
    bool routeMatches(const QString &id) const {
        return m_controller->apiHealthy()&&!m_controller->policyBusy()&&m_controller->selectedNodeId()==id
            &&m_controller->activeNodeId()==id&&m_controller->routingMode()==QStringLiteral("global")
            &&m_controller->activeProxyPort()==m_session.proxyPort&&!m_controller->tunRequested()&&!m_controller->proxyRequested()
            &&m_controller->appliedRevision()==m_controller->savedRevision();
    }
    bool coreReceiptUnchanged() {
        const auto receipt=m_controller->policyReceipt();
        if(!routeMatches(m_importedId)){m_error="PrivateUiCoreRouteReceiptChanged";return false;}
        for(auto it=m_coreReceipt.begin();it!=m_coreReceipt.end();++it)if(receipt.value(it.key()).toString()!=it.value().toString()){
            m_error="PrivateUiCoreRouteReceiptChanged";return false;
        }
        return true;
    }
    bool readback(bool selected) {
        // A live V2 store owns its writer lock. Reopen the exact committed
        // ciphertext at an independent path so validation cannot contend with
        // the application's lock or recover/mutate its active store.
        QFile ciphertext(m_session.storePath);if(!ciphertext.open(QIODevice::ReadOnly))return false;
        const auto bytes=ciphertext.read(NodeStore::MaximumBytes+1);
        if(ciphertext.error()!=QFile::NoError||bytes.isEmpty()||bytes.size()>NodeStore::MaximumBytes)return false;
        ciphertext.close();
        QTemporaryDir snapshotDirectory;if(!snapshotDirectory.isValid())return false;
        const auto snapshotPath=snapshotDirectory.filePath(QStringLiteral("nodes.dpapi"));
        QFile snapshot(snapshotPath);
        if(!snapshot.open(QIODevice::WriteOnly|QIODevice::NewOnly)||snapshot.write(bytes)!=bytes.size()||!snapshot.flush())return false;
        snapshot.close();
        NodeStore reopened(snapshotPath);const auto providers=reopened.subscriptions();const auto nodes=reopened.nodes();
        const auto actualReceipt=QJsonObject::fromVariantMap(m_controller->policyReceipt());
        const auto durableReceipt=reopened.configurationReceipt();const auto savedRevision=m_controller->savedRevision();
        if(!reopened.error().isEmpty()||reopened.saving()||!reopened.configurationAvailable()||!reopened.configurationV2()
            ||providers.size()!=1||nodes.size()!=2||durableReceipt.value("request_id")!=actualReceipt.value("request_id")
            ||durableReceipt.value("store_id")!=actualReceipt.value("store_id")
            ||!durableReceipt.value("saved_revision").isString()||durableReceipt.value("saved_revision").toString()!=savedRevision
            ||reopened.configurationRevision()!=savedRevision||durableReceipt.value("plan_digest")!=actualReceipt.value("plan_digest"))return false;
        if(m_session.uiDnsPolicy&&reopened.networkConfiguration().value("dns").toObject()
            !=QJsonObject::fromVariantMap(m_session.dnsConfiguration()))return false;
        const auto &source=providers.first();
        if(QUuid(source.id).isNull()||source.name!=QStringLiteral("Synthetic owned subscription")||source.url!=m_session.subscriptionUrl()
            ||source.enabled||source.intervalMinutes!=1440||source.formatHint!=QStringLiteral("auto")||source.downloadRoute!=QStringLiteral("system")
            ||source.lastSuccess<=0||(!m_sourceId.isEmpty()&&source.id!=m_sourceId))return false;
        const auto expected=NodeImporter::parse(m_session.subscriptionBody());if(!expected||expected.nodes.size()!=1)return false;
        const auto &parsed=expected.nodes.first();QString imported;QJsonObject expectedOutbound;
        if(!NativeNodeBridge::executableOutbound(parsed,&expectedOutbound).isEmpty())return false;
        for(const auto &node:nodes){
            if(node.id==m_session.fixtureNodeId){
                if(!node.sourceId.isEmpty()||node.importSource!=QStringLiteral("manual")||node.protocol!=QStringLiteral("socks5")
                    ||node.host!=QStringLiteral("127.0.0.1")||node.port!=m_session.fixtureSocksPort
                    ||node.username!=QStringLiteral("fixture")||node.password!=m_session.fixturePassword)return false;
            }else{
                QJsonObject actualOutbound;
                if(!imported.isEmpty()||QUuid(node.id).isNull()||node.sourceId!=source.id||node.name!=parsed.name
                    ||node.protocol!=parsed.protocol||node.host!=parsed.host||node.port!=parsed.port||node.username!=parsed.username
                    ||node.password!=parsed.password||node.parameters!=parsed.parameters||node.importSource!=QStringLiteral("subscription")
                    ||!NativeNodeBridge::executableOutbound(node,&actualOutbound).isEmpty()||actualOutbound!=expectedOutbound)return false;
                imported=node.id;
            }
        }
        const bool actualSelected=reopened.selectedId()==imported;
        if(imported.isEmpty()||(!m_importedId.isEmpty()&&m_importedId!=imported)||actualSelected!=selected)return false;
        if(!ciphertext.open(QIODevice::ReadOnly)||ciphertext.read(NodeStore::MaximumBytes+1)!=bytes||ciphertext.error()!=QFile::NoError)return false;
        if(!snapshot.open(QIODevice::ReadOnly)||snapshot.read(NodeStore::MaximumBytes+1)!=bytes||snapshot.error()!=QFile::NoError)return false;
        m_sourceId=source.id;m_importedId=imported;
        m_readbacks.append(QJsonObject{{"stage",selected?"selected-imported-node":"imported-catalog"},{"independentNodeStore",true},
            {"configurationV2",true},{"sourceCount",1},{"nodeCount",2},{"importedNodeId",imported},{"sourceId",source.id},
            {"selectedImportedNode",actualSelected},{"saved_revision",reopened.configurationRevision()},
            {"ciphertextSha256",QString::fromLatin1(QCryptographicHash::hash(bytes,QCryptographicHash::Sha256).toHex())}});
        return true;
    }
    static QQuickItem *nodeRow(QQuickItem *parent,const QString &id) {
        const auto value=parent->property("record");
        const auto row=value.metaType()==QMetaType::fromType<QJSValue>()?value.value<QJSValue>().toVariant().toMap():value.toMap();
        if(row.value("rowKind")==QStringLiteral("node")&&row.value("id")==id&&!parent->property("pooled").toBool())return parent;
        for(auto *child:parent->childItems())if(auto *found=nodeRow(child,id))return found;
        return nullptr;
    }
};
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
        if(!m_session.uiImportPolicy)m_controller->imports()->shutdown();
        auto &library=RustCoreLibrary::instance();
        if(!library.load()||library.expectedSourceSha()!=m_session.sourceSha){fail("PairedCoreIdentityRequired");return;}
        const auto nodes=m_controller->nodes();
        if(m_session.nodeOrdinal!=1||nodes.size()!=1||!controlledFixtureCatalog(m_session)){
            fail("OwnedSyntheticCatalogRequired");return;
        }
        m_id=nodes.first().toMap().value("id").toString();
        if(m_id!=m_session.fixtureNodeId||!m_controller->prepareRealAcceptance()){fail("IsolatedSessionUnavailable");return;}
        m_controller->setProxyPort(m_session.proxyPort);
#ifdef SWIRL_PRIVATE_UI_QUOTA
        if(m_session.uiImportPolicy){
            if(m_session.uiDnsPolicy){
                if(!m_session.dnsTrust||!m_controller->canStart()
                    ||!m_controller->configureDns(m_session.dnsConfiguration())){fail("PrivateUiDnsConfigurationRejected");return;}
                NodeStore reloaded(m_session.storePath);
                const auto actual=reloaded.networkConfiguration().value("dns").toObject();
                if(!reloaded.error().isEmpty()||actual!=QJsonObject::fromVariantMap(m_session.dnsConfiguration())
                    ||m_controller->dnsConfiguration()!=m_session.dnsConfiguration()){
                    fail("PrivateUiDnsPersistenceUnconfirmed");return;
                }
                m_dnsConfigurationSha=QString::fromLatin1(QCryptographicHash::hash(
                    QJsonDocument(actual).toJson(QJsonDocument::Compact),QCryptographicHash::Sha256).toHex());
                m_dnsConfigured=true;
            }
            m_window->resize(1450,884); // Existing node-input fixture geometry; normal animations stay enabled.
            m_importUi=std::make_unique<ControlledImportUi>(m_window,m_controller,m_session,[this]{return beginNetworkPhase();},this);
            if(!publish("ui-import-policy")||!m_importUi->begin()){fail("PrivateUiNavigationFailed");return;}
            m_begun=true;m_timer.start();QTimer::singleShot(0,this,[this]{tick();});return;
        }
#endif
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
    bool m_networkPhaseStarted=false;
#ifdef SWIRL_PRIVATE_UI_QUOTA
    std::unique_ptr<ControlledImportUi> m_importUi;
    bool m_uiTick=false;
    bool m_dnsConfigured=false;
    QString m_dnsConfigurationSha;
#endif
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
    bool beginNetworkPhase() {
        if(m_networkPhaseStarted)return true;
        const auto now=controlledNowNs();
        if(now>=controlledStartedNs+20'000'000'000LL)return false;
        m_networkPhaseStarted=true;m_requestsClock.start();
        controlledRequestStartedNs.store(now,std::memory_order_release);
        return true;
    }
    void proxyRequests(bool probeAlreadyClicked) {
        if(m_stopping||m_done)return;
        if(!beginNetworkPhase()){fail("StartupDeadlineExceeded");return;}
        m_requestsStarted=true;
        if(!publish("requests")){fail("PrivateReceiptWriteFailed");return;}
        m_network.setProxy(QNetworkProxy(QNetworkProxy::HttpProxy,QStringLiteral("127.0.0.1"),quint16(m_session.proxyPort)));
        if(!probeAlreadyClicked){
            const auto probe=QUrl(QString("http://%1:%2/generate_204").arg(m_session.originHost()).arg(m_session.fixtureHttpPort));
            m_controller->testSelectedNode(m_id,probe);
        }
        request("http",QUrl(QString("http://%1:%2/").arg(m_session.originHost()).arg(m_session.fixtureHttpPort)));
        if(m_stopping||m_done)return;
        if(m_session.uiDnsPolicy)return; // The real HTTP completion admits HTTPS below, without a new clock.
        request("https",QUrl(QString("https://%1:%2/trace").arg(m_session.originHost()).arg(m_session.fixtureHttpsPort)));
    }
    void request(const char *scheme,const QUrl &url) {
        if(m_stopping||m_done)return;
#ifdef SWIRL_PRIVATE_UI_QUOTA
        if(m_importUi&&!m_importUi->witnessRoute(QStringLiteral("proxy-%1-start").arg(QString::fromLatin1(scheme)))){
            fail("PrivateUiNormalProxyRouteMismatch");return;
        }
        if(m_importUi&&!m_importUi->beginCoreRequest(QString::fromLatin1(scheme),url)){
            fail("PrivateUiCoreRouteRequestRejected");return;
        }
#endif
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
#ifdef SWIRL_PRIVATE_UI_QUOTA
            const bool routeRejected=m_importUi&&!m_stopping
                &&!m_importUi->witnessRoute(QStringLiteral("proxy-%1-complete").arg(QString::fromLatin1(scheme)));
            if(routeRejected&&m_error.isEmpty())m_error="PrivateUiNormalProxyRouteMismatch";
#endif
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
#ifdef SWIRL_PRIVATE_UI_QUOTA
            // Store this completed response before aborting peers: abort can
            // synchronously run their finished handlers and finish the run.
            if(routeRejected){stop();return;}
            if(m_importUi&&!m_stopping&&!m_done){
                if(!succeeded||!sealed){fail("PrivateUiNormalProxyResponseFailed");return;}
                if(!m_importUi->coreResponseFinished(QString::fromLatin1(scheme))){
                    fail("PrivateUiCoreRouteResponseRejected");return;
                }
            }
#endif
            if(m_session.uiDnsPolicy&&QByteArray(scheme)=="http"&&!m_stopping&&!m_done){
                if(!succeeded||!sealed){fail("PrivateUiDnsHttpFailed");return;}
                request("https",QUrl(QString("https://%1:%2/trace").arg(m_session.originHost()).arg(m_session.fixtureHttpsPort)));
            }
            tick();
        });
    }
    bool collectProbe() {
        if(m_probeCompleted||m_controller->tests()->busy())return true;
        const auto probe=m_controller->tests()->result(m_id);if(probe.isEmpty())return true;
#ifdef SWIRL_PRIVATE_UI_QUOTA
        if(m_importUi&&!m_importUi->witnessRoute("probe-result",probe.value("nodeReference").toString())){
            fail("PrivateUiProbeResultReferenceMismatch");return false;
        }
#endif
        m_probeCompleted=true;m_probeSuccess=probe.value("success").toBool();m_uiLatency=probe.value("latency",-1).toLongLong();
        m_probeHttp=probe.value("http").toInt();m_probePhase=probe.value("phase").toString();
        m_probeFailureCode=probe.value("failureCode").toString();
        m_outboundConnectMs=probe.value("outboundConnectMs",-1).toLongLong();m_originTlsMs=probe.value("originTlsMs",-1).toLongLong();
        return true;
    }
    void tick() {
#ifdef SWIRL_PRIVATE_UI_QUOTA
        if(m_importUi&&m_uiTick)return;
        QScopedValueRollback<bool> tickScope(m_uiTick,true);
#endif
        if(m_done||(!m_begun&&!m_stopping))return;
        if(m_stopping){
            if(m_replies.isEmpty()&&!m_controller->tests()->busy()&&!m_controller->processAlive()&&!m_controller->busy()
                &&(!m_session.uiImportPolicy||!m_controller->imports()->busy()))finish();
            return;
        }
        if(!m_requestsStarted){
            if(m_clock.elapsed()>=20000){fail("StartupDeadlineExceeded");return;}
#ifdef SWIRL_PRIVATE_UI_QUOTA
            if(m_importUi){
                if(m_networkPhaseStarted&&m_requestsClock.elapsed()>=8000){fail("RequestDeadlineExceeded");return;}
                m_importUi->advance();
                if(!m_importUi->error().isEmpty()){fail(m_importUi->error());return;}
                if(!m_importUi->ready())return;
                m_id=m_importUi->importedId();
                if(m_session.uiDnsPolicy){
                    if(!collectProbe()||!m_probeCompleted)return;
                    if(!m_probeSuccess){fail("PrivateUiDnsProbeFailed");return;}
                }
                if(!m_importUi->prepareCoreRequests()){
                    if(!m_importUi->error().isEmpty())fail(m_importUi->error());
                    return;
                }
                proxyRequests(true);
            }else
#endif
            {
            if(!m_connectRequested&&!m_controller->busy()){
                if(m_controller->selectedNodeId()!=m_id){fail("NodeSelectionUnconfirmed");return;}
                m_connectRequested=true;m_controller->connectNode(m_id);return;
            }
            if(!m_controller->apiHealthy())return;
            if(m_controller->activeNodeId()!=m_id||m_controller->routingMode()!=QStringLiteral("global")
                ||m_controller->activeProxyPort()!=m_session.proxyPort||m_controller->tunRequested()||m_controller->proxyRequested()){
                fail("SelectedProxyRouteUnconfirmed");return;
            }
            // All three requests use the same explicit selected node. There is
            // no direct-mode or alternative-node retry on any failed response.
            // The Rust HEAD fixture is HTTP on loopback; HTTPS is independently
            // exercised below with a fixture-only, peer-verified Qt trust set.
            proxyRequests(false);
            }
        }
        if(m_stopping||m_done||!m_requestsStarted)return;
#ifdef SWIRL_PRIVATE_UI_QUOTA
        if(m_importUi&&m_requestsClock.elapsed()>=8000){fail("RequestDeadlineExceeded");return;}
#endif
        if(!collectProbe())return;
        bool coreRoutesComplete=true;
#ifdef SWIRL_PRIVATE_UI_QUOTA
        if(m_importUi){
            coreRoutesComplete=m_importUi->collectCoreRoutes();
            if(!m_importUi->error().isEmpty()){fail(m_importUi->error());return;}
        }
#endif
        if(m_probeCompleted&&m_completed==2&&coreRoutesComplete){
#ifdef SWIRL_PRIVATE_UI_QUOTA
            // Evidence may arrive asynchronously. Recheck the same clock after
            // sampling; a late route record cannot turn timeout into success.
            if(m_importUi&&m_requestsClock.elapsed()>=8000){fail("RequestDeadlineExceeded");return;}
#endif
            stop();return;
        }
        if(m_requestsClock.elapsed()>=8000)fail("RequestDeadlineExceeded");
    }
    void stop() {
        if(m_stopping||m_done)return;
        m_stopping=true;publish("stopping");
        const auto replies=m_replies;
        for(auto *reply:replies)reply->abort();
        if(m_session.uiImportPolicy)m_controller->imports()->shutdown();
        m_controller->tests()->cancel();m_controller->stop();
        m_timer.start();QTimer::singleShot(0,this,[this]{tick();});
    }
    void finish() {
        m_done=true;m_timer.stop();
        bool httpPassed=m_http.size()==2;
        bool exitObserved=false;
        for(const auto &entry:m_http){const auto row=entry.toObject();httpPassed=httpPassed&&row.value("success").toBool();exitObserved=exitObserved||!row.value("exitIpSha256").toString().isEmpty();}
        bool uiImport=false,uiPolicy=false;
#ifdef SWIRL_PRIVATE_UI_QUOTA
        bool uiProbe=false,uiDisplay=false;
        if(m_importUi){
            uiImport=m_importUi->importExercised();uiPolicy=m_importUi->policyExercised();uiProbe=m_importUi->probeClicked();
            uiDisplay=m_importUi->displayedProbe(m_uiLatency,m_probeHttp,m_outboundConnectMs);
            if(m_error.isEmpty()&&(!uiImport||!uiPolicy||!uiProbe||!uiDisplay))m_error="PrivateUiSurfaceEvidenceIncomplete";
        }
#endif
        const bool passed=m_error.isEmpty()&&m_probeCompleted&&m_probeSuccess&&httpPassed&&exitObserved;
        QJsonObject result{{"schema",1},{"nonce",m_session.nonce},{"sourceSha",m_session.sourceSha},
            {"nodeOrdinal",m_session.nodeOrdinal},{"passed",passed},{"failureCode",m_error},
            {"selectedNodeReference",NodeTestService::nodeReference(m_id)},{"probeCompleted",m_probeCompleted},
            {"probeSuccess",m_probeSuccess},{"uiHeadersMs",m_uiLatency},{"proxyRequests",m_http},
            {"probeHttpStatus",m_probeHttp},{"probePhase",m_probePhase},{"probeFailureCode",m_probeFailureCode},
            {"outboundConnectMs",m_outboundConnectMs},{"originTlsMs",m_originTlsMs},
            {"fixtureOnly",true},{"liveReady",false},{"persistentBudgetGuardExercised",false},
            {"uiSubscriptionImportExercised",uiImport},{"uiPolicySelectionExercised",uiPolicy},
            {"tasksReleased",true},{"systemNetworkChanged",false},{"requestDeadlineMs",8000},{"elapsedMs",m_clock.elapsed()}};
#ifdef SWIRL_PRIVATE_UI_QUOTA
        if(m_importUi){
            result.insert("uiImportEvidence",m_importUi->evidence());result.insert("uiProbeButtonExercised",uiProbe);
            result.insert("uiDisplayedLatencyMatches",uiDisplay);
        }
        if(m_session.uiDnsPolicy){
            result.insert("uiDnsEvidence",QJsonObject{{"workflow","same-endpoint-dot-v1"},{"control",m_session.uiDnsControl},
                {"configured",m_dnsConfigured},{"configurationSha256",m_dnsConfigurationSha},
                {"trustBindingSha256",m_session.dnsTrust?m_session.dnsTrust->bindingDigest():QString{}},
                {"caSha256",QString::fromLatin1(QCryptographicHash::hash(m_session.fixtureDnsCa,QCryptographicHash::Sha256).toHex())},
                {"queryHost","swirl-node.fixture.invalid"},{"resolverAddress",QStringLiteral("127.0.0.1:%1").arg(m_session.fixtureSocksPort)},
                {"snapshots",m_importUi?m_importUi->dnsSnapshots():QJsonArray{}}});
        }
#endif
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
    QStringList manifestKeys{"schema","sourceSha","nonce","nodeOrdinal","proxyPort","fixture"};
    const bool nativeControl=input.contains("nativeWatchdogControl");
    if(nativeControl){
        if(input.value("nativeWatchdogControl")!=QJsonValue(QStringLiteral("native-watchdog-500ms")))return false;
        manifestKeys.append("nativeWatchdogControl");
    }
    const bool uiImport=input.contains("uiWorkflow");
    if(uiImport){
#ifndef SWIRL_PRIVATE_UI_QUOTA
        return false;
#else
        if(nativeControl||input.value("uiWorkflow")!=QJsonValue(QStringLiteral("subscription-policy-v1")))return false;
        manifestKeys.append("uiWorkflow");
        const auto origin=input.value("uiOrigin").toObject();
        if(!controlledKeys(origin,{"host","certificateSha256","keySha256"})
            ||origin.value("host")!=QJsonValue("203.0.113.1")
            ||origin.value("certificateSha256")!=QJsonValue("650152f76d410e5ae1a2b589002d1dd79a9c2af405021aed50da861fac52d748")
            ||origin.value("keySha256")!=QJsonValue("e62fd952d2f14fa39e6849032825d4e6a6b46837fce0037f6ed1abd46becc814"))return false;
        manifestKeys.append("uiOrigin");
        if(input.contains("uiImportControl")){
            if(!input.value("uiImportControl").isString()||!QStringList{"wrong-ca","over-limit","wrong-url","missing-capability"}
                .contains(input.value("uiImportControl").toString()))return false;
            manifestKeys.append("uiImportControl");
        }
#endif
    }
    const bool uiDns=input.contains("uiDns");
    if(uiDns){
#ifndef SWIRL_PRIVATE_UI_QUOTA
        return false;
#else
        if(!uiImport||input.contains("uiImportControl")||!input.value("uiDns").isObject())return false;
        const auto dns=input.value("uiDns").toObject();
        if(!controlledKeys(dns,{"workflow","control","caSha256"})
            ||dns.value("workflow")!=QJsonValue("same-endpoint-dot-v1")||!dns.value("control").isString()
            ||!QStringList{"","wrong-ca","wrong-address","wrong-question","stall","cancel"}.contains(dns.value("control").toString()))return false;
        manifestKeys.append("uiDns");
#endif
    }
    if(!controlledKeys(input,manifestKeys)
        ||input.value("schema")!=QJsonValue(2)||input.value("nodeOrdinal")!=QJsonValue(1)
        ||input.value("sourceSha").toString()!=RustCoreLibrary::expectedSourceSha()
        ||!QRegularExpression("^[0-9a-f]{64}$").match(input.value("nonce").toString()).hasMatch())return false;
    if(!input.value("fixture").isObject())return false;
    const auto settings=input.value("fixture").toObject();
    if(!controlledKeys(settings,{"httpPort","httpsPort","socksPort","caSha256"}))return false;
    ControlledNodeSession candidate;
    candidate.root=QDir::cleanPath(root);candidate.sourceSha=input.value("sourceSha").toString();
    candidate.nonce=input.value("nonce").toString();candidate.nodeOrdinal=1;
    candidate.nativeWatchdog500msControl=nativeControl;
    candidate.uiImportPolicy=uiImport;candidate.uiImportControl=input.value("uiImportControl").toString();
    candidate.uiDnsPolicy=uiDns;candidate.uiDnsControl=input.value("uiDns").toObject().value("control").toString();
    if(!controlledPort(input.value("proxyPort"),&candidate.proxyPort)
        ||!controlledPort(settings.value("httpPort"),&candidate.fixtureHttpPort)
        ||!controlledPort(settings.value("httpsPort"),&candidate.fixtureHttpsPort)
        ||!controlledPort(settings.value("socksPort"),&candidate.fixtureSocksPort)
        ||QSet<int>{candidate.proxyPort,candidate.fixtureHttpPort,candidate.fixtureHttpsPort,candidate.fixtureSocksPort}.size()!=4
        ||!QDir(root).entryList(QStringList{"nodes.dpapi*","fixture-store-*"},QDir::AllEntries|QDir::Hidden|QDir::System|QDir::NoDotAndDotDot).isEmpty()
        ||QFileInfo::exists(root+"/result.json")||QFileInfo::exists(root+"/state.json"))return false;
    const auto caHash=settings.value("caSha256").toString();
    if(uiImport&&caHash!=(candidate.uiImportControl==QStringLiteral("wrong-ca")
        ?QStringLiteral("e1075d330aab28049a89ba8e64f5f93f8ddbe2573c022c28508bb2ac2df26f1b")
        :QStringLiteral("a2fd461d4090889bd26e0eaea5bc974cffbdcced8d7aa0198221e5b9f5b05311")))return false;
    if(nativeControl&&caHash!=QStringLiteral("a2fd461d4090889bd26e0eaea5bc974cffbdcced8d7aa0198221e5b9f5b05311"))return false;
    if(caHash!=QStringLiteral("a2fd461d4090889bd26e0eaea5bc974cffbdcced8d7aa0198221e5b9f5b05311")
        &&caHash!=QStringLiteral("e1075d330aab28049a89ba8e64f5f93f8ddbe2573c022c28508bb2ac2df26f1b"))return false;
    const auto caPath=root+"/fixture-ca.pem";
    QFile ca(caPath);
    if(!controlledPath(caPath)||!ca.open(QIODevice::ReadOnly)||ca.size()>16384)return false;
    candidate.fixtureCa=ca.read(16385);
    if(QString::fromLatin1(QCryptographicHash::hash(candidate.fixtureCa,QCryptographicHash::Sha256).toHex())!=caHash)return false;
    if(uiDns){
        const auto expected=candidate.uiDnsControl==QStringLiteral("wrong-ca")
            ?QStringLiteral("e1075d330aab28049a89ba8e64f5f93f8ddbe2573c022c28508bb2ac2df26f1b")
            :QStringLiteral("a2fd461d4090889bd26e0eaea5bc974cffbdcced8d7aa0198221e5b9f5b05311");
        QFile dnsCa(root+"/dns-ca.pem");
        if(input.value("uiDns").toObject().value("caSha256")!=QJsonValue(expected)
            ||!controlledPath(dnsCa.fileName())||!dnsCa.open(QIODevice::ReadOnly)||dnsCa.size()>16384)return false;
        candidate.fixtureDnsCa=dnsCa.read(16385);
        if(QString::fromLatin1(QCryptographicHash::hash(candidate.fixtureDnsCa,QCryptographicHash::Sha256).toHex())!=expected)return false;
    }
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
    controlledNativeWatchdog500ms.store(false,std::memory_order_release);
    return std::jthread([](std::stop_token stop){
        while(!stop.stop_requested()){
            const auto requestStarted=controlledRequestStartedNs.load(std::memory_order_acquire);
            // Only this independent native producer uses the fixed 500ms
            // control. Qt request timers and the parent keep their normal 8s.
            const auto deadline=requestStarted&&controlledNativeWatchdog500ms.load(std::memory_order_acquire)
                ?std::min<std::int64_t>(controlledAbsoluteNs,requestStarted+500'000'000LL)
                :controlledDeadlineFor(requestStarted);
            const auto now=controlledNowNs();
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
