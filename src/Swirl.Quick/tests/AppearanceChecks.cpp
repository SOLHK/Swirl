#include "AppearanceChecks.h"
#include "app/SwirlPressClock.h"
#include <QQuickWindow>
#include <QQuickItem>
#include <QQuickItemGrabResult>
#include <QQmlContext>
#include <QQmlExpression>
#include <QQmlProperty>
#include <QTest>
#include <QSignalSpy>
#include <QSettings>
#include <QProcess>
#include <QCoreApplication>
#include <QGuiApplication>
#include <QImage>
#include <QColor>
#include <QQmlComponent>
#include <QQmlEngine>
#include <QFontMetricsF>
#include <QFontDatabase>
#include <QCursor>
#include <QMouseEvent>
#include <QKeyEvent>
#include <QElapsedTimer>
#include <QDateTime>
#include <QFileInfo>
#include <QFile>
#include <QJsonArray>
#include <QJsonDocument>
#include <QJsonObject>
#include <QEventLoop>
#include <QTimer>
#include <QMutex>
#include <QMutexLocker>
#include <QtMath>
#include <chrono>
#include <functional>
#include <memory>
#include <QSGRendererInterface>
#include <QSGTransformNode>
#include <private/qquickitem_p.h>
#ifdef Q_OS_WIN
#include <private/qrhid3d11_p.h>
#endif

static QJsonArray appearanceMatrixValues(const QMatrix4x4 &matrix) {
    QJsonArray values;
    for(int row=0;row<4;++row)for(int column=0;column<4;++column)values.append(matrix(row,column));
    return values;
}

static QJsonObject appearanceSwapChainProbe(QQuickWindow *window) {
    QJsonObject result{{"scope","read-only normal-frame barrier before timed input"}};
#ifdef Q_OS_WIN
    result.insert("platformSupported",true);
    auto *renderer=window->rendererInterface();
    result.insert("rendererInterfacePresent",renderer!=nullptr);
    if(!renderer)return result;
    result.insert("graphicsApi",int(renderer->graphicsApi()));
    const bool d3d11=renderer->graphicsApi()==QSGRendererInterface::Direct3D11;
    result.insert("d3d11",d3d11);
    if(!d3d11)return result;
    // Qt 6.12 QRhiSwapChain has no nativeHandles() API. Reuse the same
    // version-locked GuiPrivate backend type as the existing Hero checks.
    // The caller runs on the render thread; retain only values, not pointers.
    auto *rhiChain=static_cast<QRhiSwapChain *>(renderer->getResource(window,QSGRendererInterface::RhiSwapchainResource));
    result.insert("rhiSwapchainPresent",rhiChain!=nullptr);
    if(!rhiChain)return result;
    auto *chain=static_cast<QD3D11SwapChain *>(rhiChain);
    result.insert("qtSwapInterval",qint64(chain->swapInterval));
    result.insert("qtSwapchainFlags",qint64(chain->swapChainFlags));
    result.insert("qtFrameLatencyWaitableObjectPresent",chain->frameLatencyWaitableObject!=nullptr);
    result.insert("dxgiSwapchainPresent",chain->swapChain!=nullptr);
    if(!chain->swapChain)return result;
    const auto hresult=[](HRESULT value){
        return QJsonObject{{"hresult",QStringLiteral("0x")+QString::number(quint32(value),16).rightJustified(8,QLatin1Char('0'))},
            {"succeeded",SUCCEEDED(value)}};
    };
    DXGI_SWAP_CHAIN_DESC desc{};
    const HRESULT descStatus=chain->swapChain->GetDesc(&desc);
    auto description=hresult(descStatus);
    if(SUCCEEDED(descStatus)){
        description.insert("flags",qint64(desc.Flags));
        description.insert("bufferCount",qint64(desc.BufferCount));
        description.insert("swapEffect",int(desc.SwapEffect));
        description.insert("frameLatencyWaitableFlag",bool(desc.Flags&DXGI_SWAP_CHAIN_FLAG_FRAME_LATENCY_WAITABLE_OBJECT));
    }
    result.insert("getDesc",description);
    IDXGISwapChain2 *queriedChain=nullptr;
    const HRESULT interfaceStatus=chain->swapChain->QueryInterface(__uuidof(IDXGISwapChain2),reinterpret_cast<void **>(&queriedChain));
    auto release=[](IDXGISwapChain2 *value){if(value)value->Release();};
    const std::unique_ptr<IDXGISwapChain2,decltype(release)> nativeChain(queriedChain,release);
    auto query=hresult(interfaceStatus);
    query.insert("interfacePresent",nativeChain!=nullptr);
    result.insert("queryInterfaceSwapChain2",query);
    if(FAILED(interfaceStatus)||!nativeChain)return result;
    UINT maximumFrameLatency=0;
    const HRESULT latencyStatus=nativeChain->GetMaximumFrameLatency(&maximumFrameLatency);
    auto latency=hresult(latencyStatus);
    if(SUCCEEDED(latencyStatus))latency.insert("frames",qint64(maximumFrameLatency));
    result.insert("getMaximumFrameLatency",latency);
    DXGI_SWAP_CHAIN_DESC1 desc1{};
    const HRESULT desc1Status=nativeChain->GetDesc1(&desc1);
    auto description1=hresult(desc1Status);
    if(SUCCEEDED(desc1Status)){
        description1.insert("flags",qint64(desc1.Flags));
        description1.insert("bufferCount",qint64(desc1.BufferCount));
        description1.insert("swapEffect",int(desc1.SwapEffect));
        description1.insert("frameLatencyWaitableFlag",bool(desc1.Flags&DXGI_SWAP_CHAIN_FLAG_FRAME_LATENCY_WAITABLE_OBJECT));
    }
    result.insert("getDesc1",description1);
#else
    Q_UNUSED(window);
    result.insert("platformSupported",false);
#endif
    return result;
}

