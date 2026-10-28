#include "AppearanceChecks.h"
#include <QQuickWindow>
#include <QQuickItem>
#include <QQuickItemGrabResult>
#include <QQmlContext>
#include <QQmlExpression>
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
        // The sidebar samples decoration over the single shared window base.
        // Its opaque accessibility fallback uses that same canvas colour.
        check(pane->metaObject()->indexOfProperty("color")==-1,"sidebar container has no independent fill property");
        QTest::qWait(250);
        auto *glass=find(pane,"sidebarLiquidGlass");
        auto *workspace=qvariant_cast<QQuickItem *>(eval("appSceneBackdrop"));
        auto *source=qvariant_cast<QQuickItem *>(eval("appSceneBackdrop.decorationSource"));
        auto *shader=glass?glass->findChild<QObject *>("sidebarLiquidShader"):nullptr;
        check(glass && source && qvariant_cast<QQuickItem *>(glass->property("backdropSource"))==source,"sidebar glass samples the independent application backdrop");
        check(glass && glass->property("sampled").toBool() && glass->property("captureLive").toBool(),"transparent sidebar uses live sampled material");
        check(shader && shader->property("status").toInt()==0 && shader->property("log").toString().isEmpty(),"production sidebar material shader is compiled without errors");
        const auto capture=[&](QQuickItem *item){
            if(!item)return QImage{};
            auto result=item->grabToImage();if(!result)return QImage{};
            QSignalSpy ready(result.data(),&QQuickItemGrabResult::ready);window->update();
            if(result->image().isNull())ready.wait(2000);
            return result->image();
        };
        const auto interiorMatches=[](const QImage &image,const QColor &expected=QColor()){
            if(image.isNull())return false;
            // Item-local readback excludes navigation labels and avoids any
            // dependency on page layout or window/DPI sample coordinates.
            const QPointF samples[]={{0.25,0.25},{0.75,0.25},{0.5,0.5},{0.25,0.75},{0.75,0.75}};
            for(const auto &sample:samples){
                const auto actual=image.pixelColor(qRound(sample.x()*(image.width()-1)),qRound(sample.y()*(image.height()-1)));
                if(actual.alpha()!=255)return false;
                if(expected.isValid() && (qAbs(actual.red()-expected.red())>2 || qAbs(actual.green()-expected.green())>2 || qAbs(actual.blue()-expected.blue())>2))return false;
            }
            return true;
        };
        const auto matchesToken=[&](QQuickItem *item,const QString &token){
            const auto expected=eval(token).value<QColor>();
            return expected.isValid() && interiorMatches(capture(item),expected);
        };
        const auto darkMaterial=capture(glass);
        const auto transmitsBase=[](const QImage &image){return !image.isNull() && image.pixelColor(image.width()/2,image.height()/4).alpha()<3;};
        check(transmitsBase(darkMaterial),"dark sidebar leaves the shared window base visible");
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
        eval("Theme.mode='Light';Theme.reduceMotion=true");QTest::qWait(350);
        const auto lightMaterial=capture(glass);
        check(glass && glass->property("sampled").toBool() && glass->property("captureLive").toBool() && transmitsBase(lightMaterial),"light sidebar retains live decoration over the shared base");
        check(!darkMaterial.isNull() && !lightMaterial.isNull() && darkMaterial.size()==lightMaterial.size() && darkMaterial!=lightMaterial,"theme selection changes the rendered sidebar material");
        eval("Theme.increaseContrast=true");QTest::qWait(150);
        check(glass && !glass->property("sampled").toBool() && !glass->property("captureLive").toBool(),"increased contrast stops sidebar sampling");
        check(matchesToken(glass,"Theme.canvas"),"increased contrast renders the shared opaque canvas token");
        eval("Theme.increaseContrast=false;Theme.transparency=false");QTest::qWait(150);
        check(glass && !glass->property("sampled").toBool() && !glass->property("captureLive").toBool(),"opaque fallback stops sidebar sampling");
        check(matchesToken(glass,"Theme.canvas"),"opaque sidebar fallback uses the shared canvas token");
        check(matchesToken(workspace,"Theme.canvas"),"opaque workspace uses the same canvas token as the sidebar");
        eval("Theme.transparency=true");QTest::qWait(150);
        check(glass && glass->property("sampled").toBool() && glass->property("captureLive").toBool(),"restoring transparency resumes sidebar sampling");
    }
    auto *proxy=find(window->contentItem(),"proxyCapsule");
    if(proxy){
        // Appearance checks observe the real host but never click its network
        // switch. Motion checks inject a controller into this same control;
        // native setting mutations are tested only on disposable CI runners.
        const bool active=eval("engineController.proxyRequested || engineController.systemProxy.owned || engineController.processAlive").toBool();
        const bool pending=eval("engineController.systemProxyBusy").toBool();
        const bool stopping=eval("engineController.systemProxyStopping").toBool();
        check(proxy->property("proxyEnabled").toBool()==active,"master proxy control reflects Swirl runtime and owned settings");
        const auto action=stopping?QStringLiteral("正在关闭代理…"):pending?QStringLiteral("正在开启代理…"):active?QStringLiteral("关闭代理"):QStringLiteral("开启代理");
        check(proxy->property("label").toString()==action,"master proxy control presents the matching direct action");
    } else check(false,"system proxy switch exists");
    qInfo()<<"APPEARANCE_CHECKS failures"<<failures;return failures?2:0;
}
