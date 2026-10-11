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
        QTest::mouseClick(window,Qt::LeftButton,Qt::NoModifier,
                          target->mapToScene(QPointF(target->width()*fraction,target->height()/2)).toPoint());
        QTest::qWait(250);
    };
    check(state("AppState.demoDown === 0 && AppState.demoUp === 0 && AppState.demoConnections === 0").toBool(),"offline counters zero");
    auto *metric = item("downloadMetric");
    check(metric && metric->property("value").toString()=="0 KB/s","offline metric rendered as zero");
    auto *chart = item("overviewChart");
    check(chart && chart->property("series").toString()=="down","download is the only default curve");
    click(item("connectionSwitch"));
    check(state("AppState.proxyOn && AppState.demoDown > 0 && AppState.demoConnections > 0").toBool(),"mouse starts demonstration connection");
    click(item("connectionSwitch"));
    check(state("!AppState.proxyOn && AppState.demoDown === 0 && AppState.demoUp === 0 && AppState.demoConnections === 0").toBool(),"mouse disconnect resets counters");
    check(state("AppState.recentEvents[0].title === '已断开演示连接'").toBool(),"disconnect recorded at current time");
    auto *combo=item("modeCombo");
    click(combo);
    QTest::keyClick(window,Qt::Key_Down);
    QTest::keyClick(window,Qt::Key_Return);
    QTest::qWait(250);
    check(state("AppState.mode === '全局'").toBool(),"mode popup keyboard selection");
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
    QTest::keyClick(window,Qt::Key_K,Qt::ControlModifier);
    QTest::qWait(50);
    auto *search=item("pageSearch");
    check(search && search->hasActiveFocus(),"Ctrl+K focuses search");
    if(search) search->setProperty("text",QStringLiteral("HTTP"));
    QTest::keyClick(window,Qt::Key_Return);
    QTest::qWait(250);
    check(state("AppState.currentPage === 'inspector'").toBool(),"search navigates to HTTP inspector");
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
    window->resize(1000,650);
    QTest::qWait(150);
    check(loader && loader->width()>0 && loader->height()>0,"minimum size leaves usable scrolling viewport");
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