int runAppearanceChecks(QQuickWindow *window,bool restoreOnly) {
    if(!window)return 2;
    QElapsedTimer totalClock,stageClock;totalClock.start();stageClock.start();
    const auto stage=[&](const char *name){qInfo()<<"APPEARANCE_STAGE"<<name<<"stageMs"<<stageClock.restart()<<"totalMs"<<totalClock.elapsed();};
    int failures=0;
    auto check=[&](bool ok,const char *name){qInfo()<<(ok?"PASS":"FAIL")<<name;if(!ok)++failures;};
    auto eval=[&](const QString &code){QQmlExpression e(qmlContext(window),window,code);auto value=e.evaluate();check(!e.hasError(),"appearance expression is valid");return value;};
    if(restoreOnly){qInfo()<<"APPEARANCE_RESTORE_PROCESS"<<QCoreApplication::applicationPid();check(eval("Theme.mode==='Dark' && Theme.dark && Theme.followSystemMotion").toBool(),"new process restores saved dark theme and explicit system-motion preference");return failures?2:0;}
    if(qEnvironmentVariableIsSet("SWIRL_EXPECTED_DPR"))
        check(qAbs(window->devicePixelRatio()-qEnvironmentVariable("SWIRL_EXPECTED_DPR").toDouble())<0.02,"native window uses the requested controlled DPR");
    {
        QQmlComponent component(qmlEngine(window));
        component.setData(R"QML(
import QtQuick
import QtQuick.Layouts
import SwirlQuick
Item {
    width:600;height:480;x:230;y:100;z:1000
    SwirlButton {objectName:"reviewButton";x:10;y:10;text:"规则分流 HTTPS 176"}
    SwirlIconButton {objectName:"reviewIcon";x:220;y:10;iconName:"plus";tooltip:"添加"}
    SwirlComboBox {objectName:"reviewCombo";x:270;y:10;model:["默认策略 SG 176 ms","自动测速"]}
    SwirlSegmentedControl {objectName:"reviewSegments";x:10;y:65;width:280;options:["全部 12","仅代理 8"]}
    SwirlText {objectName:"reviewFigures";x:310;y:75;tabularFigures:true;text:"176 ms · HTTPS 完整请求"}
    SubscriptionAction {objectName:"reviewAction";x:10;y:115;text:"更新全部";iconName:"refresh";solid:true}
    SwirlNavigationItem {objectName:"reviewNavigation";x:210;y:115;width:180;pageId:"external";title:"面板";iconName:"gauge"}
    PolicyGroupTypes {objectName:"reviewGroupTypes";x:0;y:170;width:590}
})QML",QUrl("qrc:/qt/qml/SwirlQuick/ControlsReviewFixture.qml"));
        auto *fixture=qobject_cast<QQuickItem *>(component.create(qmlContext(window)));
        check(fixture!=nullptr,"shared control review fixture loads");
        if(!fixture)qWarning()<<component.errors();
        if(fixture){
            fixture->setParentItem(window->contentItem());
            struct RestoreCursor { QPoint position=QCursor::pos(); ~RestoreCursor(){QCursor::setPos(position);} } restoreCursor;
            window->requestActivate();QTest::qWait(100);
            const auto surface=[](QQuickItem *control){return control?control->property("background").value<QQuickItem *>():nullptr;};
            const auto movePointer=[&](QPoint local,int settle=160){
                QCursor::setPos(window->mapToGlobal(local));
                QCoreApplication::processEvents();
                QTest::mouseMove(window,window->mapFromGlobal(QCursor::pos()));
                QTest::qWait(settle);
            };
            std::function<QQuickItem *(QQuickItem *,const QString &)> visualItem;
            visualItem=[&](QQuickItem *parent,const QString &name)->QQuickItem *{
                if(parent->objectName()==name)return parent;
                for(auto *child:parent->childItems())if(auto *match=visualItem(child,name))return match;
                return nullptr;
            };
            const auto windowInventory=[&](const char *phase,const QString &theme,const QString &control=QString()){
                QJsonArray windows;
                for(auto *candidate:QGuiApplication::allWindows()){
                    auto *quick=qobject_cast<QQuickWindow *>(candidate);
                    const auto geometry=candidate->geometry();
                    // handle() only observes platform-window creation. Do not
                    // call winId(), which would create the hidden panel's HWND.
                    windows.append(QJsonObject{{"address",QStringLiteral("0x")+QString::number(reinterpret_cast<quintptr>(candidate),16)},
                        {"objectName",candidate->objectName()},{"className",QString::fromLatin1(candidate->metaObject()->className())},
                        {"title",candidate->title()},{"main",candidate==window},{"visible",candidate->isVisible()},
                        {"exposed",candidate->isExposed()},{"active",candidate->isActive()},{"visibility",int(candidate->visibility())},
                        {"flags",QStringLiteral("0x")+QString::number(candidate->flags().toInt(),16)},
                        {"hasPlatformWindow",candidate->handle()!=nullptr},{"quickWindow",quick!=nullptr},
                        {"sceneGraphInitialized",quick&&quick->isSceneGraphInitialized()},{"dpr",candidate->devicePixelRatio()},
                        {"geometry",QJsonObject{{"x",geometry.x()},{"y",geometry.y()},{"width",geometry.width()},{"height",geometry.height()}}}});
                }
                qInfo().noquote()<<"APPEARANCE_WINDOW_INVENTORY"<<phase<<theme<<control<<QJsonDocument(windows).toJson(QJsonDocument::Compact);
            };
            for(const auto &theme:QStringList{"Light","Dark"}){
                windowInventory("before-theme",theme);
                eval("Theme.mode='"+theme+"';Theme.reduceMotion=false;Theme.followSystemMotion=false;Theme.increaseContrast=false");QTest::qWait(160);
                windowInventory("after-theme",theme);
                for(const auto &name:QStringList{"reviewButton","reviewIcon","reviewCombo","reviewAction","reviewNavigation"}){
                    auto *control=fixture->findChild<QQuickItem *>(name);auto *paint=surface(control);
                    check(paint&&qAbs(paint->property("radius").toReal()-(name=="reviewNavigation"?eval("Theme.sidebarRowRadius").toReal():paint->height()/2))<0.01,"shared surfaces retain the requested capsule or navigation curve");
                    if(!control||!paint)continue;
                    const auto size=control->size();const auto position=control->position();
                    auto *content=control->property("contentItem").value<QQuickItem *>();
                    auto *focusFill=paint->findChild<QQuickItem *>("controlFocusFill");
                    const auto sameRenderedColor=[](const QColor &left,const QColor &right){return left.rgba64().premultiplied()==right.rgba64().premultiplied();};
                    const auto motionRetired=[&]{return !paint->property("moving").toBool()&&paint->property("hoverProgress").toReal()==0&&paint->property("contactProgress").toReal()==0&&focusFill&&focusFill->opacity()==0&&paint->scale()==1&&content&&content->scale()==1;};
                    const auto diagnose=[&](const char *phase,const QColor &normal){
                        qInfo()<<"CONTROL_STATE"<<theme<<name<<phase<<"hovered"<<control->property("hovered")<<"down"<<control->property("down")
                               <<"visualFocus"<<control->property("visualFocus")<<"focused"<<paint->property("focused")<<"focusProgress"<<(focusFill?focusFill->opacity():-1)
                               <<"enabled"<<paint->property("controlEnabled")<<"opacity"<<paint->opacity()<<"moving"<<paint->property("moving")
                               <<"hoverProgress"<<paint->property("hoverProgress")<<"contactProgress"<<paint->property("contactProgress")
                               <<"surfaceScale"<<paint->scale()<<"contentScale"<<(content?content->scale():-1)<<"motionLift"<<control->property("motionLift")
                               <<"normal"<<normal<<"actual"<<paint->property("color");
                    };
                    // The interaction's moving flag excludes the independent color
                    // Behavior. Wait for both its exact token and the motion endpoint
                    // before using a normal frame as this control's baseline.
                    const auto expectedNormal=paint->property("primary").toBool()?eval("Theme.primaryButton").value<QColor>():paint->property("quiet").toBool()?QColor(Qt::transparent):eval("Theme.buttonBase").value<QColor>();
                    fixture->forceActiveFocus(Qt::OtherFocusReason);
                    movePointer(QPoint(window->width()-20,90),0);
                    const bool restingSettled=QTest::qWaitFor([&]{return !control->property("hovered").toBool()&&!control->property("visualFocus").toBool()&&motionRetired()&&sameRenderedColor(paint->property("color").value<QColor>(),expectedNormal);},1000);
                    if(!restingSettled)diagnose("resting",expectedNormal);
                    check(restingSettled,"native pointer leaves and all shared control motion settles before its resting sample");
                    if(!restingSettled)continue;
                    const auto normal=paint->property("color").value<QColor>();
                    const auto restingPixels=window->grabWindow();
                    bool intermediateHoverFrame=false;
                    qreal sampledHoverProgress=0;
                    qint64 sampledHoverMs=-1;
                    int hoveredFrames=0;
                    QElapsedTimer hoverClock;hoverClock.start();
                    // Observe rendered-frame preparation from before input: a fixed sleep can
                    // resume after a short animation has already finished on a busy runner.
                    const auto hoverSample=QObject::connect(window,&QQuickWindow::afterAnimating,fixture,[&]{
                        if(!control->property("hovered").toBool())return;
                        ++hoveredFrames;
                        const auto progress=paint->property("hoverProgress").toReal();
                        if(!intermediateHoverFrame&&paint->property("moving").toBool()&&progress>0&&progress<1){
                            intermediateHoverFrame=true;sampledHoverProgress=progress;sampledHoverMs=hoverClock.elapsed();
                        }
                    });
                    movePointer(control->mapToScene(QPointF(control->width()/2,control->height()/2)).toPoint(),0);
                    const bool sampledIntermediate=QTest::qWaitFor([&]{return intermediateHoverFrame;},1000);
                    QObject::disconnect(hoverSample);
                    qInfo()<<"CONTROL_HOVER_FRAME"<<theme<<name<<"progress"<<sampledHoverProgress<<"inputElapsedMs"<<sampledHoverMs<<"hoveredFrames"<<hoveredFrames;
                    check(sampledIntermediate,"real pointer starts an intermediate hover frame instead of jumping to its endpoint");
                    QTest::qWait(160);
                    qInfo()<<"CONTROL_HOVER"<<theme<<name<<control->property("hovered")<<normal<<paint->property("color")
                           <<"cursor"<<window->mapFromGlobal(QCursor::pos())<<"target"<<control->mapToScene(QPointF(control->width()/2,control->height()/2))<<"active"<<window->isActive();
                    check(QTest::qWaitFor([&]{return control->property("hovered").toBool()&&paint->property("color").value<QColor>()!=normal;},1000),"shared control hover visibly changes its surface");
                    check(!paint->findChild<QQuickItem *>("controlInteractionRim")&&QQmlProperty(paint,"border.width").read().toReal()==0,"hover feedback keeps ordinary controls free of outline strokes");
                    const auto hoveredPixels=window->grabWindow();
                    const qreal dpr=window->devicePixelRatio();
                    const auto rect=control->mapRectToScene(control->boundingRect());
                    const QRect pixelRect(qFloor(rect.x()*dpr),qFloor(rect.y()*dpr),qCeil(rect.width()*dpr),qCeil(rect.height()*dpr));
                    check(!restingPixels.isNull()&&!hoveredPixels.isNull()&&restingPixels.copy(pixelRect)!=hoveredPixels.copy(pixelRect),"hover feedback changes the actual rendered button pixels");
                    if(name!="reviewCombo")check(control->property("motionLift").toReal()<-.5,"hover gently lifts the button without relaying out its shell");
                    control->forceActiveFocus(Qt::TabFocusReason);
                    const bool focusSettled=QTest::qWaitFor([&]{return control->property("visualFocus").toBool()&&paint->property("focused").toBool()&&focusFill&&focusFill->isVisible()&&focusFill->opacity()>.99;},1000);
                    if(!focusSettled)diagnose("focused",normal);
                    check(control->property("visualFocus").toBool()&&paint->property("focused").toBool(),"keyboard focus reaches the shared surface");
                    check(focusSettled&&QQmlProperty(focusFill,"border.width").read().toReal()==0&&QQmlProperty(paint,"border.width").read().toReal()==0,"keyboard focus fills the surface without adding a border");
                    const auto focusedPixels=window->grabWindow();
                    check(!focusedPixels.isNull()&&focusedPixels.copy(pixelRect)!=hoveredPixels.copy(pixelRect),"keyboard focus visibly tints the actual rendered button pixels");
                    if(name!="reviewCombo"){
                        windowInventory("before-press",theme,name);
                        // grabWindow() already blocks until readback completes. Pair a
                        // subsequent normal sync and swap so an older in-flight frame
                        // cannot satisfy this barrier. This does not drain DXGI's queue.
                        struct NormalFrameBarrier {
                            QMutex mutex;
                            std::chrono::steady_clock::time_point start;
                            bool armed=false,pending=false,retired=false;
                            quint64 frame=0,ignoredSwaps=0;
                            qreal synchronizedMs=-1,swappedMs=-1;
                            QJsonObject swapchainProbe;
                        };
                        auto normalFrame=std::make_shared<NormalFrameBarrier>();
                        bool readbackRetired=false;
                        {
                            QObject readbackContext;
                            const auto readbackSync=QObject::connect(window,&QQuickWindow::beforeSynchronizing,&readbackContext,[normalFrame,window]{
                                QMutexLocker lock(&normalFrame->mutex);
                                if(!normalFrame->armed||normalFrame->retired)return;
                                ++normalFrame->frame;normalFrame->pending=true;
                                normalFrame->synchronizedMs=std::chrono::duration<qreal,std::milli>(std::chrono::steady_clock::now()-normalFrame->start).count();
                                if(normalFrame->swapchainProbe.isEmpty())normalFrame->swapchainProbe=appearanceSwapChainProbe(window);
                            },Qt::DirectConnection);
                            const auto readbackFrame=QObject::connect(window,&QQuickWindow::frameSwapped,&readbackContext,[normalFrame]{
                                QMutexLocker lock(&normalFrame->mutex);
                                if(!normalFrame->armed||normalFrame->retired)return;
                                if(!normalFrame->pending){++normalFrame->ignoredSwaps;return;}
                                normalFrame->swappedMs=std::chrono::duration<qreal,std::milli>(std::chrono::steady_clock::now()-normalFrame->start).count();
                                normalFrame->pending=false;normalFrame->retired=true;
                            },Qt::DirectConnection);
                            {QMutexLocker lock(&normalFrame->mutex);normalFrame->start=std::chrono::steady_clock::now();normalFrame->armed=true;}
                            window->update();
                            readbackRetired=QTest::qWaitFor([normalFrame]{QMutexLocker lock(&normalFrame->mutex);return normalFrame->retired;},1000);
                            {QMutexLocker lock(&normalFrame->mutex);normalFrame->armed=false;}
                            QObject::disconnect(readbackSync);QObject::disconnect(readbackFrame);
                        }
                        check(readbackRetired,"a normal frame retires screenshot readback before timed input");
                        {
                            QMutexLocker lock(&normalFrame->mutex);
                            qInfo().noquote()<<"CONTROL_PRESS_NORMAL_FRAME"<<theme<<name<<QJsonDocument(QJsonObject{
                                {"retired",normalFrame->retired},{"frame",qint64(normalFrame->frame)},
                                {"ignoredUnpairedSwaps",qint64(normalFrame->ignoredSwaps)},
                                {"synchronizedMs",normalFrame->synchronizedMs},{"swappedMs",normalFrame->swappedMs},
                                {"swapchainProbe",normalFrame->swapchainProbe}}).toJson(QJsonDocument::Compact);
                        }
                        const auto at=control->mapToScene(QPointF(control->width()/2,control->height()/2)).toPoint();
                        const auto hovered=paint->property("color").value<QColor>();
                        QElapsedTimer pressClock;
                        QJsonArray pressFrames;
                        bool legacyObservedWithin40ms=false;
                        const auto samplePress=[&](const char *phase){
                            if(!pressClock.isValid())return;
                            const qreal elapsed=pressClock.nsecsElapsed()/1000000.0;
                            const auto down=control->property("down").toBool();
                            const auto scale=paint->scale();
                            const auto labelScale=content?content->scale():0;
                            pressFrames.append(QJsonObject{{"phase",QString::fromLatin1(phase)},{"elapsedMs",elapsed},{"down",down},{"contact",paint->property("contactProgress").toReal()},{"surfaceScale",scale},{"contentScale",labelScale}});
                            if((qstrcmp(phase,"afterAnimating")==0||qstrcmp(phase,"frameSwappedQueued")==0)&&elapsed<=40&&down&&scale<.995&&content&&qAbs(labelScale-scale)<.001)legacyObservedWithin40ms=true;
                        };
                        struct SubmittedPressFrames {
                            QMutex mutex;
                            std::chrono::steady_clock::time_point start;
                            bool armed=false;
                            bool inputDown=false;
                            bool pending=false;
                            quint64 frame=0;
                            qreal latestFrameBeginMs=-1;
                            qreal frameBeginMs=-1;
                            qreal synchronizedMs=0;
                            qreal renderStartMs=-1;
                            qreal renderEndMs=-1;
                            qreal surfaceScale=1;
                            qreal contentScale=1;
                            qreal surfaceScaleY=1,contentScaleY=1;
                            qreal surfacePropertyScale=1,contentPropertyScale=1;
                            qreal geometryCapturedMs=-1;
                            QMatrix4x4 surfaceMatrix,contentMatrix;
                            bool hasSceneGraphNodes=false,geometryValid=false;
                            bool hasContent=false;
                            QJsonArray frames;
                        };
                        auto presented=std::make_shared<SubmittedPressFrames>();
                        QObject pressContext;
                        const auto pressAnimation=QObject::connect(window,&QQuickWindow::afterAnimating,&pressContext,[&]{samplePress("afterAnimating");});
                        const auto pressDelivery=QObject::connect(window,&QQuickWindow::frameSwapped,&pressContext,[&]{samplePress("frameSwappedQueued");},Qt::QueuedConnection);
                        const auto pressFrameBegin=QObject::connect(window,&QQuickWindow::beforeFrameBegin,&pressContext,[presented]{
                            QMutexLocker lock(&presented->mutex);
                            // A frame may have begun before input armed this probe.
                            // Keep that boundary unknown instead of inventing a time.
                            presented->latestFrameBeginMs=presented->armed
                                ?std::chrono::duration<qreal,std::milli>(std::chrono::steady_clock::now()-presented->start).count():-1;
                        },Qt::DirectConnection);
                        // Qt 6.12 advances GUI animations after its sync wait.
                        // A queued frameSwapped handler can read the next frame's
                        // values, and itemTransform() can recompute a matrix that was
                        // never adopted by the scene graph. Keep GUI scale as a
                        // diagnostic, but capture the actual existing SG nodes after
                        // sync, then pair those matrices with this frame's submission.
                        // This is not a physical display scan-out timestamp.
                        const auto pressSync=QObject::connect(window,&QQuickWindow::beforeSynchronizing,&pressContext,[presented,paint,content]{
                            QMutexLocker lock(&presented->mutex);
                            if(!presented->armed)return;
                            presented->frameBeginMs=presented->latestFrameBeginMs;
                            presented->latestFrameBeginMs=-1;
                            presented->synchronizedMs=std::chrono::duration<qreal,std::milli>(std::chrono::steady_clock::now()-presented->start).count();
                            presented->renderStartMs=-1;
                            presented->renderEndMs=-1;
                            presented->surfacePropertyScale=paint->scale();
                            presented->hasContent=content!=nullptr;
                            presented->contentPropertyScale=content?content->scale():0;
                            presented->geometryCapturedMs=-1;
                            presented->hasSceneGraphNodes=false;presented->geometryValid=false;
                            ++presented->frame;
                            presented->pending=true;
                        },Qt::DirectConnection);
                        const auto pressGeometry=QObject::connect(window,&QQuickWindow::afterSynchronizing,&pressContext,[presented,paint,content]{
                            QMutexLocker lock(&presented->mutex);
                            if(!presented->armed||!presented->pending)return;
                            // Qt6.12's itemNodeInstance is the already-created node.
                            // Calling itemNode() here would create a missing node and
                            // turn this observation into a scene-graph mutation.
                            const auto *surfaceNode=QQuickItemPrivate::get(paint)->itemNodeInstance;
                            const auto *contentNode=content?QQuickItemPrivate::get(content)->itemNodeInstance:nullptr;
                            presented->geometryCapturedMs=std::chrono::duration<qreal,std::milli>(std::chrono::steady_clock::now()-presented->start).count();
                            presented->hasSceneGraphNodes=surfaceNode&&contentNode;
                            if(!presented->hasSceneGraphNodes)return;
                            presented->surfaceMatrix=surfaceNode->matrix();presented->contentMatrix=contentNode->matrix();
                            bool finite=true;
                            for(int row=0;row<4;++row)for(int column=0;column<4;++column)
                                finite=finite&&qIsFinite(presented->surfaceMatrix(row,column))&&qIsFinite(presented->contentMatrix(row,column));
                            const auto scaleX=[](const QMatrix4x4 &matrix){return qSqrt(qreal(matrix(0,0))*matrix(0,0)+qreal(matrix(1,0))*matrix(1,0));};
                            const auto scaleY=[](const QMatrix4x4 &matrix){return qSqrt(qreal(matrix(0,1))*matrix(0,1)+qreal(matrix(1,1))*matrix(1,1));};
                            presented->surfaceScale=scaleX(presented->surfaceMatrix);presented->surfaceScaleY=scaleY(presented->surfaceMatrix);
                            presented->contentScale=scaleX(presented->contentMatrix);presented->contentScaleY=scaleY(presented->contentMatrix);
                            presented->geometryValid=finite&&presented->surfaceScale>0&&presented->surfaceScaleY>0
                                &&presented->contentScale>0&&presented->contentScaleY>0;
                        },Qt::DirectConnection);
                        const auto pressRenderStart=QObject::connect(window,&QQuickWindow::beforeRendering,&pressContext,[presented]{
                            QMutexLocker lock(&presented->mutex);
                            if(presented->armed&&presented->pending)
                                presented->renderStartMs=std::chrono::duration<qreal,std::milli>(std::chrono::steady_clock::now()-presented->start).count();
                        },Qt::DirectConnection);
                        const auto pressRenderEnd=QObject::connect(window,&QQuickWindow::afterRendering,&pressContext,[presented]{
                            QMutexLocker lock(&presented->mutex);
                            if(presented->armed&&presented->pending)
                                presented->renderEndMs=std::chrono::duration<qreal,std::milli>(std::chrono::steady_clock::now()-presented->start).count();
                        },Qt::DirectConnection);
                        const auto pressSwap=QObject::connect(window,&QQuickWindow::frameSwapped,&pressContext,[presented]{
                            QMutexLocker lock(&presented->mutex);
                            if(!presented->armed||!presented->pending)return;
                            const qreal elapsed=std::chrono::duration<qreal,std::milli>(std::chrono::steady_clock::now()-presented->start).count();
                            presented->frames.append(QJsonObject{{"frame",qint64(presented->frame)},
                                {"frameBeginMs",presented->frameBeginMs},
                                {"synchronizedMs",presented->synchronizedMs},{"swappedMs",elapsed},
                                {"renderStartMs",presented->renderStartMs},{"renderEndMs",presented->renderEndMs},
                                {"down",presented->inputDown},{"surfaceScale",presented->surfaceScale},
                                {"contentScale",presented->contentScale},{"hasContent",presented->hasContent},
                                {"surfaceScaleY",presented->surfaceScaleY},{"contentScaleY",presented->contentScaleY},
                                {"surfacePropertyScale",presented->surfacePropertyScale},{"contentPropertyScale",presented->contentPropertyScale},
                                {"geometryCapturedMs",presented->geometryCapturedMs},{"hasSceneGraphNodes",presented->hasSceneGraphNodes},
                                {"geometryValid",presented->geometryValid},
                                {"surfaceMatrix",appearanceMatrixValues(presented->surfaceMatrix)},
                                {"contentMatrix",appearanceMatrixValues(presented->contentMatrix)}});
                            presented->pending=false;
                        },Qt::DirectConnection);
                        // QTest::qWait polls with sleeps of up to10ms, which can
                        // starve a fast render loop during this strict deadline.
                        QEventLoop pressObservation;
                        QTimer pressDeadline;pressDeadline.setTimerType(Qt::PreciseTimer);pressDeadline.setSingleShot(true);
                        QObject::connect(&pressDeadline,&QTimer::timeout,&pressObservation,&QEventLoop::quit);
                        const QPointF globalAt=window->mapToGlobal(at);
                        QMouseEvent pressEvent(QEvent::MouseButtonPress,QPointF(at),globalAt,
                            Qt::LeftButton,Qt::LeftButton,Qt::NoModifier);
                        {
                            QMutexLocker lock(&presented->mutex);
                            presented->start=std::chrono::steady_clock::now();
                            presented->armed=true;
                        }
                        pressClock.start();pressDeadline.start(40);
                        // Qt 6.12's QTest mouse helper drains processEvents after
                        // delivery. Send the same-stack press before entering the
                        // observation loop so its first frame cannot escape arming.
                        const bool pressDelivered=QCoreApplication::sendEvent(window,&pressEvent);
                        samplePress("inputDelivered");
                        const bool pressDown=control->property("down").toBool();
                        {
                            QMutexLocker lock(&presented->mutex);
                            presented->inputDown=pressDown;
                        }
                        pressObservation.exec();
                        samplePress("deadlineObservation");
                        QJsonArray presentedFrames;
                        {
                            // Acquiring this lock also retires an in-flight direct
                            // callback before any fixture item can be destroyed.
                            // Callbacks entering afterwards see armed=false and never
                            // dereference the captured item pointers. Shared ownership
                            // keeps their synchronization state alive through disconnect.
                            QMutexLocker lock(&presented->mutex);
                            presented->armed=false;
                            presentedFrames=presented->frames;
                        }

                        check(pressDelivered&&pressDown,"same-stack timed press reaches the actual control");
                        bool contractedWithin40ms=false;
                        bool submittedGeometryPresent=!presentedFrames.isEmpty();
                        for(const auto &frame:presentedFrames){
                            const auto sample=frame.toObject();
                            submittedGeometryPresent=submittedGeometryPresent&&sample.value("hasSceneGraphNodes").toBool()&&sample.value("geometryValid").toBool();
                            if(sample.value("swappedMs").toDouble()<=40&&sample.value("down").toBool()
                                &&sample.value("hasSceneGraphNodes").toBool()&&sample.value("geometryValid").toBool()
                                &&sample.value("surfaceScale").toDouble()<.995&&sample.value("hasContent").toBool()
                                &&sample.value("surfaceScaleY").toDouble()<.995
                                &&qAbs(sample.value("contentScale").toDouble()-sample.value("surfaceScale").toDouble())<.001
                                &&qAbs(sample.value("contentScaleY").toDouble()-sample.value("surfaceScaleY").toDouble())<.001)
                                contractedWithin40ms=true;
                        }
                        qInfo().noquote()<<"CONTROL_PRESS_FRAMES"<<theme<<name<<QJsonDocument(pressFrames).toJson(QJsonDocument::Compact);
                        qInfo().noquote()<<"CONTROL_PRESS_SUBMITTED_FRAMES"<<theme<<name
                            <<"legacyObservedWithin40ms"<<legacyObservedWithin40ms<<QJsonDocument(presentedFrames).toJson(QJsonDocument::Compact);
                        check(submittedGeometryPresent,"submitted press frames contain finite scene-graph transforms for surface and label");
                        check(contractedWithin40ms,"a short press contracts both the surface and its label within the first40ms");
                        QObject::disconnect(pressAnimation);QObject::disconnect(pressDelivery);
                        QTest::qWait(100);
                        check(control->property("down").toBool()&&paint->property("color").value<QColor>()!=hovered,"shared button provides a distinct pressed surface");
                        check(QQmlProperty(paint,"border.width").read().toReal()==0,"press feedback does not introduce an outline stroke");
                        QMouseEvent releaseEvent(QEvent::MouseButtonRelease,QPointF(at),globalAt,
                            Qt::LeftButton,Qt::NoButton,Qt::NoModifier);
                        const bool releaseDelivered=QCoreApplication::sendEvent(window,&releaseEvent);
                        const bool released=!control->property("down").toBool();
                        QTest::qWait(30);
                        check(paint->scale()<.999,"release continues from the pressed frame through a spring return");
                        check(releaseDelivered&&released,"same-stack timed release reaches the actual control");
                        check(QTest::qWaitFor([&]{return qAbs(paint->scale()-1)<.001;},1400),"released button springs back to its resting scale");
                        if(theme=="Light" && name=="reviewButton"){
                            SwirlPressClock *nativeClock=nullptr;
                            for(auto *candidate:control->findChildren<SwirlPressClock *>())
                                if(candidate->surfaceTarget()==paint && candidate->contentTarget()==content)nativeClock=candidate;
                            check(nativeClock!=nullptr,"ordinary review button owns its production native press clock");
                            if(nativeClock){
                                const auto armNative=[&]{
                                    QMutexLocker lock(&presented->mutex);
                                    presented->start=std::chrono::steady_clock::now();
                                    presented->frames=QJsonArray();presented->pending=false;
                                    presented->latestFrameBeginMs=-1;presented->inputDown=true;presented->armed=true;
                                };
                                const auto submittedContraction=[&]{
                                    QMutexLocker lock(&presented->mutex);
                                    for(const auto &entry:presented->frames){const auto frame=entry.toObject();
                                        if(frame.value("geometryValid").toBool() && frame.value("surfaceScale").toDouble()<.995
                                            && frame.value("surfaceScaleY").toDouble()<.995
                                            && qAbs(frame.value("surfaceScaleY").toDouble()-frame.value("contentScaleY").toDouble())<.001
                                            && frame.value("swappedMs").toDouble()<=40
                                            && qAbs(frame.value("surfaceScale").toDouble()-frame.value("contentScale").toDouble())<.001)
                                            return true;
                                    }
                                    return false;
                                };
                                const auto adoptedScale=[&]{
                                    QMutexLocker lock(&presented->mutex);
                                    return QPointF(presented->surfaceScale,presented->contentScale);
                                };
                                const auto sendMouse=[&](QEvent::Type type){
                                    QMouseEvent event(type,QPointF(at),globalAt,Qt::LeftButton,
                                        type==QEvent::MouseButtonPress?Qt::LeftButton:Qt::NoButton,Qt::NoModifier);
                                    return QCoreApplication::sendEvent(window,&event);
                                };
                                armNative();pressDeadline.start(40);sendMouse(QEvent::MouseButtonPress);pressObservation.exec();
                                check(submittedContraction(),"native reversal fixture observes a submitted paired contraction within the first40ms");
                                // These values came from existing SG nodes after sync. The
                                // same-stack release must hand off that adopted pose to
                                // the GUI spring, rather than the earlier GUI clock value.
                                const auto adopted=adoptedScale();sendMouse(QEvent::MouseButtonRelease);
                                check(qAbs(paint->scale()-adopted.x())<.001 && qAbs(content->scale()-adopted.y())<.001,
                                    "native press release starts its spring from the actual adopted paired geometry");
                                // Deliver re-press during a real GUI spring update that
                                // has not yet reached the scene graph. The previous node
                                // matrices remain the visual origin for this reversal.
                                QPointF springOrigin;
                                bool reversedSpring=false,repressContinuous=false;
                                QEventLoop reversalObservation;
                                QTimer reversalBudget,repressDeadline;
                                reversalBudget.setSingleShot(true);repressDeadline.setSingleShot(true);
                                repressDeadline.setTimerType(Qt::PreciseTimer);
                                QObject::connect(&reversalBudget,&QTimer::timeout,&reversalObservation,&QEventLoop::quit);
                                QObject::connect(&repressDeadline,&QTimer::timeout,&reversalObservation,&QEventLoop::quit);
                                const auto reverseSpring=QObject::connect(window,&QQuickWindow::afterAnimating,&pressContext,[&]{
                                    if(reversedSpring)return;
                                    const auto actual=adoptedScale();const auto gui=paint->scale();
                                    if(actual.x()<=.983 || gui>=.999 || qAbs(gui-actual.x())<.0001)return;
                                    springOrigin=actual;armNative();repressDeadline.start(40);
                                    sendMouse(QEvent::MouseButtonPress);reversedSpring=true;
                                    repressContinuous=qAbs(paint->scale()-springOrigin.x())<.001
                                        && qAbs(content->scale()-springOrigin.y())<.001;
                                });
                                reversalBudget.start(1400);reversalObservation.exec();reversalBudget.stop();repressDeadline.stop();
                                QObject::disconnect(reverseSpring);
                                QJsonArray reverseFrames;
                                {QMutexLocker lock(&presented->mutex);reverseFrames=presented->frames;}
                                bool firstRepressContinuous=false;
                                if(!reverseFrames.isEmpty()){
                                    const auto first=reverseFrames.first().toObject();
                                    firstRepressContinuous=first.value("swappedMs").toDouble()<=40
                                        && first.value("geometryValid").toBool()
                                        && first.value("surfaceScale").toDouble()<=springOrigin.x()+.001
                                        && first.value("contentScale").toDouble()<=springOrigin.y()+.001
                                        && first.value("surfaceScaleY").toDouble()<=springOrigin.x()+.001
                                        && first.value("contentScaleY").toDouble()<=springOrigin.y()+.001
                                        && qAbs(first.value("surfaceScaleY").toDouble()-first.value("contentScaleY").toDouble())<.001
                                        && qAbs(first.value("surfaceScale").toDouble()-first.value("contentScale").toDouble())<.001;
                            }
                            qInfo().noquote()<<"NATIVE_PRESS_SPRING_REVERSAL"<<QJsonDocument(QJsonObject{
                                {"exercised",reversedSpring},{"sameStackContinuous",repressContinuous},
                                {"adoptedSurfaceBefore",springOrigin.x()},{"adoptedContentBefore",springOrigin.y()},
                                {"submittedFrames",reverseFrames}}).toJson(QJsonDocument::Compact);
                            check(reversedSpring && repressContinuous,"re-press reverses from the actual adopted spring pose in the input stack");
                            check(reversedSpring && firstRepressContinuous,"the first submitted re-press preserves adopted geometry within40ms");
                            sendMouse(QEvent::MouseButtonRelease);
                            check(QTest::qWaitFor([&]{return !nativeClock->running() && qAbs(paint->scale()-1)<.001;},1400),
                                "native release retires its clock and settles normally");
                            control->forceActiveFocus(Qt::TabFocusReason);armNative();pressDeadline.start(40);
                            QKeyEvent keyDown(QEvent::KeyPress,Qt::Key_Space,Qt::NoModifier);
                            const bool keyboardDelivered=QCoreApplication::sendEvent(window,&keyDown);
                            const bool keyboardDown=control->property("down").toBool();
                            pressObservation.exec();
                            check(keyboardDelivered && keyboardDown && submittedContraction(),
                                "Space activation submits paired native surface and label geometry within the first40ms");
                            const auto keyboardAdopted=adoptedScale();
                            QKeyEvent keyUp(QEvent::KeyRelease,Qt::Key_Space,Qt::NoModifier);
                            QCoreApplication::sendEvent(window,&keyUp);
                            check(!control->property("down").toBool() && qAbs(paint->scale()-keyboardAdopted.x())<.001
                                && qAbs(content->scale()-keyboardAdopted.y())<.001 && control->scale()==1,
                                "Space release preserves the adopted pose and stable hit area");
                            check(QTest::qWaitFor([&]{return !nativeClock->running() && qAbs(paint->scale()-1)<.001;},1400),
                                "Space release settles the production native clock");
                            const auto visibility=window->visibility();
                            sendMouse(QEvent::MouseButtonPress);
                            check(nativeClock && nativeClock->running(),"window hide interrupts an active production native press");
                            window->hide();
                            check(!nativeClock->running() && !paint->property("moving").toBool(),
                                "hiding the real window retires native press callbacks and feedback motion");
                            window->setVisibility(visibility);window->requestActivate();sendMouse(QEvent::MouseButtonRelease);
                            check(QTest::qWaitFor([&]{return !control->property("down").toBool() && !nativeClock->running()
                                && qAbs(paint->scale()-1)<.001 && qAbs(content->scale()-1)<.001;},1400),
                                "restoring the real window leaves no stale paired press transform");
                            {QMutexLocker lock(&presented->mutex);presented->armed=false;}
                            }
                        }
                        QObject::disconnect(pressFrameBegin);QObject::disconnect(pressSync);QObject::disconnect(pressGeometry);QObject::disconnect(pressRenderStart);
                        QObject::disconnect(pressRenderEnd);QObject::disconnect(pressSwap);
                    }
                    control->setEnabled(false);
                    // Compare exact premultiplied channels: RGB hidden by alpha=0
                    // has no rendered effect; opaque channel differences still fail.
                    const bool disabledSettled=QTest::qWaitFor([&]{return !paint->property("controlEnabled").toBool()&&!control->property("down").toBool()&&paint->opacity()<1&&motionRetired()&&sameRenderedColor(paint->property("color").value<QColor>(),normal);},1000);
                    if(!disabledSettled)diagnose("disabled",normal);
                    check(disabledSettled,"disabled surface retires hover and press feedback");
                    check(control->size()==size&&control->position()==position,"all button states retain shell geometry");
                    control->setEnabled(true);
                }
                for(const auto &strategy:QStringList{"manual","url_test","fallback","load_balance"}){
                    auto *control=visualItem(fixture,"createPolicyGroup-"+strategy);auto *paint=surface(control);
                    check(control&&paint,"strategy creation action uses its real card surface");
                    if(!control||!paint)continue;
                    const auto size=control->size();
                    movePointer(QPoint(window->width()-15,90));
                    check(QTest::qWaitFor([&]{return !control->property("hovered").toBool();},1000),"native pointer leaves the strategy card before its resting sample");
                    const auto normal=paint->property("color").value<QColor>();
                    const auto at=control->mapToScene(QPointF(control->width()/2,control->height()/2)).toPoint();
                    movePointer(at);
                    qInfo()<<"CARD_HOVER"<<theme<<strategy<<paint->property("hovered")<<normal<<paint->property("color")
                           <<"cursor"<<window->mapFromGlobal(QCursor::pos())<<"target"<<at<<"active"<<window->isActive();
                    check(QTest::qWaitFor([&]{return paint->property("hovered").toBool()&&paint->property("color").value<QColor>()!=normal;},1000),"strategy creation card brightens on hover");
                    control->forceActiveFocus(Qt::TabFocusReason);QTest::qWait(160);
                    check(paint->property("focused").toBool(),"strategy creation card has keyboard focus feedback");
                    QTest::mousePress(window,Qt::LeftButton,Qt::NoModifier,at);QTest::qWait(160);
                    check(control->property("down").toBool()&&paint->property("color").value<QColor>()!=normal&&paint->scale()<1,"strategy creation card has visible press and contact feedback");
                    QTest::mouseMove(window,QPoint(window->width()-15,90));QTest::mouseRelease(window,Qt::LeftButton,Qt::NoModifier,QPoint(window->width()-15,90));
                    control->setEnabled(false);QTest::qWait(180);
                    check(paint->opacity()<1&&!paint->property("hovered").toBool()&&control->size()==size,"disabled strategy card dims and retains its click geometry");
                    control->setEnabled(true);
                }
            }
            auto *figures=fixture->findChild<QQuickItem *>("reviewFigures");
            for(const auto &family:QStringList{eval("Theme.fontFamily").toString(),"Segoe UI","Microsoft YaHei UI"}){
                if(!QFontDatabase::families().contains(family))continue;
                QFont font=figures->property("font").value<QFont>();font.setFamily(family);figures->setProperty("font",font);QTest::qWait(40);
                font=figures->property("font").value<QFont>();const QFontMetricsF metrics(font);
                check((font.styleStrategy()&QFont::ContextFontMerging)&&(font.styleStrategy()&QFont::PreferTypoLineMetrics),"mixed-script text retains contextual fallback and typographic line metrics");
                check(qAbs(metrics.horizontalAdvance("111111")-metrics.horizontalAdvance("888888"))<0.05,"numeric glyph updates retain equal advances in bundled and Windows fonts");
                check(figures->baselineOffset()>0&&figures->baselineOffset()<=figures->height(),"mixed-script baseline remains inside measured text height");
            }
            auto *teardownButton=fixture->findChild<QQuickItem *>("reviewButton");
            QPointer<SwirlPressClock> teardownClock;
            if(teardownButton)for(auto *candidate:teardownButton->findChildren<SwirlPressClock *>())
                if(candidate->surfaceTarget()==teardownButton->property("background").value<QQuickItem *>()
                    && candidate->contentTarget()==teardownButton->property("contentItem").value<QQuickItem *>())teardownClock=candidate;
            if(teardownButton){
                const auto at=teardownButton->mapToScene(QPointF(teardownButton->width()/2,teardownButton->height()/2));
                QMouseEvent press(QEvent::MouseButtonPress,at,window->mapToGlobal(at.toPoint()),
                    Qt::LeftButton,Qt::LeftButton,Qt::NoModifier);
                QCoreApplication::sendEvent(window,&press);
            }
            check(teardownClock && teardownClock->running(),"fixture destruction interrupts a live native paired press");
            delete fixture;
            check(teardownClock.isNull(),"destroying a pressed control releases its production clock and transforms");
            int fullMotionIdleFrames=0;
            QObject idleReceiver;
            const auto idleConnection=QObject::connect(window,&QQuickWindow::frameSwapped,&idleReceiver,[&]{++fullMotionIdleFrames;});
            QTest::qWait(650);QObject::disconnect(idleConnection);
            qInfo()<<"NATIVE_PRESS_FULL_MOTION_IDLE_FRAMES"<<fullMotionIdleFrames;
            check(fullMotionIdleFrames<=4,"completed and destroyed native press clocks leave no full-motion idle drawing loop");
        }
    }
    stage("shared-controls-and-fonts");
    eval("Theme.reduceMotion=false;AppState.navigate('settings')");
    check(QTest::qWaitFor([&]{return eval("pageLoader.item && !pageLoader.pendingGrab && !pageLoader.moving && pageLoader.activeLoader.routeId==='settings'").toBool();},3500),"general settings with appearance controls settles before input");
    std::function<QQuickItem *(QQuickItem *,const QString &)> find=[&](QQuickItem *item,const QString &name)->QQuickItem *{if(item->objectName()==name)return item;for(auto *child:item->childItems())if(auto *match=find(child,name))return match;return nullptr;};
    auto *picker=find(window->contentItem(),"themeModePicker");check(picker&&picker->isVisible()&&picker->isEnabled(),"theme picker is visible and enabled");
    if(picker){
        window->resize(800,672);QTest::qWait(150);
        auto select=[&](int index){
            window->requestActivate();
            const auto center=picker->mapToScene(QPointF(picker->width()/2,picker->height()/2));
            const bool inside=QRectF(QPointF(0,0),window->size()).contains(center);
            check(inside,"theme picker hit area stays inside the narrow viewport");
            if(!inside)return;
            QTest::mouseClick(window,Qt::LeftButton,Qt::NoModifier,center.toPoint());QTest::qWait(150);
            auto *popup=qvariant_cast<QObject *>(picker->property("popup"));
            check(popup && popup->property("visible").toBool(),"theme click opens the in-window popup");
            if(popup){
                auto *content=qvariant_cast<QQuickItem *>(popup->property("contentItem"));
                auto *choice=content?find(content,"swirlComboOption-"+QString::number(index)):nullptr;
                check(choice!=nullptr,"theme choice exists");
                if(choice)QTest::mouseClick(window,Qt::LeftButton,Qt::NoModifier,choice->mapToScene(QPointF(choice->width()/2,choice->height()/2)).toPoint());
                check(QTest::qWaitFor([&]{return !popup->property("visible").toBool();},1200),"theme selection releases the popup input grab");
            }
        };
        select(2);check(eval("Theme.mode==='Dark' && Theme.dark").toBool(),"pointer theme interaction applies dark palette");
        select(1);check(eval("Theme.mode==='Light' && !Theme.dark").toBool(),"pointer theme interaction applies light palette");
        select(0);check(eval("Theme.mode==='System' && Theme.dark===(Qt.styleHints.colorScheme===Qt.Dark)").toBool(),"system mode follows actual Qt color scheme");
        window->requestActivate();picker->forceActiveFocus();QTest::qWait(80);QTest::keyClick(window,Qt::Key_End);QTest::qWait(150);
        check(eval("Theme.mode==='Dark' && Theme.dark").toBool(),"keyboard theme selection updates palette");
        for(int round=0;round<3;++round){select(1);select(2);select(0);}
        auto *contrast=find(window->contentItem(),"increaseContrastToggle");
        if(contrast){
            const auto at=contrast->mapToScene(QPointF(contrast->width()/2,contrast->height()/2)).toPoint();
            const auto before=eval("Theme.increaseContrast").toBool();
            QTest::mouseClick(window,Qt::LeftButton,Qt::NoModifier,at);QTest::qWait(100);
            check(eval("Theme.increaseContrast").toBool()!=before,"switch remains clickable after repeated theme selections");
            QTest::mouseClick(window,Qt::LeftButton,Qt::NoModifier,at);
        } else check(false,"contrast switch exists");
        select(2);
    }
    stage("theme-input-and-popup-cycles");
    check(eval("!scaledCanvas.layer.enabled").toBool(),"text canvas is not a resampled window texture");
    eval("Theme.followSystemMotion=true;Theme.appearanceSettings.sync()");QTest::qWait(250);
    QSettings settings;check(QTest::qWaitFor([&]{settings.sync();return settings.value("Appearance/savedMode").toString()=="Dark"&&settings.value("Appearance/savedFollowSystemMotion").toBool();},3000),"chosen theme and motion preference are persisted");
    stage("settings-persistence");
    const auto restorePath=QCoreApplication::applicationDirPath()+"/Swirl-appearance-restore.txt";
    const bool oldRestoreRemoved=!QFileInfo::exists(restorePath)||QFile::remove(restorePath);
    check(oldRestoreRemoved,"old restoration output is removed before starting the new process");
    QProcess child;qint64 childPid=0;
    QObject::connect(&child,&QProcess::started,&child,[&]{childPid=child.processId();});
    const auto childStartedAt=QDateTime::currentDateTimeUtc();
    child.start(QCoreApplication::applicationFilePath(),{"--appearance-restore-test","--preview-preserve-settings"});
    // A second native GUI process may need messages from the parent HWND during
    // initialization. Keep this event loop live instead of blocking it in waitForFinished.
    const bool childFinished=QTest::qWaitFor([&]{return child.state()==QProcess::NotRunning;},15000);
    check(childFinished&&child.exitStatus()==QProcess::NormalExit&&child.exitCode()==0,"fresh application process confirms theme restoration");
    if(!childFinished){child.kill();child.waitForFinished(1000);}
    QFile restoreOutput(restorePath);
    const bool restoreReadable=oldRestoreRemoved&&restoreOutput.open(QIODevice::ReadOnly);
    const auto restoreText=restoreReadable?restoreOutput.readAll():QByteArray();
    const auto expectedProcess=QByteArray("APPEARANCE_RESTORE_PROCESS ")+QByteArray::number(childPid);
    const bool freshRestore=restoreReadable&&childPid>0&&QFileInfo(restorePath).lastModified().toUTC()>=childStartedAt&&restoreText.contains(expectedProcess)&&restoreText.contains("PASS new process restores saved dark theme and explicit system-motion preference");
    check(freshRestore,"restoration evidence belongs to this newly started process");
    qInfo()<<"APPEARANCE_RESTORE_RESULT"<<"pid"<<childPid<<"startedUtc"<<childStartedAt<<"finished"<<childFinished<<"state"<<child.state()<<"error"<<child.error()<<"freshOutput"<<freshRestore;
    stage("fresh-process-restoration");
    window->requestActivate();
    eval("Theme.transparency=true;Theme.increaseContrast=false;AppState.navigate('activity')");
    check(QTest::qWaitFor([&]{return eval("pageLoader.activeLoader.routeId==='activity' && !pageLoader.pendingGrab && !pageLoader.moving").toBool();},3500),"activity route settles");
    auto *pane=find(window->contentItem(),"sidebarFloatingBackground");
    check(pane!=nullptr,"sidebar pane exists");
    if(pane){
        check(pane->metaObject()->indexOfProperty("color")==-1 && pane->opacity()==1,"sidebar container has no fill or foreground opacity workaround");
        auto *glass=find(pane,"sidebarLiquidGlass");
        auto *workspace=qvariant_cast<QQuickItem *>(eval("appSceneBackdrop"));
        auto *source=qvariant_cast<QQuickItem *>(eval("appSceneBackdrop.decorationSource"));
        auto *shader=glass?glass->findChild<QObject *>("sidebarLiquidShader"):nullptr;
        check(glass && source && qvariant_cast<QQuickItem *>(glass->property("backdropSource"))==source,"clear sidebar remains over the original application backdrop");
        check(shader && shader->property("status").toInt()==0 && shader->property("log").toString().isEmpty(),"production sidebar material shader is compiled without errors");
        const auto capture=[&](QQuickItem *item){
            if(!item)return QImage{};
            auto result=item->grabToImage();if(!result)return QImage{};
            QSignalSpy ready(result.data(),&QQuickItemGrabResult::ready);window->update();
            if(result->image().isNull())ready.wait(2000);
            return result->image();
        };
        const auto noSampling=[&]{
            if(!glass || glass->property("sampled").toBool() || glass->property("captureLive").toBool())return false;
            for(auto *child:glass->findChildren<QObject *>()){
                const QByteArray type=child->metaObject()->className();
                if(type.contains("ShaderEffectSource") || type.contains("Blur") || type.contains("MultiEffect"))return false;
            }
            return glass->opacity()==1;
        };
        // A broad inset rectangle excludes the rounded rim independently of
        // the shader's contour formula. Compare every interior RGBA pixel.
        const auto interior=[&](const QImage &image){
            if(image.isNull() || !glass)return QRect();
            const auto dpr=qreal(image.width())/glass->width();
            const int inset=qCeil(glass->property("cornerRadius").toReal()*dpr)+2;
            return image.rect().adjusted(inset,inset,-inset,-inset);
        };
        const auto clearMaterial=[&](const QImage &image){
            const auto bounds=interior(image);if(bounds.width()<=0 || bounds.height()<=0)return false;
            for(int y=bounds.top();y<=bounds.bottom();++y)for(int x=bounds.left();x<=bounds.right();++x)
                if(image.pixelColor(x,y).alpha()!=0)return false;
            return true;
        };
        const auto unchangedParent=[&]{
            if(!glass)return false;
            const auto withPane=window->grabWindow();
            pane->setVisible(false);QTest::qWait(35);const auto withoutPane=window->grabWindow();
            pane->setVisible(true);QTest::qWait(35);
            if(withPane.isNull() || withPane.size()!=withoutPane.size())return false;
            const auto dpr=window->devicePixelRatio();
            const int inset=qCeil(glass->property("cornerRadius").toReal()*dpr)+2;
            const auto origin=glass->mapToScene(QPointF())*dpr;
            const QRect bounds(qRound(origin.x())+inset,qRound(origin.y())+inset,qRound(glass->width()*dpr)-2*inset,qRound(glass->height()*dpr)-2*inset);
            return bounds.width()>0 && bounds.height()>0 && withPane.rect().contains(bounds)
                && withPane.copy(bounds)==withoutPane.copy(bounds);
        };
        QImage lightMaterial,darkMaterial;
        for(const QString theme:{QStringLiteral("Light"),QStringLiteral("Dark")}){
            eval(QStringLiteral("Theme.mode='%1';Theme.reduceMotion=true;Theme.increaseContrast=false").arg(theme));QTest::qWait(180);
            const auto material=capture(glass);
            check(noSampling(),"clear sidebar never samples or blurs the original scene");
            check(clearMaterial(material),"every tested material interior pixel has exactly zero alpha");
            check(unchangedParent(),"parent wing, colour and foreground RGBA pixels are unchanged through the sidebar");
            if(theme=="Light"){
                lightMaterial=material;
                check(eval("Theme.canvas.toString()==='#f7f7f7' && Theme.surface.toString()==='#ffffff' && Theme.border.toString()==='#e0e0e3'").toBool(),"accepted neutral light canvas and surface colours remain unchanged");
            }else darkMaterial=material;
        }
        qint64 lightAlpha=0,darkAlpha=0;int lightPeak=0,darkPeak=0;
        if(!lightMaterial.isNull() && darkMaterial.size()==lightMaterial.size())
            for(int y=0;y<lightMaterial.height();++y)for(int x=0;x<lightMaterial.width();++x){
                const int light=lightMaterial.pixelColor(x,y).alpha(),dark=darkMaterial.pixelColor(x,y).alpha();
                lightAlpha+=light;darkAlpha+=dark;lightPeak=qMax(lightPeak,light);darkPeak=qMax(darkPeak,dark);
            }
        check(darkAlpha>0 && darkAlpha<lightAlpha*.4 && darkPeak<lightPeak*.5,"dark edge retains a quiet contour instead of the light continuous bright bevel");
        const auto before=window->grabWindow();
        QQmlComponent fixture(qmlEngine(window));
        fixture.setData("import QtQuick; Rectangle {width:600;height:900;color:'#D02A65'; Text {anchors.fill:parent;text:'RIGHT PAGE CONTENT';font.pixelSize:60;wrapMode:Text.Wrap}}",QUrl());
        auto *overlay=qobject_cast<QQuickItem *>(fixture.create());
        auto *mainArea=qvariant_cast<QQuickItem *>(eval("mainArea"));
        check(overlay && mainArea,"right-page regression fixture created");
        if(overlay && mainArea){
            overlay->setParentItem(mainArea);overlay->setZ(999);window->update();QTest::qWait(250);
            const auto after=window->grabWindow();
            const auto origin=pane->mapToScene(QPointF(pane->width()-18,120))*window->devicePixelRatio();
            const QRect strip(origin.toPoint(),QSize(4,qRound((pane->height()-240)*window->devicePixelRatio())));
            check(!before.isNull() && !after.isNull() && before.copy(strip)==after.copy(strip),"right-page text and color never get copied underneath sidebar navigation");
        }
        delete overlay;
        eval("Theme.increaseContrast=true");QTest::qWait(150);
        check(noSampling() && clearMaterial(capture(glass)) && unchangedParent(),"high-contrast outline preserves the fully clear sidebar interior");
        eval("Theme.increaseContrast=false;Theme.transparency=false");QTest::qWait(150);
        check(noSampling() && clearMaterial(capture(glass)) && unchangedParent(),"window transparency preference never adds a sidebar fill or captured scene");
        QQuickItem *workspaceBase=nullptr;
        if(workspace)for(auto *child:workspace->childItems())if(child->property("tintOpacity").isValid()){workspaceBase=child;break;}
        check(workspaceBase && workspaceBase->property("tintOpacity").toReal()==1 && workspaceBase->property("color").value<QColor>()==eval("Theme.canvas").value<QColor>(),"opaque workspace base still uses the shared canvas token");
        check(source && source->isVisible(),"opaque workspace keeps the original global wing visible");
        eval("Theme.transparency=true");QTest::qWait(150);
        check(noSampling() && clearMaterial(capture(glass)) && unchangedParent(),"restoring window transparency preserves the original clear sidebar scene");
    }
    auto *proxy=find(window->contentItem(),"proxyCapsule");
    if(proxy){
        // Observe real ownership without operating the host proxy. Controlled
        // states below exercise the same component against a counting fake.
        const bool active=eval("engineController.proxyRequested || engineController.systemProxy.owned || engineController.processAlive").toBool();
        const bool pending=eval("engineController.systemProxyBusy").toBool();
        const bool stopping=eval("engineController.systemProxyStopping").toBool();
        check(proxy->property("proxyEnabled").toBool()==active,"master proxy control reflects Swirl runtime and owned settings");
        const auto label=stopping?QStringLiteral("正在关闭代理…"):pending?QStringLiteral("正在开启代理…"):QStringLiteral("系统代理");
        check(proxy->property("label").toString()==label,"proxy label is stable outside explicit pending operations");
        check(eval("proxyCapsule.proxyWing && SwirlProxyWingMotion.active===proxyCapsule.proxyOwned && proxyCapsule.Accessible.description===proxyCapsule.detail").toBool(),"production wing ownership and accessible status stay bound to actual runtime state");
        auto *weave=find(window->contentItem(),"activityCloudKnotWeave");
        check(weave && weave->property("active").toBool()==proxy->property("proxyOwned").toBool(),"Activity knot animation is bound to actual owned proxy state");
    } else check(false,"system proxy switch exists");
    QQmlComponent proxyFixture(qmlEngine(window));
    proxyFixture.setData(R"QML(
import QtQuick
import SwirlQuick
Item {
 id: fixture; x:230; y:90; width:420; height:60; z:1100
 property alias control: capsule
 property QtObject fake: QtObject {
  property bool proxyRequested:false; property bool processAlive:false
  property bool systemProxyBusy:false; property bool systemProxyStopping:false
  property bool busy:false; property bool policyBusy:false
  property string routingError:""; property string policyError:""; property string errorCode:"None"; property string error:""
  property int toggleCalls:0
  property QtObject imports:QtObject {property bool busy:false}
  property QtObject systemProxy:QtObject {
   property bool owned:false; property bool enabled:false; property bool systemEnabled:false
   property string stateReadError:""; property string error:""
  }
  function toggleSystemProxy(){++toggleCalls}
 }
 function scenario(name){
  fake.proxyRequested=false;fake.processAlive=false;fake.systemProxyBusy=false;fake.systemProxyStopping=false
  fake.systemProxy.owned=false;fake.systemProxy.enabled=false;fake.systemProxy.systemEnabled=false;fake.systemProxy.stateReadError=""
  if(name==="external")fake.systemProxy.systemEnabled=true
  if(name==="core")fake.processAlive=true
  if(name==="owned"){fake.proxyRequested=true;fake.processAlive=true;fake.systemProxy.owned=true;fake.systemProxy.enabled=true}
  if(name==="starting"){fake.proxyRequested=true;fake.systemProxyBusy=true}
  if(name==="stopping"){fake.proxyRequested=true;fake.systemProxyStopping=true}
  if(name==="error")fake.systemProxy.stateReadError="受控读取失败"
 }
 SwirlSystemProxyCapsule {id:capsule;controller:fixture.fake;width:240;height:32}
})QML",QUrl("qrc:/qt/qml/SwirlQuick/ProxyAppearanceFixture.qml"));
    auto *proxyStates=qobject_cast<QQuickItem *>(proxyFixture.create(qmlContext(window)));
    check(proxyStates!=nullptr,"isolated proxy presentation fixture loads");
    if(proxyStates){
        proxyStates->setParentItem(window->contentItem());
        auto *control=qvariant_cast<QQuickItem *>(proxyStates->property("control"));
        auto *fake=proxyStates->property("fake").value<QObject *>();
        for(const QString scenario:{QStringLiteral("idle"),QStringLiteral("external"),QStringLiteral("core"),QStringLiteral("owned"),QStringLiteral("starting"),QStringLiteral("stopping"),QStringLiteral("error")}){
            QMetaObject::invokeMethod(proxyStates,"scenario",Q_ARG(QVariant,scenario));QTest::qWait(35);
            const bool starting=scenario=="starting",stopping=scenario=="stopping",error=scenario=="error",owned=scenario=="owned";
            const auto expectedLabel=starting?QStringLiteral("正在开启代理…"):stopping?QStringLiteral("正在关闭代理…"):QStringLiteral("系统代理");
            check(control && control->property("label").toString()==expectedLabel,"controlled proxy states retain stable label or specific pending text");
            check(control && control->property("proxyEnabled").toBool()==(owned || scenario=="core" || starting || stopping)
                && control->property("proxyOwned").toBool()==owned,"proxy presentation derives enabled and ownership from controller state");
            check(control && control->property("tone").toString()==(error?"warning":owned?"success":"neutral")
                && control->property("activityPhase").toString()==(starting || stopping?"pending":error?"failed":owned?"succeeded":"idle"),"state glyph phase and tone follow actual controller semantics");
            const auto detailToken=starting?QStringLiteral("正在启动已保存策略"):stopping?QStringLiteral("正在结束配置操作"):error?QStringLiteral("受控读取失败"):owned?QStringLiteral("已接管系统代理"):scenario=="external"?QStringLiteral("其他应用的系统代理已开启"):scenario=="core"?QStringLiteral("内核正在运行"):QStringLiteral("点击启动已保存策略");
            const auto accessibleDescription=QQmlProperty::read(control,QStringLiteral("Accessible.description"),qmlContext(control));
            qInfo()<<"PROXY_APPEARANCE_ACCESSIBLE"<<scenario<<accessibleDescription<<"expected detail token"<<detailToken;
            check(control && control->property("detail").toString().contains(detailToken)
                && accessibleDescription.isValid() && accessibleDescription==control->property("detail")
                && (!error || control->property("detail").toString()=="受控读取失败"),"accessible description preserves operation and error details");
            const auto calls=fake?fake->property("toggleCalls").toInt():-1;
            if(control)QTest::mouseClick(window,Qt::LeftButton,Qt::NoModifier,control->mapToScene(QPointF(control->width()/2,control->height()/2)).toPoint());
            check(fake && fake->property("toggleCalls").toInt()==calls+((stopping || error)?0:1),"proxy button invokes only its isolated controller and respects blocked states");
        }
        delete proxyStates;
    }else qWarning()<<proxyFixture.errors();


    stage("glass-and-runtime-state");
    qInfo()<<"APPEARANCE_CHECKS failures"<<failures<<"totalMs"<<totalClock.elapsed();return failures?2:0;
}
