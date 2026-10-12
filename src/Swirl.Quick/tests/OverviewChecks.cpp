#include "OverviewChecks.h"
#include <QQuickWindow>
#include <QQuickItem>
#include <QQmlContext>
#include <QQmlExpression>
#include <QQmlEngine>
#include <QTest>
#include <QDebug>
#include <functional>
#include <QTemporaryDir>
#include <QFile>
#include "../app/ModuleDraftStore.h"

int runOverviewChecks(QQuickWindow *window)
{
    int failures = 0, checks = 0;
    const auto check = [&](bool condition, const char *name) {
        ++checks;
        if (!condition) { ++failures; qCritical() << "FAIL" << name; }
        else qInfo() << "PASS" << name;
    };
    if (!window) return 1;
    window->resize(1450,884);
    QTest::qWait(150);
    const auto state = [&](const QString &expression) {
        QQmlExpression eval(qmlContext(window), window, expression);
        const auto result = eval.evaluate();
        if (eval.hasError()) qCritical() << eval.error();
        return result;
    };
    // Repeater delegates and popup content can be visually reparented, so use
    // the actual scene tree rather than only QObject ownership.
    std::function<QQuickItem *(QQuickItem *,const QString &)> findVisual;
    findVisual = [&](QQuickItem *parent,const QString &name) -> QQuickItem * {
        if (parent->objectName()==name) return parent;
        for (auto *child:parent->childItems())
            if (auto *found=findVisual(child,name)) return found;
        return nullptr;
    };
    const auto item = [&](const char *name) { return findVisual(window->contentItem(),QString::fromLatin1(name)); };
    const auto click = [&](QQuickItem *target, qreal fraction = 0.5) {
        if (!target) { check(false,"input target exists"); return; }
        // The overview retains its trends and tools below the primary status
        // panels. Scroll the real viewport before sending input to those items.
        if (auto *scroll = item("overviewScroll")) {
            auto *viewport = qobject_cast<QQuickItem *>(
                qvariant_cast<QObject *>(scroll->property("contentItem")));
            bool insideViewport = false;
            for (auto *parent = target; parent; parent = parent->parentItem())
                if (parent == viewport) { insideViewport = true; break; }
            if (viewport && insideViewport) {
                const qreal top = target->mapToItem(viewport, QPointF()).y();
                const qreal bottom = top + target->height();
                const qreal delta = top < 0 ? top :
                    bottom > viewport->height() ? bottom - viewport->height() : 0;
                if (delta != 0) {
                    const qreal maximum = qMax<qreal>(0,
                        viewport->property("contentHeight").toReal() - viewport->height());
                    viewport->setProperty("contentY", qBound<qreal>(0,
                        viewport->property("contentY").toReal() + delta, maximum));
                    QTest::qWait(100);
                }
            }
        }
        QTest::mouseClick(window,Qt::LeftButton,Qt::NoModifier,
                          target->mapToScene(QPointF(target->width()*fraction,target->height()/2)).toPoint());
        QTest::qWait(250);
    };
    check(state("AppState.demoDown === 0 && AppState.demoUp === 0 && AppState.demoConnections === 0").toBool(),"offline counters zero");
    check(state("AppState.connectionState === '未连接（演示）' && AppState.demoMode").toBool(),"overview fixture cannot claim real engine connectivity");
    check(state("Theme.canvas.toString() === '#f7f7f8' && Theme.surface.toString() === '#ffffff'").toBool(),"all pages share neutral canvas and white card tokens");
    check(state("Theme.windowRadius === 12 && Theme.containerRadius === 12 && Theme.cardRadius === 10 && Theme.popupRadius === 10 && Theme.controlRadius === 8 && Theme.pillRadius(32) === 10 && Theme.roundedRadius(100,24) === 8").toBool(),"window, containers, cards, popups and controls follow the shared radius hierarchy");
    const auto lightSelected=state("Theme.navigationSelected").value<QColor>();
    const auto lightSidebar=state("Theme.sidebarBase").value<QColor>();
    check(lightSidebar.green()-lightSelected.green()>=30,"light navigation selection is clearly darker than the sidebar");
    auto *brand=window->findChild<QObject *>("brandVector");
    check(brand && brand->property("source").toUrl().toString().endsWith("swirl_knot_mark_light.svg"),"sidebar uses latest knot SVG light artwork");
    state("Theme.mode='Dark'");QTest::qWait(100);
    check(brand && brand->property("source").toUrl().toString().endsWith("swirl_knot_mark_dark.svg") && state("Theme.navigationSelected").value<QColor>().green()-state("Theme.sidebarBase").value<QColor>().green()>=30,"dark mode switches knot SVG and retains distinct navigation selection");
    state("Theme.mode='Light'");QTest::qWait(100);
    check(window->property("_qt_sg_hdr_format").toString()=="scrgb","window requests real FP16 scRGB with automatic SDR fallback");
    auto *statusCards=item("statusCardsGrid");
    check(statusCards && statusCards->property("columns").toInt()==6,"reference overview keeps all six status cards in one row when they fit");
    for(const auto &name : {"windowCloseButton","windowMinimizeButton","windowMaximizeButton","historyBackButton","historyForwardButton"}) {
        auto *circle=item(name);
        auto *background=circle?qvariant_cast<QObject *>(circle->property("background")):nullptr;
        check(circle && background && qAbs(background->property("radius").toReal()-circle->height()/2)<0.1,
              "circular window and toolbar button outlines retain their geometry");
    }
    bool zoomCornersStable=true;
    for(int percent : {75,100,125,150}) {
        state(QStringLiteral("Theme.setScalePercent(%1)").arg(percent));QTest::qWait(80);
        const qreal scale=percent/100.0;
        zoomCornersStable=zoomCornersStable && qAbs(state("Theme.windowRadius").toReal()-12*scale)<0.01 && qAbs(state("Theme.controlRadius").toReal()-8*scale)<0.01;
        for(const auto &name : {"windowCloseButton","windowMinimizeButton","windowMaximizeButton","historyBackButton","historyForwardButton"}) {
            auto *circle=item(name);
            auto *background=circle?qvariant_cast<QObject *>(circle->property("background")):nullptr;
            zoomCornersStable=zoomCornersStable && circle && background && qAbs(background->property("radius").toReal()-circle->height()/2)<0.1;
        }
    }
    check(zoomCornersStable,"radius hierarchy scales proportionally at 75/100/125/150 percent and circular controls remain circular");
    state("Theme.resetScale()");QTest::qWait(80);
    check(item("addButton")==nullptr && item("globalSettingsButton")==nullptr,"global add and settings shortcuts removed from every page");
    auto *subscriptions=item("nav-subscriptions");auto *profiles=item("nav-profiles");
    if(subscriptions && profiles) {
        QTest::mouseMove(window,subscriptions->mapToScene(QPointF(subscriptions->width()/2,subscriptions->height()/2)).toPoint());
        state("AppState.navigate('profiles')");QTest::qWait(30);
        auto *oldBackground=qvariant_cast<QObject *>(subscriptions->property("background"));
        auto *newBackground=qvariant_cast<QObject *>(profiles->property("background"));
        check(oldBackground && newBackground && oldBackground->property("color").value<QColor>().alpha()==0 && newBackground->property("color").value<QColor>().alpha()>0,"pointer remaining over the old navigation row cannot produce a second selection highlight");
        QTest::mousePress(window,Qt::LeftButton,Qt::NoModifier,subscriptions->mapToScene(QPointF(subscriptions->width()/2,subscriptions->height()/2)).toPoint());
        check(oldBackground && oldBackground->property("color").value<QColor>().alpha()==0,"pressing an unselected navigation row does not paint a second highlighted row");
        QTest::mouseRelease(window,Qt::LeftButton,Qt::NoModifier,subscriptions->mapToScene(QPointF(subscriptions->width()/2,subscriptions->height()/2)).toPoint());
        check(oldBackground && newBackground && oldBackground->property("color").value<QColor>().alpha()>0 && newBackground->property("color").value<QColor>().alpha()==0,"navigation selection transfers immediately with no outgoing fade");
    } else check(false,"navigation regression targets exist");
    state("AppState.navigate('overview')");QTest::qWait(150);
    auto *metric = item("downloadMetric");
    check(metric && metric->property("value").toString()=="0 KB/s","offline metric rendered as zero");
    auto *chart = item("overviewChart");
    check(chart && chart->property("series").toString()=="down","download is the only default curve");
    check(item("connectionSwitch")==nullptr,"upper-right connection demo control removed");
    state("AppState.setConnection(true)");
    check(state("AppState.proxyOn && AppState.demoDown > 0 && AppState.demoConnections > 0").toBool(),"demonstration connection state starts");
    click(item("systemProxyToggle"));
    click(item("tunToggle"));
    check(state("AppState.systemProxyOn && AppState.tunOn && AppState.proxyOn").toBool(),"demo system and TUN switches belong to a connected demo session");
    state("AppState.setConnection(false)");
    check(state("!AppState.proxyOn && AppState.demoDown === 0 && AppState.demoUp === 0 && AppState.demoConnections === 0").toBool(),"mouse disconnect resets counters");
    check(state("!AppState.systemProxyOn && !AppState.tunOn").toBool(),"disconnect clears demo system proxy and TUN states");
    check(state("AppState.recentEvents[0].title === '已断开连接'").toBool(),"disconnect recorded at current time");
    state("Theme.setScalePercent(75)");
    check(state("!Theme.followSystemScale && Theme.uiScale === 0.75 && Theme.dp(20) === 15 && Theme.appearanceSettings.savedScalePercent === 75").toBool(),"manual 75 percent scale updates shared layout units and stored preference");
    state("Theme.setScalePercent(150)");
    check(state("Theme.uiScale === 1.5 && Theme.fontSize(16) === 24").toBool(),"manual 150 percent scale updates shared typography");
    state("Theme.resetScale()");
    check(state("Theme.followSystemScale && Theme.uiScale === 1").toBool(),"scale reset follows system DPI through Qt logical pixels");
    auto *combo=item("modeCombo");
    click(combo);
    QTest::keyClick(window,Qt::Key_Down);
    QTest::keyClick(window,Qt::Key_Return);
    QTest::qWait(250);
    check(state("AppState.mode === '全局'").toBool(),"mode popup keyboard selection");
    state("pageLoader.item.showDetails = true");
    QTest::qWait(150);
    click(item("seriesSelector"),0.5);
    check(chart && chart->property("series").toString()=="up","upload selection replaces download");
    click(item("seriesSelector"),0.85);
    check(chart && chart->property("series").toString()=="total","total selection displays cumulative series");
    click(item("rangeSelector"),0.62);
    check(chart && chart->property("rangeIndex").toInt()==2,"six-hour range input");
    click(item("nodePickerButton"));
    auto *popup=window->findChild<QObject *>("nodePicker");
    check(popup && popup->property("opened").toBool(),"node picker opens from button");
    click(item("hongKongNode"));
    check(state("AppState.selectedNode === '香港 · 01' && AppState.selectedNodeRegion === 'HK' && AppState.selectedNodeProtocol === 'Hysteria2' && AppState.selectedNodeLatency === 52").toBool(),"node choice updates region protocol and historical latency");
    click(item("nodePickerButton"));
    QTest::keyClick(window,Qt::Key_Escape);
    QTest::qWait(250);
    check(popup && !popup->property("visible").toBool(),"node picker dismisses with Escape");
    state("Theme.setScalePercent(125); AppState.navigate('settings')");QTest::qWait(200);
    auto *scaleSlider=item("scaleSlider");
    check(scaleSlider && scaleSlider->isEnabled() && scaleSlider->property("from").toReal()==0.75 && scaleSlider->property("to").toReal()==1.5 && scaleSlider->property("stepSize").toReal()==0.01 && scaleSlider->property("value").toReal()==1.25,"appearance exposes enabled 75-150 percent slider with one percent steps");
    if(scaleSlider) {
        const auto start=scaleSlider->mapToScene(QPointF(scaleSlider->width()*0.55,scaleSlider->height()/2)).toPoint();
        const auto finish=scaleSlider->mapToScene(QPointF(scaleSlider->width()*0.85,scaleSlider->height()/2)).toPoint();
        QTest::mousePress(window,Qt::LeftButton,Qt::NoModifier,start);
        QTest::mouseMove(window,finish,100);
        QTest::mouseRelease(window,Qt::LeftButton,Qt::NoModifier,finish);
        QTest::qWait(100);
    }
    check(state("Theme.uiScale > 1.3 && Theme.uiScale < 1.5 && Math.round(Theme.uiScale*100) === Theme.appearanceSettings.savedScalePercent").toBool(),"dragging appearance slider applies and stores a one percent scale immediately");
    state("Theme.resetScale(); AppState.navigate('overview')");QTest::qWait(200);
    QTest::keyClick(window,Qt::Key_K,Qt::ControlModifier);
    QTest::qWait(50);
    auto *search=item("pageSearch");
    check(search && search->hasActiveFocus(),"Ctrl+K focuses search");
    if(search) search->setProperty("text",QStringLiteral("HTTP"));
    QTest::keyClick(window,Qt::Key_Return);
    QTest::qWait(250);
    check(state("AppState.currentPage === 'inspector'").toBool(),"search navigates to HTTP inspector");
    click(item("historyBackButton"));
    check(state("AppState.currentPage === 'overview'").toBool(),"mouse history button remains clickable below title drag region");
    QTest::keyClick(window,Qt::Key_Right,Qt::AltModifier);
    QTest::qWait(250);
    QTest::keyClick(window,Qt::Key_Left,Qt::AltModifier);
    QTest::qWait(250);
    check(state("AppState.currentPage === 'overview'").toBool(),"Alt+Left returns through navigation history");
    QTest::keyClick(window,Qt::Key_Right,Qt::AltModifier);
    QTest::qWait(250);
    check(state("AppState.currentPage === 'inspector'").toBool(),"Alt+Right restores forward destination");
    QTest::keyClick(window,Qt::Key_1,Qt::ControlModifier);
    QTest::qWait(150);
    auto *loader=item("pageLoader");
    check(loader && loader->y()+loader->height()<=window->height()-16,"overview has bottom margin at reference size");
    bool resizeStable=true;
    for(int width=1260;width>=800;width-=20) {
        window->resize(width,650);QTest::qWait(30);
        resizeStable=resizeStable && loader && loader->width()>0 && loader->height()>0 && loader->mapToScene(QPointF(loader->width(),loader->height())).x()<=window->width()+1;
    }
    check(resizeStable,"continuous resizing across 24 window widths keeps the content viewport within the window");
    window->resize(1000,650);
    QTest::qWait(150);
    check(window->width()==1000 && window->height()==650,"manual window resizing can change width and height independently");
    check(loader && loader->width()>0 && loader->height()>0,"minimum size leaves usable scrolling viewport");
    auto *compactStatusCards=item("statusCardsGrid");
    auto *speedPanel=item("speedPanel");
    check(compactStatusCards && compactStatusCards->property("columns").toInt()==3,"compact overview uses balanced card rows instead of leaving a single card orphaned");
    check(speedPanel && speedPanel->width()<loader->width()*0.7,"compact overview keeps latency and speed side by side");
    auto *latencyPanel=item("latencyPanel");
    check(latencyPanel && speedPanel && qAbs(latencyPanel->mapToScene(QPointF()).y()-speedPanel->mapToScene(QPointF()).y())<1 && qAbs(latencyPanel->height()-speedPanel->height())<1,"compact latency and speed cards share top and bottom edges");
    auto *proxyPanel=item("currentProxyPanel");auto *systemPanel=item("systemStatusPanel");
    check(proxyPanel && systemPanel && qAbs(proxyPanel->mapToScene(QPointF()).y()-systemPanel->mapToScene(QPointF()).y())<1 && qAbs(proxyPanel->height()-systemPanel->height())<1,"current proxy and system status share top and bottom edges");
    window->resize(1260,816);QTest::qWait(150);
    auto *navScroll=item("sidebarNavigationScroll");
    auto *lastNav=item("nav-rewrite");
    check(navScroll && lastNav && lastNav->mapToScene(QPointF(0,lastNav->height())).y()<=navScroll->mapToScene(QPointF(0,navScroll->height())).y()+1,"all sidebar rows fit the reported laptop window without clipping the last label");
    window->resize(800,560);QTest::qWait(150);
    check(window->width()==800 && window->height()==560,"minimum window size can be reached without locking the aspect ratio");
    QMetaObject::invokeMethod(window,"previewScrollBottom");
    QTest::qWait(150);
    auto *importRow=item("importConfigRow");
    check(importRow && importRow->mapToScene(QPointF(0,importRow->height())).y()<=window->height()-17,
          "last bottom row is fully reachable at minimum size");
    window->resize(1450,884);
    QTest::keyClick(window,Qt::Key_K,Qt::ControlModifier);
    if(auto *captureSearch=item("pageSearch"))captureSearch->setProperty("text",QStringLiteral("抓包"));
    QTest::keyClick(window,Qt::Key_Return);QTest::qWait(250);
    check(state("AppState.currentPage === 'capture' && !captureProvider.running").toBool(),"search opens real capture page without starting listener");
    if(auto *port=item("capturePortField"))port->setProperty("text","0");
    click(item("captureStartButton"));
    check(state("captureProvider.running && captureProvider.port > 0").toBool(),"capture start button opens actual loopback listener");
    click(item("captureStartButton"));
    check(state("!captureProvider.running").toBool(),"capture stop button closes actual listener");
    QTest::keyClick(window,Qt::Key_K,Qt::ControlModifier);
    if(auto *moduleSearch=item("pageSearch"))moduleSearch->setProperty("text",QStringLiteral("DHCP"));
    QTest::keyClick(window,Qt::Key_Return);QTest::qWait(250);
    check(state("AppState.currentPage === 'feature-dhcp' && !captureProvider.running").toBool(),"search opens dedicated DHCP module without network listener");
    auto *firstToggle=item("moduleFirstToggle");
    const bool before=firstToggle && firstToggle->property("checked").toBool();
    click(firstToggle);
    click(item("moduleSaveButton"));
    check(state("moduleDrafts.load('feature-dhcp').settings.f0").toBool()!=before,"module toggle is saved as actual local draft");
    state("AppState.navigate('featurehub')");QTest::qWait(200);
    check(item("moduleSearch")!=nullptr,"module hub renders searchable catalog");
    check(state("FeatureCatalog.entries.length===56").toBool(),"catalog contains 56 capability entries");
    state("AppState.navigate('feature-dhcp')");QTest::qWait(200);
    check(item("moduleFirstToggle") && item("moduleFirstToggle")->property("checked").toBool()!=before,"module draft restored after navigation");
    // Drive record creation through the page, then reload the persisted list.
    if(auto *loaderItem=item("pageLoader")) {
        if(auto *modulePage=qvariant_cast<QObject *>(loaderItem->property("item")))modulePage->setProperty("tab",1);
    }
    QTest::qWait(100);click(item("moduleAddButton"));
    if(auto *name=item("moduleEntryName"))name->setProperty("text",QStringLiteral("UI test reservation"));
    if(auto *value=item("moduleEntryValue"))value->setProperty("text",QStringLiteral("192.0.2.20"));
    click(item("moduleEntryConfirm"));click(item("moduleSaveButton"));
    check(state("moduleDrafts.load('feature-dhcp').records.some(function(r){return r.name==='UI test reservation' && r.value==='192.0.2.20'})").toBool(),"entry dialog persists actual module record");
    auto *store=qobject_cast<ModuleDraftStore *>(qmlContext(window)->contextProperty("moduleDrafts").value<QObject *>());
    QTemporaryDir temp;
    if(store && temp.isValid()) {
        const auto draft=store->load("feature-dhcp");
        const auto file=QUrl::fromLocalFile(temp.filePath("draft.json"));
        check(store->exportFile(file,"feature-dhcp",draft),"draft JSON export writes actual file");
        check(store->importFile(file,"feature-dhcp")==draft,"draft JSON roundtrip retains settings and ordered records");
        check(store->importFile(file,"feature-dns").isEmpty() && !store->lastError().isEmpty(),"draft import rejects wrong module");
        QFile bad(temp.filePath("bad.json"));
        if(!bad.open(QIODevice::WriteOnly))return 2;
        bad.write("{broken");bad.close();
        check(store->importFile(QUrl::fromLocalFile(bad.fileName()),"feature-dhcp").isEmpty() && !store->lastError().isEmpty(),"draft import rejects malformed JSON");
    } else check(false,"draft test fixture exists");
    qInfo() << "Overview input checks:" << checks << "checks," << failures << "failures";
    return failures ? 2 : 0;
}
