#include <QQuickWindow>
#include <QQuickItem>
#include <QQmlContext>
#include <QQmlExpression>
#include <QTest>
#include <QDir>
#include <QFile>
#include <QJsonDocument>
#include <QJsonArray>
#include <QJsonObject>
#include <QScreen>
#include <QMap>
#include <algorithm>
#include <functional>

int runLiquidGlassChecks(QQuickWindow *window, const QString &directory)
{
    QDir().mkpath(directory);
    QJsonArray checks, captures;
    int failures = 0;
    auto check = [&](const QString &name, bool passed) {
        checks.append(QJsonObject{{"name", name}, {"passed", passed}});
        if (!passed) ++failures;
    };
    auto eval = [&](const QString &code) {
        QQmlExpression expression(qmlContext(window), window, code);
        const auto result = expression.evaluate();
        if (expression.hasError()) check(expression.error().toString(), false);
        return result;
    };
    std::function<QQuickItem *(QQuickItem *, const QString &)> find;
    find = [&](QQuickItem *item, const QString &name) -> QQuickItem * {
        if (item->objectName() == name) return item;
        for (auto child : item->childItems()) if (auto match = find(child, name)) return match;
        return nullptr;
    };
    auto button = [&](const QString &name) { return find(window->contentItem(), name); };
    auto click = [&](const QString &name) {
        auto item = button(name);
        check(name + " exists", item && item->isVisible());
        if (item) QTest::mouseClick(window, Qt::LeftButton, Qt::NoModifier,
                                   item->mapToScene(QPointF(item->width()/2, item->height()/2)).toPoint());
        QTest::qWait(180);
    };
    window->showNormal();
    window->resize(914, 672);
    window->requestActivate();
    eval("Theme.reduceMotion=true;Theme.transparency=true");
    QStringList routes{"activity", "settings"};
    if (qEnvironmentVariableIsSet("SWIRL_GLASS_ALL_PAGES")) {
        const auto ids = QJsonDocument::fromJson(eval("JSON.stringify(AppState.allPageIds.concat(['activity','fonts']))").toString().toUtf8()).array();
        for (const auto id : ids) if (id.toString() != "external") routes.append(id.toString());
        routes.removeDuplicates();
    }
    QMap<QString,QRectF> lightCards;
    for (const auto theme : {QString("Light"), QString("Dark")}) {
        eval("Theme.mode='" + theme + "'");
        for (const auto &route : routes) {
            eval("AppState.navigate('" + route + "')");
            const bool ready=QTest::qWaitFor([&]{return eval("pageLoader.activeLoader && pageLoader.activeLoader.routeId===pageLoader.routeKey && pageLoader.item!==null && !pageLoader.pendingGrab && !pageLoader.moving").toBool();},5000);
            check(theme + "/" + route + " loaded",ready);
            window->update();QTest::qWait(350);
            const auto shot = window->grabWindow();
            const auto file = theme.toLower() + "-" + route + ".png";
            check(file + " rendered", !shot.isNull() && shot.save(directory + "/" + file));
            captures.append(QJsonObject{{"file",file},{"dpr",window->devicePixelRatio()},
                {"width",shot.width()},{"height",shot.height()}});
            if (route == "activity") {
                // The accepted five-card layout replaces the historical two
                // fixed-height cards. Keep every actual surface and its layout
                // invariant across themes, including the compact reading order.
                const QStringList names{"activityStatusCard","activityTrafficCard","activitySourcesCard","activityDiagnosticCard","activityConnectionsCard"};
                QList<QQuickItem *> cards;
                for(const auto &name:names){
                    auto *card=button(name);cards.append(card);
                    check(name+" retains a readable opaque surface",card && card->width()>=240 && card->height()>=130
                        &&card->property("color").value<QColor>().alpha()==255);
                    if(!card)continue;
                    const auto bounds=card->mapRectToScene(card->boundingRect());
                    if(theme=="Light")lightCards.insert(name,bounds);
                    else check(name+" preserves position and size across themes",lightCards.contains(name)&&bounds==lightCards.value(name));
                }
                if(std::all_of(cards.cbegin(),cards.cend(),[](auto *card){return card!=nullptr;})){
                    auto *page=button("activityPage");
                    check("live activity layout remains present",page!=nullptr);
                    const bool wide=page&&page->property("wide").toBool();
                    const auto bounds=[&](int i){return cards[i]->mapRectToScene(cards[i]->boundingRect());};
                    if(wide){
                        check("five-card paired rows retain their proportions",qAbs(bounds(0).top()-bounds(1).top())<1
                            &&qAbs(cards[0]->height()-cards[1]->height())<1
                            &&qAbs(bounds(2).top()-bounds(3).top())<1&&qAbs(bounds(2).bottom()-bounds(4).bottom())<1
                            &&qAbs(cards[0]->width()/(cards[0]->width()+cards[1]->width())-5.0/12)<0.03
                            &&qAbs(cards[2]->width()/(cards[2]->width()+cards[3]->width())-7.0/12)<0.03);
                    }else{
                        bool ordered=true;
                        for(int i=1;i<cards.size();++i)ordered=ordered&&bounds(i).top()>bounds(i-1).bottom()
                            &&qAbs(bounds(i).left()-bounds(i-1).left())<1&&qAbs(cards[i]->width()-cards[i-1]->width())<1;
                        check("compact appearance keeps all five readable cards in order",ordered);
                    }
                }
                const auto controls = button("windowControls");
                const auto tun = button("tunCapsule");
                check("caption and TUN hit regions do not overlap", controls && tun &&
                    tun->mapToScene(QPointF(tun->width(),0)).x() <= controls->mapToScene(QPointF()).x());
            }
        }
    }
    eval("AppState.navigate('activity');Theme.increaseContrast=true;Theme.transparency=false");
    QTest::qWait(180);
    check("contrast disables translucent glass",eval("Theme.glassFill.a===1").toBool());
    check("reduced motion removes decorative duration",eval("SwirlMotion.pageDuration===0 && SwirlMotion.pressScale===1").toBool());
    check("accessible appearance capture",window->grabWindow().save(directory+"/reduced-transparency-contrast.png"));
    eval("Theme.increaseContrast=false;Theme.transparency=true;Theme.reduceMotion=false");
    for (int i=0;i<12;++i) { eval(i%2 ? "AppState.navigate('activity')" : "AppState.navigate('overview')"); QTest::qWait(30); }
    check("rapid navigation settles on final route",QTest::qWaitFor([&]{return eval("AppState.currentPage==='activity' && pageLoader.activeLoader.routeId==='activity' && !pageLoader.pendingGrab && !SwirlMotion.busy").toBool();},5000));
    click("windowMaximizeButton");
    check("maximize uses Windows work area",window->visibility()==QWindow::Maximized && window->geometry()==window->screen()->availableGeometry());
    click("windowMaximizeButton");
    check("restore preserves normal size",window->visibility()==QWindow::Windowed && window->size()==QSize(914,672));
    click("windowMinimizeButton");
    check("minimize",window->visibility()==QWindow::Minimized);
    window->showNormal();window->requestActivate();QTest::qWait(180);
    auto title = button("titleDragArea");
    if (title) {
        QTest::mouseDClick(window,Qt::LeftButton,Qt::NoModifier,QPoint(100,20));QTest::qWait(180);
        check("title double click maximizes",window->visibility()==QWindow::Maximized);
        window->showNormal();
    } else check("title drag area",false);
    QFile report(directory+"/report.json");
    if (!report.open(QIODevice::WriteOnly)) return 3;
    report.write(QJsonDocument(QJsonObject{{"checks",checks},{"captures",captures},{"failures",failures},
        {"dpr",window->devicePixelRatio()},{"graphicsApi",int(window->rendererInterface()->graphicsApi())},
        {"note","Qt render captures on Windows; per-process DPR override, not a change to system display settings. Screenshots require visual review."}}).toJson());
    return failures ? 2 : 0;
}
