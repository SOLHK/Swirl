#pragma once
#include "app/FontManager.h"
#include "FontTestViewport.h"
#include <QQuickWindow>
#include <QQuickItem>
#include <QQmlExpression>
#include <QQmlContext>
#include <QTest>
#include <QPointer>
#include <QJsonDocument>
#include <QJsonObject>
#include <QJsonArray>
#include <QFile>
#include <QDir>
#include <QElapsedTimer>
#include <QFont>
#include <functional>
#ifdef Q_OS_WIN
#include <windows.h>
#include <psapi.h>
#endif

inline qint64 fontUiPrivateBytes(){
#ifdef Q_OS_WIN
        PROCESS_MEMORY_COUNTERS_EX counters{};
        if(K32GetProcessMemoryInfo(GetCurrentProcess(),reinterpret_cast<PROCESS_MEMORY_COUNTERS *>(&counters),sizeof(counters)))return counters.PrivateUsage;
#endif
        return -1;
}


// Runs only in the existing isolated preview process; never controls another app.
inline int runFontUiChecks(QQuickWindow *window,FontManager *manager,const QString &output)
{
    if(!window||output.isEmpty()||manager->previewAxes().isEmpty())return 3;
    QDir().mkpath(output);QJsonArray checks;int failures=0;
    auto check=[&](bool ok,const QString &name){checks.append(QJsonObject{{"name",name},{"pass",ok}});if(!ok){++failures;qCritical()<<name;}else qInfo()<<"PASS"<<name;};
    auto eval=[&](const QString &code){QQmlExpression expression(qmlContext(window),window,code);const auto result=expression.evaluate();check(!expression.hasError(),"QML expression: "+code);return result;};
    std::function<QQuickItem *(QQuickItem *,const QString &)> find=[&](QQuickItem *item,const QString &name)->QQuickItem *{
        if(item->objectName()==name)return item;for(auto *child:item->childItems())if(auto *found=find(child,name))return found;return nullptr;};
    auto get=[&](const QString &name){return find(window->contentItem(),name);};
    auto capture=[&](const QString &name){const auto image=window->grabWindow();check(!image.isNull()&&image.save(output+"/"+name+".png"),"raw Qt render: "+name);};
    bool memorySamplesValid=true;
    auto memory=[&](){const auto value=fontUiPrivateBytes();if(value<0)memorySamplesValid=false;return value;};
#ifdef Q_OS_WIN
    constexpr bool requirePrivateBytes=true;
#else
    constexpr bool requirePrivateBytes=false;
#endif
    const QSize requestedViewport(1100,900);
    window->hide();
    if(!prepareFontTestViewport(window,requestedViewport,output+"/font-ui-setup-failure.json"))return 3;
    QTest::qWait(150);
    const auto viewport=fontTestViewportReport(window,requestedViewport);
    eval("AppState.navigate('settings')");QTest::qWait(350);
    auto *loader=window->findChild<QObject *>("pageLoader");
    // Wait for the existing asynchronous page host to finish its navigation.
    QElapsedTimer ready;ready.start();
    while(loader&&ready.elapsed()<8000){
        auto *candidate=qvariant_cast<QObject *>(loader->property("item"));
        if(candidate&&candidate->metaObject()->indexOfProperty("section")>=0&&!loader->property("pendingGrab").toBool()&&!loader->property("moving").toBool())break;
        QTest::qWait(20);
    }
    QPointer<QObject> page=loader?qvariant_cast<QObject *>(loader->property("item")):nullptr;
    check(page,"settings page exists");if(!page)return 2;
    page->setProperty("section",QStringLiteral("字体"));QTest::qWait(200);
    auto *manual=get("fontManualMode");
    check(manual,"manual font mode control exists");
    if(manual){manual->setProperty("checked",true);check(QMetaObject::invokeMethod(manual,"toggled"),"enable explicit manual font mode");}
    check(!manager->previewAutomatic(),"advanced axis controls use manual preview mode");
    QTest::qWait(50);
    auto *slider=get("fontAxisSlider_HGHT"),*input=get("fontAxisInput_wdth");
    check(slider&&input,"dynamic slider and numeric controls exist");
    if(slider){slider->setProperty("value",800);check(QMetaObject::invokeMethod(slider,"moved"),"slider moved handler");}
    check(manager->previewValues().value("HGHT").toDouble()==800,"slider edits actual HGHT coordinate");
    if(input){
        input->forceActiveFocus();
        check(input->hasActiveFocus(),"numeric editor gains focus before a user edit");
        input->setProperty("text","109.75");
        check(QMetaObject::invokeMethod(input,"textEdited"),"numeric editor receives an explicit user edit");
        check(QMetaObject::invokeMethod(input,"editingFinished"),"numeric commit handler");
    }
    check(manager->previewValues().value("wdth").toDouble()==109.75,"numeric editor accepts fractional axis values");
    const auto originalApplied=manager->variableAxesFor(manager->currentFamily(),400);
    const auto beforeMemory=memory();QElapsedTimer updates;updates.start();QJsonArray frameIntervals;QElapsedTimer frameTimer;frameTimer.start();
    auto connection=QObject::connect(window,&QQuickWindow::frameSwapped,window,[&]{frameIntervals.append(double(frameTimer.nsecsElapsed())/1000000.0);frameTimer.restart();});
    for(int i=0;i<180;++i){manager->setPreviewAxis("HGHT",1+(i*37)%1000);QTest::qWait(2);}
    const auto updateMs=updates.elapsed();QTest::qWait(100);QObject::disconnect(connection);
    const auto warmMemory=memory();
    QJsonArray dragMemory{double(warmMemory)};
    for(int pass=0;pass<7;++pass){
        for(int i=0;i<180;++i){manager->setPreviewAxis("HGHT",1+(i*37)%1000);QTest::qWait(2);}
        dragMemory.append(double(memory()));
    }
    const auto repeatedMemory=memory();
    // A finite sequence of NEW fractional triples, separate from repeated-coordinate warmup.
    QJsonArray distinctMemory;int distinctCount=0;bool distinctBudgetExceeded=false;
    QElapsedTimer distinctTimer;distinctTimer.start();
    for(int block=0;block<16;++block){
        for(int j=0;j<64;++j){
            const int i=block*64+j;
            manager->setPreviewAxis("HGHT",1.125+i*998.5/1024.0);
            manager->setPreviewAxis("wght",100.125+((i*617)%1024)*799.5/1024.0);
            manager->setPreviewAxis("wdth",80.0125+((i*389)%1024)*39.95/1024.0);
            ++distinctCount;QTest::qWait(12);
        }
        distinctMemory.append(QJsonObject{{"coordinates",distinctCount},{"privateBytes",double(memory())},{"elapsedMs",double(distinctTimer.elapsed())}});
        if(memory()>1024LL*1024*1024){distinctBudgetExceeded=true;break;}
    }
    const auto distinctEndMemory=memory();
    manager->resetPreviewAxes();QTest::qWait(3000);const auto distinctIdleMemory=memory();
    // On Windows, a failed process-memory query must not silently pass either
    // memory gate. Unsupported platforms retain an explicit unmeasured status.
    check((!requirePrivateBytes||memorySamplesValid)&&!distinctBudgetExceeded,"finite new-coordinate stress stays below 1 GiB private bytes");
    // Later assertions deliberately keep the same confirmed fixture as the earlier test.
    manager->setPreviewAxis("wdth",109.75);

    const auto lateGrowth=dragMemory.last().toDouble()-dragMemory.at(dragMemory.size()-3).toDouble();
    check((!requirePrivateBytes||memorySamplesValid)&&(warmMemory<0||lateGrowth<16LL*1024*1024),"repeated identical coordinate set reaches a memory plateau");
    check(page&&qvariant_cast<QObject *>(loader->property("item"))==page,"axis updates retain the settings page instance");
    check(manager->variableAxesFor(manager->currentFamily(),400)==originalApplied,"drag preview leaves active UI unchanged until Apply");
    manager->setPreviewAxis("HGHT",800);manager->setPreviewAxis("wght",575);
    auto *apply=get("fontApply");check(apply&&QMetaObject::invokeMethod(apply,"clicked"),"apply button handler");QTest::qWait(100);
    check(manager->variableAxesFor(manager->currentFamily(),400).value("HGHT").toInt()==800,"confirmed HGHT propagates globally");
    for(const auto &tag:QStringList{"wght","wdth","HGHT"}){
        auto *field=get("fontAxisInput_"+tag);
        check(field&&field->property("font").value<QFont>().variableAxisValue(QFont::Tag("HGHT"))==800,"input control live font: "+tag);
    }
    capture("settings-top");
    // Scroll only this app's settings Flickable; do not alter Windows scaling.
    std::function<void(QQuickItem *)> scroll=[&](QQuickItem *item){
        if(!item)return;
        if(item->property("contentHeight").isValid()&&item->property("contentY").isValid()&&item->height()>300)
            item->setProperty("contentY",qMax(0.,item->property("contentHeight").toDouble()-item->height()));
        for(auto *child:item->childItems())scroll(child);
    };
    scroll(qobject_cast<QQuickItem *>(page.data()));QTest::qWait(100);capture("settings-bottom");
    auto *license=get("fontLicense");
    check(license&&QMetaObject::invokeMethod(license,"clicked"),"font license dialog opens");QTest::qWait(350);
    int popupText=0,popupWrong=0;QJsonArray popupCaptures;
    auto *dialog=window->findChild<QObject *>("fontLicenseDialog");
    check(dialog&&dialog->property("visible").toBool(),"license popup is visible in its owner overlay");
    if(dialog){
        std::function<void(QQuickItem *)> inspect=[&](QQuickItem *item){
            if(!item)return;
            if(item->isVisible()&&(item->inherits("QQuickText")||item->inherits("QQuickTextEdit"))&&!item->property("text").toString().isEmpty()){
                const auto font=item->property("font").value<QFont>();
                if(font.family()==manager->currentFamily()){++popupText;if(font.variableAxisValue(QFont::Tag("HGHT"))!=800)++popupWrong;}
            }
            for(auto *child:item->childItems())inspect(child);
        };
        inspect(qvariant_cast<QQuickItem *>(dialog->property("contentItem")));
        inspect(qvariant_cast<QQuickItem *>(dialog->property("header")));
        capture("font-license-dialog");popupCaptures.append("font-license-dialog.png");
        QMetaObject::invokeMethod(dialog,"close");
    }
    check(popupText>0&&popupWrong==0,"dialog text inherits confirmed axes");
    QTest::qWait(150);
    QJsonArray pageAudits;
    for(const auto &route:QStringList{"overview","proxies","capture","settings"}){
        eval(QString("AppState.navigate('%1')").arg(route));QTest::qWait(300);
        if(route=="settings")continue;
        int checked=0,wrong=0;
        std::function<void(QQuickItem *)> audit=[&](QQuickItem *item){
            if(item->isVisible()&&(item->inherits("QQuickText")||item->inherits("QQuickTextInput")||item->inherits("QQuickTextEdit"))&&!item->property("text").toString().isEmpty()){
                const auto font=item->property("font").value<QFont>();
                if(font.family()==manager->currentFamily()){++checked;if(font.variableAxisValue(QFont::Tag("HGHT"))!=800||font.variableAxisValue(QFont::Tag("wdth"))!=109.75)++wrong;}
            }
            for(auto *child:item->childItems())audit(child);
        };
        audit(window->contentItem());check(checked>0&&wrong==0,route+" live text axis bindings");
        pageAudits.append(QJsonObject{{"page",route},{"textItems",checked},{"wrongAxes",wrong}});capture(route);
    }
    QFile report(output+"/font-ui-report.json");if(report.open(QIODevice::WriteOnly))report.write(QJsonDocument(QJsonObject{
        {"privateBytesBeforeManager",QCoreApplication::instance()->property("fontBeforeManagerBytes").toDouble()},{"privateBytesAfterBundledFonts",QCoreApplication::instance()->property("fontAfterManagerBytes").toDouble()},{"privateBytesAfterPrivateFont",QCoreApplication::instance()->property("fontAfterImportBytes").toDouble()},{"dialogTextItems",popupText},{"dialogCaptures",popupCaptures},{"checks",checks},{"failures",failures},{"dpr",window->devicePixelRatio()},{"updateCount",180},{"updateLoopMs",double(updateMs)},
        {"distinctCoordinates",distinctCount},{"distinctMemoryBytes",distinctMemory},{"distinctBudgetExceeded",distinctBudgetExceeded},{"privateBytesAfterDistinct",double(distinctEndMemory)},{"privateBytesAfterDistinctResetAndIdle",double(distinctIdleMemory)},{"distinctIdleMs",3000},{"dragMemoryBytes",dragMemory},{"privateBytesBefore",double(beforeMemory)},{"privateBytesAfterWarmDrag",double(warmMemory)},{"privateBytesAfterRepeatedDrag",double(repeatedMemory)},{"privateBytesAfter",double(memory())},{"frameIntervalsMs",frameIntervals},{"pages",pageAudits},
        {"privateBytesMeasurementStatus",memorySamplesValid?"measured":"unavailable"},{"privateBytesRequired",requirePrivateBytes},{"viewport",viewport},{"captureKind","raw QQuickWindow render; not physical-screen or remote-compression evidence"}}).toJson());
    return failures?2:0;
}
