#pragma once
#include "app/VariableFontPreview.h"
#include "tests/FontUiChecks.h"
#include <QEventLoop>
#include <QMouseEvent>
#include <QScreen>
#include <QSGRendererInterface>
#include <QThread>
#include <QTimer>
#include <algorithm>
#include <array>
#include <atomic>
#include <chrono>
#include <cmath>
#include <memory>
#include <mutex>
#include <vector>

inline qint64 fontFrameNowNs() { return std::chrono::duration_cast<std::chrono::nanoseconds>(std::chrono::steady_clock::now().time_since_epoch()).count(); }
inline QQuickItem *fontFrameFind(QQuickItem *item,const QString &name) {
    if(item->objectName()==name)return item;
    for(auto *child:item->childItems())if(auto *found=fontFrameFind(child,name))return found;
    return nullptr;
}
inline QJsonObject fontFrameStats(std::vector<double> values) {
    if(values.empty())return {{"count",0}};
    std::sort(values.begin(),values.end());double sum=0;for(auto n:values)sum+=n;
    auto rank=[&](double q){return values[std::max(0,int(std::ceil(q*values.size()))-1)];};
    return {{"count",int(values.size())},{"mean",sum/values.size()},{"p50",rank(.5)},{"p95",rank(.95)},{"p99",rank(.99)},{"max",values.back()}};
}
struct FontFrameSample {
    int index=0,readySequence=0;
    qint64 begin=0,syncBegin=0,syncEnd=0,renderBegin=0,renderEnd=0,queued=0,end=0;
};
struct FontRasterSample { int sequence=0,line=0;bool paint=false,axesMatch=false;qint64 begin=0,end=0; };
struct FontInputSample {int sequence=0;qint64 begin=0,end=0,driverQueued=0;double wght=0,wdth=0,hght=0;};
struct FontFrameTrace {
    std::mutex mutex;
    std::atomic_bool enabled{true};
    std::atomic_int sequence{0},readySequence{0};
    qint64 epoch=fontFrameNowNs();int begun=0;
    quintptr renderThread=0;
    FontFrameSample current;
    std::array<double,3> expected{};
    QHash<int,int> readyMasks;
    std::vector<FontFrameSample> frames;
    std::vector<FontRasterSample> rasters;
    std::vector<FontInputSample> inputs;
    std::vector<qint64> swaps;
    FontFrameTrace(){frames.reserve(1024);rasters.reserve(4096);inputs.reserve(512);swaps.reserve(1024);}
};

