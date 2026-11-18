#include <QCoreApplication>
#include <QJSEngine>
#include <QDebug>
#include <QtQml/private/qv4engine_p.h>
#include <QtQml/private/qv4mm_p.h>
#include <QtQml/private/qv4object_p.h>
#include <QtQml/private/qv4persistent_p.h>
#include <vector>

// Independent diagnostic for the allocator invariant described in QTBUG-149512.
// It observes free-list membership without allocating over a live object's tail.
namespace QV4 {
std::vector<PersistentValue> sweepRoots;
int sameWordAllocations = 0;
namespace Heap {
struct SweepAllocator : Object {
    void init() { Object::init(); }
    void destroy() {
        ExecutionEngine *vm = internalClass->engine;
        const HeapItem *dying = reinterpret_cast<const HeapItem *>(this);
        Chunk *ownChunk = dying->chunk();
        const auto ownWord = (dying - ownChunk->realBase()) / Chunk::Bits;
        for (int n = 0; n < 256; ++n) {
            Heap::Object *fresh = vm->newObject();
            const HeapItem *freshSlot = reinterpret_cast<const HeapItem *>(fresh);
            const bool sameWord = freshSlot->chunk() == ownChunk
                && (freshSlot - ownChunk->realBase()) / Chunk::Bits == ownWord;
            if (sameWord) {
                ++sameWordAllocations;
                sweepRoots.emplace_back(vm, Value::fromHeapObject(fresh));
            }
        }
        Object::destroy();
    }
};
}
struct SweepAllocator : Object {
    V4_OBJECT2(SweepAllocator, Object)
    V4_NEEDS_DESTROY
};
DEFINE_OBJECT_VTABLE(SweepAllocator);
}

int main(int argc, char **argv) {
    QCoreApplication app(argc, argv);
    QJSEngine js;
    QV4::ExecutionEngine *vm = js.handle();
    QV4::MemoryManager *mm = vm->memoryManager;
    std::vector<QV4::PersistentValue> retained;
    mm->gcBlocked = QV4::MemoryManager::InCriticalSection;
    for (int n = 0; n < 2048; ++n) {
        auto *object = vm->newObject();
        if (n % 2) retained.emplace_back(vm, QV4::Value::fromHeapObject(object));
    }
    mm->gcBlocked = QV4::MemoryManager::Unblocked;
    mm->runFullGC();
    mm->allocate<QV4::SweepAllocator>();
    mm->runFullGC();

    int liveObjectsInFreeList = 0;
    for (const auto &value : QV4::sweepRoots) {
        const auto *managed = value.asManaged();
        const auto *start = reinterpret_cast<const QV4::HeapItem *>(managed->heapObject());
        const size_t values = managed->vtable()->nInlineProperties
            + managed->vtable()->inlinePropertyOffset;
        const size_t slotCount = values * sizeof(QV4::Value) / QV4::Chunk::SlotSize;
        for (int bin = 0; bin < QV4::BlockAllocator::NumBins; ++bin) {
            for (const auto *free = mm->blockAllocator.freeBins[bin]; free; free = free->freeData.next) {
                if (free > start && free < start + slotCount) ++liveObjectsInFreeList;
            }
        }
    }
    qInfo() << "SWEEP_SLOTS_RESULT" << "qt" << qVersion()
            << "sameBitmapWordAllocations" << QV4::sameWordAllocations
            << "freeRunsInsideLiveObjects" << liveObjectsInFreeList;
    QV4::sweepRoots.clear();
    return QV4::sameWordAllocations == 0 ? 3 : liveObjectsInFreeList ? 2 : 0;
}
