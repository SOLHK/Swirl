#pragma once
#include <QAction>
#include <QGuiApplication>
#include <QMenu>
#include <QPointer>
#include <QQuickWindow>
#include <QSystemTrayIcon>
#include <functional>

class TrayController final : public QObject {
public:
    TrayController(QQuickWindow *window,const QIcon &icon,std::function<void()> quit)
        :m_window(window),m_tray(icon),m_quit(std::move(quit)) {
        m_tray.setToolTip(QStringLiteral("Swirl · v")+QCoreApplication::applicationVersion());
        auto *show=m_menu.addAction(tr("打开 Swirl"));show->setObjectName("trayShow");
        m_menu.addSeparator();
        auto *exit=m_menu.addAction(tr("退出 Swirl"));exit->setObjectName("trayExit");
        connect(show,&QAction::triggered,this,&TrayController::restore);
        connect(exit,&QAction::triggered,this,[this]{
            if(m_exiting)return;
            beginExit();m_quit();
        });
        connect(&m_tray,&QSystemTrayIcon::activated,this,[this](QSystemTrayIcon::ActivationReason reason){
            if(reason==QSystemTrayIcon::Trigger||reason==QSystemTrayIcon::DoubleClick)restore();
        });
        m_tray.setContextMenu(&m_menu);m_tray.show();
    }
    ~TrayController() override {m_tray.hide();m_tray.setContextMenu(nullptr);}
    void beginExit(){m_exiting=true;m_menu.close();m_tray.hide();m_hidden.clear();}
    bool hideWindows() {
        if(m_exiting||!m_window)return false;
        if(!m_window->isVisible())return true;
        if(!QSystemTrayIcon::isSystemTrayAvailable()){m_window->showMinimized();return true;}
        m_hidden.clear();
        for(auto *window:QGuiApplication::topLevelWindows()){
            if(!window->isVisible()||window->type()==Qt::Popup||window->type()==Qt::ToolTip)continue;
            m_hidden.append(window);window->hide();
        }
        return true;
    }
    void restore() {
        if(m_exiting||!m_window)return;
        for(const auto &window:m_hidden)if(window)window->show();
        m_hidden.clear();
        m_window->setWindowStates(m_window->windowStates()&~Qt::WindowMinimized);
        m_window->show();m_window->raise();m_window->requestActivate();
    }
    QMenu *menu(){return &m_menu;}
    QSystemTrayIcon *icon(){return &m_tray;}
private:
    QPointer<QQuickWindow> m_window;
    QSystemTrayIcon m_tray;
    QMenu m_menu;
    std::function<void()> m_quit;
    QList<QPointer<QWindow>> m_hidden;
    bool m_exiting=false;
};