// Timing is collected in-process only. No pointer is injected into another app.
// No qWait/sleep, screenshot, JSON serialization or file IO occurs in the measured loop.
inline QJsonObject runFontFramePhase(QQuickWindow *window,FontManager *manager,QQuickItem *slider,
                                    const QList<VariableFontPreview *> &lines,const QString &mode,int round)
{
    constexpr int warmup=30,samples=240,total=warmup+samples;
    auto trace=std::make_shared<FontFrameTrace>();QObject receiver;QEventLoop loop;
    QList<QMetaObject::Connection> connections;
    auto direct=[&](auto signal,auto callback){connections.append(QObject::connect(window,signal,&receiver,callback,Qt::DirectConnection));};
    direct(&QQuickWindow::beforeFrameBegin,[trace]{
        if(!trace->enabled.load())return;std::lock_guard guard(trace->mutex);
        trace->current={};trace->current.index=++trace->begun;trace->current.begin=fontFrameNowNs();
        trace->renderThread=reinterpret_cast<quintptr>(QThread::currentThreadId());
    });
    direct(&QQuickWindow::beforeSynchronizing,[trace]{if(!trace->enabled.load())return;std::lock_guard guard(trace->mutex);trace->current.syncBegin=fontFrameNowNs();trace->current.readySequence=trace->readySequence.load();});
    direct(&QQuickWindow::afterSynchronizing,[trace]{if(!trace->enabled.load())return;std::lock_guard guard(trace->mutex);trace->current.syncEnd=fontFrameNowNs();});
    direct(&QQuickWindow::beforeRendering,[trace]{if(!trace->enabled.load())return;std::lock_guard guard(trace->mutex);trace->current.renderBegin=fontFrameNowNs();});
    direct(&QQuickWindow::afterRendering,[trace]{if(!trace->enabled.load())return;std::lock_guard guard(trace->mutex);trace->current.renderEnd=fontFrameNowNs();});
    direct(&QQuickWindow::frameSwapped,[trace]{if(!trace->enabled.load())return;std::lock_guard guard(trace->mutex);const auto now=fontFrameNowNs();trace->current.queued=now;trace->swaps.push_back(now);});
    direct(&QQuickWindow::afterFrameEnd,[trace]{if(!trace->enabled.load())return;std::lock_guard guard(trace->mutex);trace->current.end=fontFrameNowNs();if(trace->current.begin&&trace->frames.size()<1024)trace->frames.push_back(trace->current);});
    for(int index=0;index<lines.size();++index){
        auto *line=lines[index];line->setMeasureRaster(true);
        connections.append(QObject::connect(line,&VariableFontPreview::rasterMeasured,&receiver,[trace,line,index](qint64 begin,qint64 end){
            if(!trace->enabled.load())return;const auto seq=trace->sequence.load();const auto font=line->font();
            std::lock_guard guard(trace->mutex);
            const bool matches=std::abs(font.variableAxisValue(QFont::Tag("wght"))-trace->expected[0])<.001 && std::abs(font.variableAxisValue(QFont::Tag("wdth"))-trace->expected[1])<.001 && std::abs(font.variableAxisValue(QFont::Tag("HGHT"))-trace->expected[2])<.001;
            if(trace->rasters.size()<8192)trace->rasters.push_back({seq,index,false,matches,begin,end});
            if(matches&&seq>0){trace->readyMasks[seq]|=1<<index;if(trace->readyMasks[seq]==15)trace->readySequence.store(seq);}
        },Qt::DirectConnection));
        connections.append(QObject::connect(line,&VariableFontPreview::textureMeasured,&receiver,[trace,index](qint64 begin,qint64 end){
            if(!trace->enabled.load())return;std::lock_guard guard(trace->mutex);
            if(trace->rasters.size()<8192)trace->rasters.push_back({trace->readySequence.load(),index,true,true,begin,end});
        },Qt::DirectConnection));
    }
    int issued=0,callbacks=0;bool completed=false;QPointF lastPoint;
    auto pointer=[&](QEvent::Type type,const QPointF &point){
        const auto button=type==QEvent::MouseMove?Qt::NoButton:Qt::LeftButton;
        QMouseEvent event(type,point,QPointF(window->mapToGlobal(point.toPoint())),button,type==QEvent::MouseButtonRelease?Qt::NoButton:Qt::LeftButton,Qt::NoModifier);
        QCoreApplication::sendEvent(window,&event);
    };
    auto input=[&](qint64 driverQueued){
        if(mode=="static"){window->update();return;}
        const int sequence=++issued;trace->sequence.store(sequence);
        const auto begin=fontFrameNowNs();
        if(mode=="slider"){
            const double t=(sequence%120)/119.0;
            const double fraction=.1+.8*(sequence/120%2?1-t:t);
            const double left=slider->property("leftPadding").toDouble(),right=slider->property("rightPadding").toDouble();
            lastPoint=slider->mapToScene(QPointF(left+fraction*(slider->width()-left-right),slider->height()/2));
            pointer(sequence==1?QEvent::MouseButtonPress:QEvent::MouseMove,lastPoint);
        }else{
            manager->setPreviewAxis("HGHT",1.125+((sequence*37)%1024)*998.5/1024.0);
            manager->setPreviewAxis("wght",100.125+((sequence*617)%1024)*799.5/1024.0);
            manager->setPreviewAxis("wdth",80.0125+((sequence*389)%1024)*39.95/1024.0);
        }
        const auto axes=manager->previewValues();const auto end=fontFrameNowNs();
        {std::lock_guard guard(trace->mutex);trace->expected={axes.value("wght").toDouble(),axes.value("wdth").toDouble(),axes.value("HGHT").toDouble()};trace->inputs.push_back({sequence,begin,end,driverQueued,trace->expected[0],trace->expected[1],trace->expected[2]});}
        window->update();
    };
    connections.append(QObject::connect(window,&QQuickWindow::frameSwapped,&receiver,[&]{
        qint64 queued=0;{std::lock_guard guard(trace->mutex);if(callbacks>=int(trace->swaps.size()))return;queued=trace->swaps[callbacks];}
        if(++callbacks>=total){completed=true;loop.quit();return;}input(queued);
    },Qt::QueuedConnection));
    QTimer deadline;deadline.setSingleShot(true);QObject::connect(&deadline,&QTimer::timeout,&loop,&QEventLoop::quit);deadline.start(6000);
    const auto started=fontFrameNowNs();input(0);loop.exec();const auto finished=fontFrameNowNs();
    trace->enabled.store(false);for(const auto &connection:connections)QObject::disconnect(connection);
    if(mode=="slider")pointer(QEvent::MouseButtonRelease,lastPoint);
    for(auto *line:lines)line->setMeasureRaster(false);
    std::lock_guard guard(trace->mutex);
    QJsonArray rawFrames,rawRasters,rawInputs;std::vector<double> intervals,sync,record,submit,whole,raster,paint,handling,driver,latency,rasterLatency;
    QHash<int,qint64> firstQueued,readyAt;QHash<int,double> rasterSums;
    const auto ms=[&](qint64 time){return time?double(time-trace->epoch)/1e6:-1.;};
    qint64 previous=0;
    for(const auto &frame:trace->frames){
        rawFrames.append(QJsonObject{{"index",frame.index},{"readySequence",frame.readySequence},{"beginMs",ms(frame.begin)},{"syncBeginMs",ms(frame.syncBegin)},{"syncEndMs",ms(frame.syncEnd)},{"recordBeginMs",ms(frame.renderBegin)},{"recordEndMs",ms(frame.renderEnd)},{"queuedPresentMs",ms(frame.queued)},{"submittedMs",ms(frame.end)}});
        if(frame.queued&&frame.readySequence&&!firstQueued.contains(frame.readySequence))firstQueued[frame.readySequence]=frame.queued;
        if(frame.index>warmup&&frame.queued){
            if(previous)intervals.push_back(double(frame.queued-previous)/1e6);
            if(frame.syncEnd>=frame.syncBegin&&frame.syncBegin)sync.push_back(double(frame.syncEnd-frame.syncBegin)/1e6);
            if(frame.renderEnd>=frame.renderBegin&&frame.renderBegin)record.push_back(double(frame.renderEnd-frame.renderBegin)/1e6);
            if(frame.end>=frame.renderEnd&&frame.renderEnd)submit.push_back(double(frame.end-frame.renderEnd)/1e6);
            whole.push_back(double(frame.end-frame.begin)/1e6);
        }
        if(frame.queued)previous=frame.queued;
    }
    for(const auto &sample:trace->rasters){
        rawRasters.append(QJsonObject{{"sequence",sample.sequence},{"line",sample.line},{"textureUpdate",sample.paint},{"axesMatch",sample.axesMatch},{"beginMs",ms(sample.begin)},{"endMs",ms(sample.end)}});
        if(!sample.paint&&sample.axesMatch){readyAt[sample.sequence]=qMax(readyAt.value(sample.sequence),sample.end);rasterSums[sample.sequence]+=double(sample.end-sample.begin)/1e6;}
        if(sample.sequence>warmup)(sample.paint?paint:raster).push_back(double(sample.end-sample.begin)/1e6);
    }
    int represented=0,changes=0;double previousHght=-1;
    for(const auto &sample:trace->inputs){
        rawInputs.append(QJsonObject{{"sequence",sample.sequence},{"beginMs",ms(sample.begin)},{"handledMs",ms(sample.end)},{"driverQueuedPresentMs",ms(sample.driverQueued)},{"wght",sample.wght},{"wdth",sample.wdth},{"HGHT",sample.hght}});
        if(sample.hght!=previousHght)++changes;previousHght=sample.hght;
        if(sample.sequence<=warmup)continue;
        handling.push_back(double(sample.end-sample.begin)/1e6);
        if(sample.driverQueued)driver.push_back(double(sample.begin-sample.driverQueued)/1e6);
        if(firstQueued.contains(sample.sequence)){++represented;latency.push_back(double(firstQueued[sample.sequence]-sample.begin)/1e6);}
        if(trace->readyMasks.value(sample.sequence)==15)rasterLatency.push_back(double(readyAt[sample.sequence]-sample.begin)/1e6);
    }
    std::vector<double> totalRaster;for(auto it=rasterSums.cbegin();it!=rasterSums.cend();++it)if(it.key()>warmup&&trace->readyMasks.value(it.key())==15)totalRaster.push_back(it.value());
    const bool inputWorked=mode!="slider"||changes>total/2;
    return {{"mode",mode},{"round",round},{"completed",completed},{"inputWorked",inputWorked},{"warmupFrames",warmup},{"requestedSampleFrames",samples},{"frameCallbacks",callbacks},{"inputCount",issued},{"representedMeasuredInputs",represented},{"elapsedMs",double(finished-started)/1e6},{"privateBytes",double(fontUiPrivateBytes())},{"renderThread",QString::number(trace->renderThread)},{"guiThread",QString::number(reinterpret_cast<quintptr>(QThread::currentThreadId()))},
        {"queuedPresentIntervalMs",fontFrameStats(intervals)},{"sceneSyncWallMs",fontFrameStats(sync)},{"renderRecordWallMs",fontFrameStats(record)},{"postRecordToSubmitWallMs",fontFrameStats(submit)},{"wholeFrameWallMs",fontFrameStats(whole)},{"rasterLineWallMs",fontFrameStats(raster)},{"rasterFourLinesWallMs",fontFrameStats(totalRaster)},{"textureUpdateCpuWallMs",fontFrameStats(paint)},{"inputHandlerWallMs",fontFrameStats(handling)},{"driverQueueDelayMs",fontFrameStats(driver)},{"inputToAllRastersMs",fontFrameStats(rasterLatency)},{"inputToQueuedPresentMs",fontFrameStats(latency)},{"frames",rawFrames},{"rasters",rawRasters},{"inputs",rawInputs}};
}

