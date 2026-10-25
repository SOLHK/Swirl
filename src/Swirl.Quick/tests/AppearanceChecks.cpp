#include "AppearanceChecks.h"
#include <QQuickWindow>
#include <QQuickItem>
#include <QQmlContext>
#include <QQmlExpression>
#include <QTest>
#include <QSettings>
#include <QProcess>
#include <QCoreApplication>
#include <QGuiApplication>
#include <QImage>
#include <QColor>
#include <QQmlComponent>
#include <QQmlEngine>
#include <functional>

int runAppearanceChecks(QQuickWindow *window,bool restoreOnly) {
    if(!window)return 2;
    int failures=0;
    auto check=[&](bool ok,const char *name){qInfo()<<(ok?"PASS":"FAIL")<<name;if(!ok)++failures;};
    auto eval=[&](const QString &code){QQmlExpression e(qmlContext(window),window,code);auto value=e.evaluate();check(!e.hasError(),"appearance expression is valid");return value;};
    if(restoreOnly){check(eval("Theme.mode==='Dark' && Theme.dark && Theme.followSystemMotion").toBool(),"new process restores saved dark theme and explicit system-motion preference");return failures?2:0;}
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
    check(eval("!scaledCanvas.layer.enabled").toBool(),"text canvas is not a resampled window texture");
    eval("Theme.followSystemMotion=true;Theme.appearanceSettings.sync()");QTest::qWait(250);
    QSettings settings;check(QTest::qWaitFor([&]{settings.sync();return settings.value("Appearance/savedMode").toString()=="Dark"&&settings.value("Appearance/savedFollowSystemMotion").toBool();},3000),"chosen theme and motion preference are persisted");
    QProcess child;child.start(QCoreApplication::applicationFilePath(),{"--appearance-restore-test","--preview-preserve-settings"});
    check(child.waitForFinished(15000)&&child.exitStatus()==QProcess::NormalExit&&child.exitCode()==0,"fresh application process confirms theme restoration");
    window->requestActivate();
    eval("Theme.transparency=true;Theme.increaseContrast=false;AppState.navigate('activity')");
    check(QTest::qWaitFor([&]{return eval("pageLoader.activeLoader.routeId==='activity' && !pageLoader.pendingGrab && !pageLoader.moving").toBool();},3500),"activity route settles");
    auto *pane=find(window->contentItem(),"sidebarFloatingBackground");
    check(pane!=nullptr,"sidebar pane exists");
    if(pane){
        // The sidebar container remains an Item with shader children. V2's
        // background fill is owned by its shared exact contour shape.
        // Require that structural contract as well as the pixel checks below.
        check(pane->metaObject()->indexOfProperty("color")==-1,"sidebar container has no independent fill property");
        QTest::qWait(250);
        const auto at=pane->mapToScene(QPointF(pane->width()-18,pane->height()/2))*window->devicePixelRatio();
        const auto before=window->grabWindow();
        const auto expected=eval("Theme.sidebarBase").value<QColor>();
        const auto actual=before.isNull()?QColor():before.pixelColor(at.toPoint());
        check(actual.isValid() && qAbs(actual.red()-expected.red())<=3 && qAbs(actual.green()-expected.green())<=3 && qAbs(actual.blue()-expected.blue())<=3,"sidebar interior uses its darker neutral material token");
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
        auto *transmission=find(window->contentItem(),"sidebarTransmission");
        check(transmission!=nullptr,"sidebar interior material exists");
        if(transmission){
            check(!transmission->isVisible(),"dark sidebar remains unchanged");
            eval("Theme.mode='Light';Theme.reduceMotion=true");QTest::qWait(350);
            check(transmission->isVisible(),"light sidebar uses the interior material");
            const auto material=window->grabWindow();
            transmission->setOpacity(0);QTest::qWait(150);
            const auto clear=window->grabWindow();
            const auto dpr=window->devicePixelRatio();
            const auto topLeft=pane->mapToScene(QPointF(0,0))*dpr;
            const QRectF bounds(topLeft,QSizeF(pane->width()*dpr,pane->height()*dpr));
            const auto area=bounds.adjusted(-6*dpr,-6*dpr,24*dpr,6*dpr).toAlignedRect().intersected(material.rect());
            const auto interior=bounds.adjusted(6*dpr,6*dpr,-6*dpr,-6*dpr);
            int changed=0,outside=0,maxDelta=0;
            if(!material.isNull() && material.size()==clear.size()){
                for(int y=area.top();y<=area.bottom();++y)for(int x=area.left();x<=area.right();++x){
                    const auto a=material.pixelColor(x,y),b=clear.pixelColor(x,y);
                    if(a==b)continue;
                    ++changed;
                    if(!interior.contains(QPointF(x+0.5,y+0.5)))++outside;
                    maxDelta=qMax(maxDelta,qMax(qAbs(a.red()-b.red()),qMax(qAbs(a.green()-b.green()),qAbs(a.blue()-b.blue()))));
                }
            }
            check(changed>0 && maxDelta<=7,"interior adjustment is visible but limited to seven RGB levels");
            check(outside==0,"contour and exterior shadow pixels remain identical");
            transmission->setOpacity(1);
            eval("Theme.increaseContrast=true");check(!transmission->isVisible(),"increased contrast bypasses interior material");
            eval("Theme.increaseContrast=false;Theme.transparency=false");check(!transmission->isVisible(),"reduced transparency bypasses interior material");
            eval("Theme.transparency=true");
        }
    }
    auto *proxy=find(window->contentItem(),"proxyCapsule");
    if(proxy){
        // Appearance checks observe the real host but never click its network
        // switch. Motion checks inject a controller into this same control;
        // native setting mutations are tested only on disposable CI runners.
        const bool active=eval("engineController.systemProxy.systemEnabled").toBool();
        const bool pending=eval("engineController.systemProxyBusy").toBool();
        check(proxy->property("proxyEnabled").toBool()==active,"proxy control reflects actual host observation");
        const auto action=pending?QStringLiteral("正在设置系统代理…"):active?QStringLiteral("关闭系统代理"):QStringLiteral("开启系统代理");
        check(proxy->property("label").toString()==action,"proxy control presents the matching direct action");
    } else check(false,"system proxy switch exists");
    qInfo()<<"APPEARANCE_CHECKS failures"<<failures;return failures?2:0;
}
