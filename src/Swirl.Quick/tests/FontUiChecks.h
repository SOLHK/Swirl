#pragma once
#include "app/FontManager.h"
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
    auto memory=[](){return fontUiPrivateBytes();};
    window->resize(1100,900);window->hide();window->show();QTest::qWait(150);
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
    auto *slider=get("fontAxisSlider_HGHT"),*input=get("fontAxisInput_wdth");
    check(slider&&input,"dynamic slider and numeric controls exist");
    if(slider){slider->setProperty("value",800);check(QMetaObject::invokeMethod(slider,"moved"),"slider moved handler");}
    check(manager->previewValues().value("HGHT").toDouble()==800,"slider edits actual HGHT coordinate");
    if(input){input->setProperty("text","109.75");check(QMetaObject::invokeMethod(input,"editingFinished"),"numeric commit handler");}
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
    const auto lateGrowth=dragMemory.last().toDouble()-dragMemory.at(dragMemory.size()-3).toDouble();
    check(warmMemory<0||lateGrowth<16LL*1024*1024,"repeated identical coordinate set reaches a memory plateau");
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
        {"dragMemoryBytes",dragMemory},{"privateBytesBefore",double(beforeMemory)},{"privateBytesAfterWarmDrag",double(warmMemory)},{"privateBytesAfterRepeatedDrag",double(repeatedMemory)},{"privateBytesAfter",double(memory())},{"frameIntervalsMs",frameIntervals},{"pages",pageAudits},
        {"captureKind","raw QQuickWindow render; not physical-screen or remote-compression evidence"}}).toJson());
    return failures?2:0;
}