inline int runFontFrameChecks(QQuickWindow *window,FontManager *manager,const QString &output) {
    if(!window||output.isEmpty()||manager->previewAxes().isEmpty())return 3;
    QDir().mkpath(output);window->resize(1100,900);window->show();
    QQmlExpression navigate(qmlContext(window),window,"AppState.navigate('settings')");navigate.evaluate();QTest::qWait(500);
    auto *loader=window->findChild<QObject *>("pageLoader");QPointer<QObject> page;
    QElapsedTimer ready;ready.start();while(ready.elapsed()<8000){
        page=loader?qvariant_cast<QObject *>(loader->property("item")):nullptr;
        if(page&&page->metaObject()->indexOfProperty("section")>=0&&!loader->property("moving").toBool())break;QTest::qWait(20);
    }
    if(!page)return 3;page->setProperty("section",QStringLiteral("字体"));QTest::qWait(300);QMetaObject::invokeMethod(page,"scrollToBottom");QTest::qWait(150);
    auto *slider=fontFrameFind(window->contentItem(),"fontAxisSlider_HGHT");QList<VariableFontPreview *> lines;
    for(int i=0;i<4;++i)if(auto *line=qobject_cast<VariableFontPreview *>(fontFrameFind(window->contentItem(),"fontPreviewLine_"+QString::number(i))))lines.append(line);
    if(!slider||lines.size()!=4)return 3;
    const auto center=slider->mapToScene(QPointF(slider->width()/2,slider->height()/2));
    if(!QRectF(0,0,window->width(),window->height()).contains(center))return 3;
    QJsonArray phases;bool ok=true;
    for(int round=1;round<=3&&ok;++round)for(const auto &mode:QStringList{"static","slider","three-axis"}){
        manager->resetPreviewAxes();QTest::qWait(200); // Setup only; outside all measured traces.
        const auto result=runFontFramePhase(window,manager,slider,lines,mode,round);phases.append(result);
        if(!result.value("completed").toBool()||!result.value("inputWorked").toBool()){ok=false;break;}
    }
    const bool samePage=page&&qvariant_cast<QObject *>(loader->property("item"))==page;
    manager->resetPreviewAxes();QTest::qWait(150);window->grabWindow().save(output+"/after-benchmark.png");
    QJsonObject report{{"completed",ok},{"samePage",samePage},{"dpr",window->devicePixelRatio()},{"qtRefreshRate",window->screen()->refreshRate()},{"screen",window->screen()->name()},{"graphicsApi",int(window->rendererInterface()->graphicsApi())},{"renderLoopOverride",qEnvironmentVariable("QSG_RENDER_LOOP")},{"fontEngine",qEnvironmentVariable("QT_QPA_PLATFORM")},{"phases",phases},
        {"method","std::chrono::steady_clock; direct render-thread signal timestamps; frame-feedback GUI driver, no qWait in measured phases; synthetic pointer events stay in this QQuickWindow"},
        {"limits","frameSwapped means queued for presentation; afterFrameEnd means submitted. No GPU completion, scanout, photons or hardware pointer latency claimed. Frame wall spans may contain driver/vsync waits; raster and render-record spans are reported separately. No animations or quality settings changed."}};
    QFile file(output+"/font-frame-report.json");if(!file.open(QIODevice::WriteOnly))return 3;file.write(QJsonDocument(report).toJson());
    return ok&&samePage?0:2;
}

