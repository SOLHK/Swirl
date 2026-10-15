#pragma once
#include <QGuiApplication>
#include <QQuickWindow>
#include <QCloseEvent>
#include <QElapsedTimer>
#include <QTimer>
#include <QDebug>
#include <functional>

// Keep the event loop alive while owned services perform asynchronous cleanup.
// Secondary-window close remains local; only the main window or Quit exits.
class ShutdownCoordinator final : public QObject {
public:
    ShutdownCoordinator(QQuickWindow *window,std::function<void()> begin,
                        std::function<bool()> pending):m_window(window),m_begin(std::move(begin)),m_pending(std::move(pending)) {
        qApp->installEventFilter(this);
        m_poll.setInterval(25);
        connect(&m_poll,&QTimer::timeout,this,[this]{
            if(m_pending() && m_elapsed.elapsed()<8000)return;
            qInfo()<<"Shutdown completed"<<m_elapsed.elapsed()<<"ms; cleanup pending:"<<m_pending();
            qApp->setProperty("shutdownDurationMs",m_elapsed.elapsed());
            m_poll.stop();m_finished=true;QCoreApplication::quit();
        });
    }
    bool started() const{return m_started;}
    void request() {
        if(m_started)return;
        m_started=true;m_elapsed.start();
        m_begin();
        for(auto *window:QGuiApplication::topLevelWindows())window->hide();
        m_poll.start();
    }
protected:
    bool eventFilter(QObject *object,QEvent *event) override {
        if(m_finished)return false;
        if((object==m_window&&event->type()==QEvent::Close)||(object==qApp&&event->type()==QEvent::Quit)){
            if(event->type()==QEvent::Close)static_cast<QCloseEvent *>(event)->ignore();
            request();return true;
        }
        return false;
    }
private:
    QQuickWindow *m_window;
    std::function<void()> m_begin;
    std::function<bool()> m_pending;
    QTimer m_poll;
    QElapsedTimer m_elapsed;
    bool m_started=false,m_finished=false;
};
