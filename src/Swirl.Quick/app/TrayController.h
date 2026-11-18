#pragma once
#include <QAction>
#include <QByteArray>
#include <QCoreApplication>
#include <QGuiApplication>
#include <QMenu>
#include <QPointer>
#include <QQuickWindow>
#include <QSystemTrayIcon>
#include <functional>

#ifdef Q_OS_WIN
#ifndef WIN32_LEAN_AND_MEAN
#define WIN32_LEAN_AND_MEAN
#endif
#include <windows.h>
#endif

class TrayController final : public QObject {
public:
    using AvailabilityCheck = std::function<bool()>;
    static bool defaultAvailability() {
        if(!QSystemTrayIcon::isSystemTrayAvailable())return false;
#ifdef Q_OS_WIN
        const HWND taskbar=FindWindowW(L"Shell_TrayWnd",nullptr);
        if(!taskbar)return false;
        DWORD taskbarPid=0;
        if(!GetWindowThreadProcessId(taskbar,&taskbarPid)||taskbarPid==0)return false;
        QByteArray selfUser,taskbarUser;
        DWORD selfIntegrity=0,taskbarIntegrity=0;
        if(!readProcessIdentity(GetCurrentProcess(),selfUser,selfIntegrity))return false;
        HANDLE taskbarProcess=OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION,FALSE,taskbarPid);
        if(!taskbarProcess)return false;
        const bool ok=readProcessIdentity(taskbarProcess,taskbarUser,taskbarIntegrity);
        CloseHandle(taskbarProcess);
        if(!ok)return false;
        const PSID selfSid=reinterpret_cast<TOKEN_USER *>(selfUser.data())->User.Sid;
        const PSID taskbarSid=reinterpret_cast<TOKEN_USER *>(taskbarUser.data())->User.Sid;
        return EqualSid(selfSid,taskbarSid)!=FALSE&&selfIntegrity>=taskbarIntegrity;
#else
        return true;
#endif
    }
    TrayController(QQuickWindow *window,const QIcon &icon,std::function<void()> quit,
                   AvailabilityCheck availability=defaultAvailability)
        :m_window(window),m_tray(icon),m_quit(std::move(quit)),
         m_available(availability&&availability()) {
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
        m_tray.setContextMenu(&m_menu);
        if(m_available)m_tray.show();
    }
    ~TrayController() override {m_tray.hide();m_tray.setContextMenu(nullptr);}
    bool isAvailable() const {return m_available;}
    void beginExit(){m_exiting=true;m_menu.close();m_tray.hide();m_hidden.clear();}
    bool hideWindows() {
        if(m_exiting||!m_window||!m_available||!m_tray.isVisible())return false;
        if(!m_window->isVisible())return true;
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
#ifdef Q_OS_WIN
    static bool readProcessIdentity(HANDLE process,QByteArray &userBuffer,DWORD &integrity) {
        HANDLE token=nullptr;
        if(!OpenProcessToken(process,TOKEN_QUERY,&token))return false;
        DWORD userBytes=0;GetTokenInformation(token,TokenUser,nullptr,0,&userBytes);
        if(userBytes==0){CloseHandle(token);return false;}
        userBuffer.resize(int(userBytes));
        if(!GetTokenInformation(token,TokenUser,userBuffer.data(),userBytes,&userBytes)){CloseHandle(token);return false;}
        DWORD labelBytes=0;GetTokenInformation(token,TokenIntegrityLevel,nullptr,0,&labelBytes);
        if(labelBytes==0){CloseHandle(token);return false;}
        QByteArray labelBuffer(int(labelBytes),0);
        if(!GetTokenInformation(token,TokenIntegrityLevel,labelBuffer.data(),labelBytes,&labelBytes)){CloseHandle(token);return false;}
        CloseHandle(token);
        auto *labelSid=reinterpret_cast<const TOKEN_MANDATORY_LABEL *>(labelBuffer.constData())->Label.Sid;
        if(!IsValidSid(const_cast<PSID>(labelSid)))return false;
        const UCHAR subCount=*GetSidSubAuthorityCount(const_cast<PSID>(labelSid));
        if(subCount==0)return false;
        integrity=*GetSidSubAuthority(const_cast<PSID>(labelSid),subCount-1);
        return IsValidSid(reinterpret_cast<TOKEN_USER *>(userBuffer.data())->User.Sid)!=FALSE;
    }
#endif
    QPointer<QQuickWindow> m_window;
    QSystemTrayIcon m_tray;
    QMenu m_menu;
    std::function<void()> m_quit;
    QList<QPointer<QWindow>> m_hidden;
    bool m_available=false;
    bool m_exiting=false;
};
