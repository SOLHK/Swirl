#pragma once
static int runSixAChecks(QQuickWindow *window,const QString &output) {
    QJsonArray checks;int failures=0;
    const auto directory=QFileInfo(output).absolutePath();QDir().mkpath(directory);
    auto check=[&](const QString &name,bool ok){checks.append(QJsonObject{{"name",name},{"passed",ok}});if(!ok)++failures;qInfo()<<"6A"<<name<<ok;};
    auto eval=[&](QObject *object,const QString &code){QQmlExpression e(qmlContext(object),object,code);auto value=e.evaluate();if(e.hasError()){++failures;qWarning()<<e.error();}return value;};
    auto wait=[](int ms){QEventLoop loop;QTimer::singleShot(ms,&loop,&QEventLoop::quit);loop.exec();};
    std::function<QQuickItem *(QQuickItem *,const QString &)> find=[&](QQuickItem *item,const QString &name)->QQuickItem *{if(item->objectName()==name)return item;for(auto *child:item->childItems())if(auto *found=find(child,name))return found;return nullptr;};
    auto click=[&](QQuickItem *item,QPointF local){if(!item)return;QTest::mouseClick(window,Qt::LeftButton,Qt::NoModifier,item->mapToScene(local).toPoint());};
    auto page=[&]{return qvariant_cast<QQuickItem *>(eval(window,"pageLoader.item"));};
    auto shot=[&](QString name){window->grabWindow().save(directory+"/"+name+".png");};
    window->resize(1100,760);window->show();window->requestActivate();
    eval(window,"Theme.mode='Light';Theme.reduceMotion=false;AppState.navigate('activity')");wait(500);
    auto *metric=find(window->contentItem(),"activityMetricHit_uploadRate");
    check("whole-metric-hit-region",metric&&metric->width()>100&&metric->height()>60);
    if(metric){click(metric,{metric->width()/2,metric->height()/2});wait(55);check("metric-card-surface-transition",eval(window,"pageLoader.heroData!==null && pageLoader.moving").toBool());wait(450);check("metric-navigates-to-traffic",eval(window,"AppState.currentPage==='traffic'").toBool());shot("traffic");}
    eval(window,"AppState.navigate('activity')");wait(450);
    auto *cumulative=find(window->contentItem(),"activityMetricHit_totalTraffic");
    if(cumulative){click(cumulative,{cumulative->width()*0.7,cumulative->height()+20});wait(100);check("metric-period-control-does-not-navigate",eval(window,"AppState.currentPage==='activity'").toBool());}
    auto *controller=qobject_cast<EngineController *>(qmlEngine(window)->rootContext()->contextProperty("engineController").value<QObject *>());
    for(int i=0;i<35;++i)controller->saveNode({{"name",QString("Fixture node %1 — long readable name").arg(i,2,10,QChar('0'))},{"protocol","socks5"},{"host","127.0.0.1"},{"port",1}});
    eval(window,"AppState.navigate('proxies')");wait(450);
    auto *nodes=page();auto *table=find(window->contentItem(),"realNodeTable");auto *hero=find(window->contentItem(),"nodeHero");
    check("node-list-and-motion-controller",nodes&&table&&hero);
    if(nodes&&table&&hero){
        click(table,{table->width()*0.35,table->property("headerHeight").toReal()+22});wait(450);
        check("node-open-dual-card-layout",hero->property("phase")=="Open"&&find(window->contentItem(),"nodeIdentitySurface")->isVisible());shot("nodes-open");
        const qreal listWidth=table->width();
        for(const double fraction:{0.25,0.5,0.75}){
            QMetaObject::invokeMethod(hero,"returnTo",Q_ARG(QVariant,table->property("selectedItem")));wait(450);
            QMetaObject::invokeMethod(hero,"start",Q_ARG(QVariant,table->property("selectedItem")));
            QElapsedTimer timeout;timeout.start();while(hero->property("progress").toReal()<fraction&&timeout.elapsed()<350)wait(3);
            check("node-sampled-during-opening",hero->property("phase")=="Opening"&&hero->property("progress").toReal()<1);
            const qreal x=hero->property("cardX").toReal(),y=hero->property("cardY").toReal();
            QMetaObject::invokeMethod(hero,"returnTo",Q_ARG(QVariant,table->property("selectedItem")));
            check(QString("node-reverse-continuity-%1").arg(fraction),qAbs(hero->property("cardX").toReal()-x)<1.5&&qAbs(hero->property("cardY").toReal()-y)<1.5);
            wait(450);check("node-close-restores-list-width",qAbs(table->width()-listWidth)<1);
        }
        QMetaObject::invokeMethod(hero,"start",Q_ARG(QVariant,table->property("selectedItem")));wait(60);
        click(table,{table->width()*0.3,table->property("headerHeight").toReal()+66});wait(60);
        window->resize(1000,720);wait(450);check("node-retarget-resize-settles",hero->property("phase")=="Open");
        // Capture motion separately from the performance benchmark.
        QJsonArray timestamps;QElapsedTimer clock;clock.start();
        for(int frame=0;frame<80;++frame){
            if(frame==0||frame==45)QMetaObject::invokeMethod(hero,"returnTo",Q_ARG(QVariant,table->property("selectedItem")));
            if(frame==20||frame==52)QMetaObject::invokeMethod(hero,"start",Q_ARG(QVariant,table->property("selectedItem")));
            wait(16);timestamps.append(double(clock.nsecsElapsed())/1e9);
            window->grabWindow().save(directory+QString("/node-frame-%1.png").arg(frame,3,10,QChar('0')));
        }
        QFile times(directory+"/node-timestamps.json");if(times.open(QIODevice::WriteOnly))times.write(QJsonDocument(timestamps).toJson());
    }
    eval(window,"AppState.navigate('processes')");wait(450);
    auto *processPage=page();
    if(processPage){
        auto *dialog=processPage->findChild<QObject *>("meteredDialog");
        check("metered-dialog-found",dialog!=nullptr);
        if(dialog){QMetaObject::invokeMethod(dialog,"open");wait(350);
            auto *editor=find(window->contentItem(),"meteredAllowlistEditor");
            auto *body=dialog->property("contentItem").value<QQuickItem *>();
            auto *footer=dialog->property("footer").value<QQuickItem *>();
            check("metered-editor-visible",editor&&editor->isVisible());
            check("metered-dialog-wraps-body",editor&&dialog->property("height").toReal()>editor->height()+100&&footer&&footer->height()>40&&body&&body->height()>0);
            shot("metered-dialog");QMetaObject::invokeMethod(dialog,"close");wait(250);
        }
    }
    auto *yellow=find(window->contentItem(),"windowMinimizeButton");
    if(yellow){click(yellow,{yellow->width()/2,yellow->height()/2});wait(100);window->showNormal();window->requestActivate();wait(150);check("yellow-mouse-focus-has-no-ring",!yellow->property("visualFocus").toBool());}
    eval(window,"Theme.reduceMotion=true;AppState.navigate('proxies')");wait(80);
    if(hero&&table){QMetaObject::invokeMethod(hero,"start",Q_ARG(QVariant,table->property("selectedItem")));check("node-reduced-motion-no-flight",!hero->property("moving").toBool());}
    QFile report(output);if(report.open(QIODevice::WriteOnly))report.write(QJsonDocument(QJsonObject{{"checks",checks},{"failures",failures},{"scope","isolated fixture nodes; no system proxy, TUN, UAC or user credentials"}}).toJson());
    return failures?1:0;
}
