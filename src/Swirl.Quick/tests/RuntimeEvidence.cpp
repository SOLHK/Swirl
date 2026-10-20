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
 controller->setControlPort(19097);controller->setProxyPort(17988);
 // Set an isolated global route before the first engine start.
 // A saved production rule or DIRECT mode must never leak into this run.
 if(!controller->prepareRealAcceptance()||controller->routingMode()!=QStringLiteral("global")){
  qWarning()<<"Runtime acceptance refused non-global routing";QTimer::singleShot(0,qApp,&QCoreApplication::quit);return;
 }
 controller->connectNode(controller->selectedNodeId());
 auto timer=new QTimer(window);timer->setInterval(500);
 QObject::connect(timer,&QTimer::timeout,window,[=]{
  auto status=system->diagnosticSnapshot();status["testsBusy"]=controller->tests()->busy();status["testsCompleted"]=controller->tests()->completed();status["testsTotal"]=controller->tests()->total();status["testsSucceeded"]=controller->tests()->succeeded();status["testsFailed"]=controller->tests()->failed();status["hasExternalIp"]=!controller->telemetry()->externalIp().isEmpty();
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