inline void applyFontReadingReview(QQuickWindow *window,double points,const QString &label,const QString &output) {
    auto *loader=window->findChild<QObject *>("pageLoader");auto *page=loader?qvariant_cast<QObject *>(loader->property("item")):nullptr;
    if(!page)return;page->setProperty("section",QStringLiteral("字体"));
    QTimer::singleShot(100,window,[window,points,label,output]{
        QJsonArray measured;
        for(int i=0;i<4;++i)if(auto *line=qobject_cast<VariableFontPreview *>(fontFrameFind(window->contentItem(),"fontPreviewLine_"+QString::number(i)))){auto font=line->font();font.setPointSizeF(points);line->setFont(font);
            QJsonObject axes;for(const auto &tag:font.variableAxisTags())axes.insert(QString::fromLatin1(tag.toString()),font.variableAxisValue(tag));
            measured.append(QJsonObject{{"line",i},{"pointSize",line->font().pointSizeF()},{"pixelSize",line->font().pixelSize()},{"family",line->font().family()},{"axes",axes}});
        }
        if(!output.isEmpty()){
            QDir().mkpath(QFileInfo(output).absolutePath());QFile file(output);
            if(file.open(QIODevice::WriteOnly))file.write(QJsonDocument(QJsonObject{{"label",label.left(16)},{"requestedPoints",points},{"dpr",window->devicePixelRatio()},{"lines",measured}}).toJson());
        }
        window->setTitle(QStringLiteral("Swirl 字体阅读对比 %1 · %2 pt · 隔离窗口").arg(label.left(16)).arg(points));
        QTimer::singleShot(100,window,[window]{QMetaObject::invokeMethod(window,"previewScrollBottom");});
    });
}
