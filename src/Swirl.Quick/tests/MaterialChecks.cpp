#include "MaterialChecks.h"
#include <QQuickRenderControl>
#include <QQuickRenderTarget>
#include <QQuickGraphicsDevice>
#include <QQuickWindow>
#include <QQuickItem>
#include <QQmlComponent>
#include <QQmlEngine>
#include <QQmlContext>
#include <QJsonDocument>
#include <QJsonArray>
#include <QJsonObject>
#include <QFile>
#include <QDir>
#include <QElapsedTimer>
#include <rhi/qrhi.h>
#include <private/qrhid3d11_p.h>
#include <algorithm>
#include <memory>
#include <cmath>
int runMaterialChecks(QQuickWindow *appWindow,const QString &directory) {
 QDir().mkpath(directory);QRhiD3D11InitParams params;
 std::unique_ptr<QRhi> rhi(QRhi::create(QRhi::D3D11,&params,QRhi::EnableTimestamps));
 if(!rhi)return 3;
 QQuickRenderControl control;QQuickWindow window(&control);window.setGraphicsDevice(QQuickGraphicsDevice::fromRhi(rhi.get()));
 if(!control.initialize())return 3;
 QJsonArray records;int failures=0;
 for(const auto resolution:{QSize(1920,1080),QSize(2560,1440),QSize(3840,2160)}) {
  window.resize(resolution);
  std::unique_ptr<QRhiTexture> texture(rhi->newTexture(QRhiTexture::RGBA8,resolution,1,QRhiTexture::RenderTarget|QRhiTexture::UsedAsTransferSource));
  if(!texture->create())return 3;
  std::unique_ptr<QRhiTextureRenderTarget> target(rhi->newTextureRenderTarget({QRhiColorAttachment(texture.get())}));
  std::unique_ptr<QRhiRenderPassDescriptor> pass(target->newCompatibleRenderPassDescriptor());target->setRenderPassDescriptor(pass.get());if(!target->create())return 3;
  window.setRenderTarget(QQuickRenderTarget::fromRhiRenderTarget(target.get()));
  QQmlComponent component(qmlEngine(appWindow),QUrl("qrc:/tests/MaterialBench.qml"));
  std::unique_ptr<QObject> root(component.create(qmlContext(appWindow)));
  if(!root){qCritical()<<component.errors();return 3;}
  auto item=qobject_cast<QQuickItem *>(root.get());item->setParentItem(window.contentItem());item->setSize(resolution);
  auto render=[&](bool capture){
   QRhiReadbackResult read;bool done=false;read.completed=[&]{done=true;};
   control.polishItems();control.beginFrame();control.sync();control.render();
   const auto gpuMs=control.commandBuffer()->lastCompletedGpuTime()*1000;
   if(capture){auto updates=rhi->nextResourceUpdateBatch();updates->readBackTexture(QRhiReadbackDescription(texture.get()),&read);control.commandBuffer()->resourceUpdate(updates);}
   control.endFrame();rhi->finish();
   QImage image;
   if(capture && done && read.data.size()>=resolution.width()*resolution.height()*4)image=QImage(reinterpret_cast<const uchar *>(read.data.constData()),resolution.width(),resolution.height(),QImage::Format_RGBA8888).copy();
   return std::pair<double,QImage>(gpuMs,image);
  };
  const QStringList names={"Gaussian","Kawase","Swirl-Dual-Kawase-RHI","Qt-MultiEffect"};
  for(int algorithm=0;algorithm<4;++algorithm) {
   root.reset();
   root.reset(component.createWithInitialProperties({{"algorithm",algorithm},{"impulse",true},{"width",resolution.width()},{"height",resolution.height()}},qmlContext(appWindow)));
   if(!root)return 3;
   item=qobject_cast<QQuickItem *>(root.get());item->setParentItem(window.contentItem());item->setSize(resolution);
   double strength=3.5,sigma=0;
   // Calibrate each implementation to a measured horizontal PSF sigma of
   // roughly 6 pixels. Equal parameter values do not mean equal blur radii.
   for(int trial=0;trial<3;++trial) {
    root->setProperty("strength",strength);for(int i=0;i<3;++i)render(false);auto image=render(true).second;
    double sum=0,mean=0,variance=0;const int cy=resolution.height()/2;
    if(image.isNull()){++failures;break;}
    for(int x=0;x<image.width();++x){const double weight=qGray(image.pixel(x,cy));sum+=weight;mean+=weight*x;}
    if(sum<=0){image.save(directory+QString("/failed-impulse-%1-%2.png").arg(resolution.width()).arg(algorithm));++failures;break;}mean/=sum;
    for(int x=0;x<image.width();++x){const double weight=qGray(image.pixel(x,cy));variance+=weight*(x-mean)*(x-mean);}
    sigma=std::sqrt(qMax(0.0,variance/sum-63.0/12.0));if(sigma>0.1)strength=qBound(0.1,strength*6.0/sigma,15.9);
   }
   root->setProperty("strength",strength);root->setProperty("impulse",false);for(int i=0;i<5;++i)render(false);
   QList<double> gpu,cpu;
   for(int frame=0;frame<40;++frame){QElapsedTimer timer;timer.start();auto result=render(false);cpu.append(timer.nsecsElapsed()/1000000.0);if(result.first>0)gpu.append(result.first);}
   std::sort(gpu.begin(),gpu.end());std::sort(cpu.begin(),cpu.end());
   const auto snapshot=render(true).second;const auto file=QString("%1-%2.png").arg(resolution.width()).arg(names[algorithm]);if(!snapshot.save(directory+"/"+file))++failures;
   records.append(QJsonObject{{"algorithm",names[algorithm]},{"width",resolution.width()},{"height",resolution.height()},{"targetSigmaPixels",6.0},{"lastCalibratedSigmaPixels",sigma},{"strength",strength},{"gpuSamples",gpu.size()},{"gpuMedianMs",gpu.isEmpty()?QJsonValue():QJsonValue(gpu[gpu.size()/2])},{"gpuP95Ms",gpu.isEmpty()?QJsonValue():QJsonValue(gpu[qMin(gpu.size()-1,qsizetype(gpu.size()*0.95))])},{"synchronousRenderMedianMs",cpu[cpu.size()/2]},{"file",file}});
  }
  root.reset();window.setRenderTarget({});
 }
 control.invalidate();
 QFile report(directory+"/blur-benchmark.json");if(!report.open(QIODevice::WriteOnly))return 3;
 report.write(QJsonDocument(QJsonObject{{"records",records},{"failures",failures},{"adapter",QString::fromUtf8(rhi->driverInfo().deviceName)},{"method","D3D11 QRhi GPU timestamps; controlled offscreen recomputation benchmark, not display FPS. Input is original synthetic complex wallpaper; PSF sigma calibrated independently. Production blur caches are event driven."}}).toJson());
 return failures?2:0;
}
