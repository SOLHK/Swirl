#pragma once

#include <QElapsedTimer>
#include <QObject>
#include <QThread>
#include <atomic>
#include <cstddef>
#include <vector>

// Test-only observer. QML calls it on the GUI thread at stage boundaries;
// storage is allocated before measurement and never grows in mark().
class ActivityPerfTrace final : public QObject {
    Q_OBJECT
public:
    struct Mark {qint64 ns=0,collectorNs=0;int stage=0;bool entering=false;};
    explicit ActivityPerfTrace(std::size_t capacity=16384,QObject *parent=nullptr)
        :QObject(parent),m_marks(capacity){}
    void arm(const QElapsedTimer &epoch) {
        Q_ASSERT(QThread::currentThread()==thread());
        m_epoch=epoch;m_armedNs=m_epoch.nsecsElapsed();m_armed=true;
    }
    void stop() {
        Q_ASSERT(QThread::currentThread()==thread());
        m_armed=false;m_stoppedNs=m_epoch.nsecsElapsed();
    }
    Q_INVOKABLE void mark(int stage,bool entering) {
        if(QThread::currentThread()!=thread()){
            m_wrongThread.fetch_add(1,std::memory_order_relaxed);return;
        }
        if(!m_armed)return;
        const qint64 start=m_epoch.nsecsElapsed();
        if(m_count>=m_marks.size()){m_overflow=true;++m_dropped;return;}
        auto &sample=m_marks[m_count++];sample.ns=start;sample.stage=stage;sample.entering=entering;
        if(stage<1||stage>12)++m_invalidStage;
        // A lower bound: excludes QML/native dispatch, assignment and return.
        sample.collectorNs=m_epoch.nsecsElapsed()-start;
    }
    const std::vector<Mark> &marks() const {return m_marks;}
    std::size_t count() const {return m_count;}
    bool overflow() const {return m_overflow;}
    quint64 dropped() const {return m_dropped;}
    quint64 invalidStage() const {return m_invalidStage;}
    quint64 wrongThread() const {return m_wrongThread.load(std::memory_order_relaxed);}
    qint64 armedNs() const {return m_armedNs;}
    qint64 stoppedNs() const {return m_stoppedNs;}
private:
    QElapsedTimer m_epoch;
    std::vector<Mark> m_marks;
    std::size_t m_count=0;
    quint64 m_dropped=0,m_invalidStage=0;
    qint64 m_armedNs=0,m_stoppedNs=0;
    std::atomic<quint64> m_wrongThread{0};
    bool m_armed=false,m_overflow=false;
};
