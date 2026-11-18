#pragma once

#include <QElapsedTimer>
#include <QObject>
#include <QThread>
#include <atomic>
#include <cstddef>
#include <vector>

// Test-only observer. Storage is allocated before measurement and never grows
// in either QML stage marks or GUI event dispatch observation.
class ActivityPerfTrace final : public QObject {
    Q_OBJECT
public:
    struct Mark {qint64 ns=0,collectorNs=0;int stage=0;bool entering=false;};
    struct Dispatch {qint64 startedNs=0,durationNs=0;int type=0;bool complete=false;};
    class DispatchScope final {
    public:
        explicit DispatchScope(int type):m_trace(s_dispatchTrace),m_generation(s_dispatchGeneration) {
            if(!m_trace)return;
            m_outermost=m_trace->m_dispatchDepth++==0;
            if(!m_outermost)return;
            const qint64 start=m_trace->m_epoch.nsecsElapsed();
            if(m_trace->m_dispatchCount>=m_trace->m_dispatches.size()){
                m_trace->m_dispatchOverflow=true;++m_trace->m_dispatchDropped;return;
            }
            m_index=m_trace->m_dispatchCount++;m_stored=true;
            m_trace->m_dispatches[m_index]={start,0,type,false};
        }
        ~DispatchScope() {
            // notify() may destroy/disarm the observer, or replace it at the
            // same address. Never touch it until both active guards agree.
            if(!m_trace||s_dispatchTrace!=m_trace||s_dispatchGeneration!=m_generation)return;
            --m_trace->m_dispatchDepth;
            if(m_outermost&&m_stored){
                auto &sample=m_trace->m_dispatches[m_index];
                sample.durationNs=m_trace->m_epoch.nsecsElapsed()-sample.startedNs;
                sample.complete=true;
            }
        }
        DispatchScope(const DispatchScope &)=delete;
        DispatchScope &operator=(const DispatchScope &)=delete;
    private:
        ActivityPerfTrace *m_trace=nullptr;
        quint64 m_generation=0;
        std::size_t m_index=0;
        bool m_outermost=false,m_stored=false;
    };
    explicit ActivityPerfTrace(std::size_t capacity=16384,QObject *parent=nullptr)
        :QObject(parent),m_marks(capacity),m_dispatches(65536){}
    ~ActivityPerfTrace() override {
        if(s_dispatchTrace==this){s_dispatchTrace=nullptr;++s_dispatchGeneration;}
    }
    void arm(const QElapsedTimer &epoch) {
        Q_ASSERT(QThread::currentThread()==thread());
        m_epoch=epoch;m_armedNs=m_epoch.nsecsElapsed();m_armed=true;
        m_dispatchCount=0;m_dispatchDropped=0;m_dispatchOverflow=false;m_dispatchDepth=0;
        ++s_dispatchGeneration;s_dispatchTrace=this;
    }
    void stop() {
        Q_ASSERT(QThread::currentThread()==thread());
        m_armed=false;m_stoppedNs=m_epoch.nsecsElapsed();
        if(m_dispatchDepth>0&&m_dispatchCount>0){
            auto &last=m_dispatches[m_dispatchCount-1];
            if(!last.complete)last.durationNs=m_stoppedNs-last.startedNs;
        }
        if(s_dispatchTrace==this){s_dispatchTrace=nullptr;++s_dispatchGeneration;}
        m_dispatchDepth=0;
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
    const std::vector<Dispatch> &dispatches() const {return m_dispatches;}
    std::size_t dispatchCount() const {return m_dispatchCount;}
    bool dispatchOverflow() const {return m_dispatchOverflow;}
    quint64 dispatchDropped() const {return m_dispatchDropped;}
    std::size_t count() const {return m_count;}
    bool overflow() const {return m_overflow;}
    quint64 dropped() const {return m_dropped;}
    quint64 invalidStage() const {return m_invalidStage;}
    quint64 wrongThread() const {return m_wrongThread.load(std::memory_order_relaxed);}
    qint64 armedNs() const {return m_armedNs;}
    qint64 stoppedNs() const {return m_stoppedNs;}
private:
    inline static thread_local ActivityPerfTrace *s_dispatchTrace=nullptr;
    inline static thread_local quint64 s_dispatchGeneration=0;
    QElapsedTimer m_epoch;
    std::vector<Mark> m_marks;
    std::vector<Dispatch> m_dispatches;
    std::size_t m_count=0,m_dispatchCount=0;
    quint64 m_dropped=0,m_invalidStage=0,m_dispatchDropped=0;
    qint64 m_armedNs=0,m_stoppedNs=0;
    std::atomic<quint64> m_wrongThread{0};
    int m_dispatchDepth=0;
    bool m_armed=false,m_overflow=false,m_dispatchOverflow=false;
};
