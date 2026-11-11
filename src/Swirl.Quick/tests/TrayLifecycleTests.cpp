#include "app/ShutdownCoordinator.h"
#include "app/SingleInstance.h"
#include "app/TrayController.h"
#include <QApplication>
#include <QFile>
#include <QJsonArray>
#include <QJsonDocument>
#include <QJsonObject>
#include <QPixmap>
#include <QProcess>
#include <QTimer>
#include <QUuid>
#include <memory>

int main(int argc,char **argv){
    if(argc==3&&QByteArray(argv[1])=="--activate"){
        QCoreApplication app(argc,argv);SingleInstance instance;
        return instance.acquire(QString::fromLocal8Bit(argv[2]))==SingleInstance::Activated?0:10;
    }
    QApplication app(argc,argv);app.setQuitOnLastWindowClosed(false);
    app.setApplicationName("Swirl tray lifecycle fixture");
    QQuickWindow mainWindow,secondary;mainWindow.resize(320,180);secondary.resize(160,90);
    mainWindow.show();secondary.show();
    QPixmap pixels(32,32);pixels.fill(QColor("#29208c"));
    int cleanupCalls=0,failures=0;bool cleanupPending=true;QJsonArray checks;
    const auto check=[&](bool passed,const char *name){checks.append(QJsonObject{{"name",name},{"passed",passed}});if(!passed)++failures;};
    std::unique_ptr<TrayController> tray;
    ShutdownCoordinator shutdown(&mainWindow,[&]{++cleanupCalls;tray->beginExit();QTimer::singleShot(100,&app,[&]{cleanupPending=false;});},
        [&]{return cleanupPending;},[&]{return tray->hideWindows();});
    tray=std::make_unique<TrayController>(&mainWindow,QIcon(pixels),[&]{shutdown.request();});
    const auto scope=QStringLiteral("isolated-tray-")+QUuid::createUuid().toString(QUuid::WithoutBraces);
    SingleInstance instance;check(instance.acquire(scope)==SingleInstance::Primary,"isolated primary owns its activation endpoint");
    bool acceptingActivation=true;int activationRound=0;QProcess nextInstance;
    instance.activate=[&]{
        if(!acceptingActivation||shutdown.started())return false;
        tray->restore();return mainWindow.isVisible();
    };
    const auto launchAgain=[&]{nextInstance.start(QCoreApplication::applicationFilePath(),{"--activate",scope});};
    QObject::connect(&nextInstance,&QProcess::finished,&app,[&](int code,QProcess::ExitStatus status){
        check(status==QProcess::NormalExit,"second process finishes normally");
        if(activationRound==0){
            check(code==0&&mainWindow.isVisible(),"second process acknowledges a restored hidden window");
            check(cleanupCalls==0&&!shutdown.started(),"second launch retains the original application services");
            ++activationRound;acceptingActivation=false;mainWindow.close();launchAgain();
        }else if(activationRound==1){
            check(code==10&&!mainWindow.isVisible(),"declined activation is not reported as successful");
            ++activationRound;acceptingActivation=true;mainWindow.showMinimized();launchAgain();
        }else{
            check(code==0&&mainWindow.isVisible()&&!mainWindow.windowStates().testFlag(Qt::WindowMinimized),"second process restores a minimized window");
            tray->menu()->findChild<QAction *>("trayExit")->trigger();
            tray->menu()->findChild<QAction *>("trayExit")->trigger();
            tray->restore();check(!mainWindow.isVisible(),"late activation cannot reopen while exiting");
        }
    });
    QObject::connect(&app,&QCoreApplication::aboutToQuit,&app,[&]{
        check(cleanupCalls==1,"explicit exit cleans up exactly once");
        check(!cleanupPending,"exit waits for asynchronous owned-resource cleanup");
        check(!tray->icon()->isVisible(),"exit removes the notification icon");
        if(app.arguments().size()>1){
            QFile file(app.arguments()[1]);
            if(!file.open(QIODevice::WriteOnly)){++failures;return;}
            const auto report=QJsonDocument(QJsonObject{{"checks",checks},{"failures",failures},{"scope","Native tray/window lifecycle; no host proxy/TUN or network changes"}}).toJson();
            if(file.write(report)!=report.size()||!file.flush())++failures;
        }
    });
    QTimer::singleShot(100,&app,[&]{
        check(QSystemTrayIcon::isSystemTrayAvailable(),"Windows notification area is available");
        check(tray->icon()->isVisible()&&!tray->icon()->icon().isNull(),"tray icon and context menu are installed");
        mainWindow.close();mainWindow.close();
        check(!mainWindow.isVisible()&&!secondary.isVisible(),"close hides application windows");
        check(cleanupCalls==0&&!shutdown.started(),"close keeps the running services and event loop alive");
        tray->menu()->findChild<QAction *>("trayShow")->trigger();
        check(mainWindow.isVisible()&&secondary.isVisible(),"tray open restores hidden windows");
        secondary.close();check(cleanupCalls==0,"secondary window close never exits the app");
        mainWindow.showMinimized();tray->restore();
        check(!mainWindow.windowStates().testFlag(Qt::WindowMinimized),"activation restores a minimized main window");
        mainWindow.close();tray->icon()->activated(QSystemTrayIcon::Trigger);
        check(mainWindow.isVisible(),"notification icon click restores the main window");
        mainWindow.close();launchAgain();
    });
    QTimer::singleShot(12000,&app,[&]{++failures;app.exit(2);});
    const auto result=app.exec();return result?result:failures?1:0;
}
