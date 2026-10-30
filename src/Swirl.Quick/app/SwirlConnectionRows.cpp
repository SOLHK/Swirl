#include "SwirlConnectionRows.h"

#include <QJSEngine>
#include <QScopeGuard>
#include <QSet>
#include <QThread>
#include <QTimer>
#include <QtQml/qqml.h>
#include <algorithm>
#include <cmath>
#include <limits>

SwirlConnectionRows::SwirlConnectionRows(QObject *parent) : QAbstractListModel(parent) {}

int SwirlConnectionRows::rowCount(const QModelIndex &parent) const {
    return parent.isValid() ? 0 : count();
}

QHash<int, QByteArray> SwirlConnectionRows::roleNames() const {
    return {{EntryRole, "entry"}};
}

QVariant SwirlConnectionRows::data(const QModelIndex &index, int role) const {
    if (QThread::currentThread() != thread() || m_engineRetired || !m_engine
        || !index.isValid() || index.model() != this || index.column() != 0
        || index.row() < 0 || index.row() >= count() || role != EntryRole)
        return {};
    return QVariant::fromValue(m_rows.at(index.row()).entry);
}

QJSValue SwirlConnectionRows::get(int row) const {
    if (QThread::currentThread() != thread() || m_engineRetired || !m_engine
        || row < 0 || row >= count())
        return {};
    return m_rows.at(row).entry;
}

int SwirlConnectionRows::rowForDisplayKey(const QString &key) const {
    return QThread::currentThread() == thread() && !m_engineRetired
        ? m_index.value(key, -1) : -1;
}

QJSValue SwirlConnectionRows::sourceRows() const {
    return QThread::currentThread() == thread() && !m_engineRetired ? m_source : QJSValue();
}

void SwirlConnectionRows::setPerformanceObserver(QObject *observer) {
    if (QThread::currentThread() != thread() || m_observer == observer) return;
    m_observer = observer;
    emit performanceObserverChanged();
}

void SwirlConnectionRows::setSourceRows(const QJSValue &source) {
    if (QThread::currentThread() != thread() || m_engineRetired || m_source.strictlyEquals(source)) return;
    m_source = source;
    ++m_sourceRevision;
    m_pending = true;
    const bool nestedNotification = m_notifyingSource;
    m_notifyingSource = true;
    const QPointer<SwirlConnectionRows> guard(this);
    emit sourceRowsChanged();
    if (!guard) return;
    m_notifyingSource = nestedNotification;
    if (!nestedNotification && !m_syncing && !m_queued) syncLatest();
}

bool SwirlConnectionRows::setError(const QString &error) {
    if (m_error == error) return true;
    m_error = error;
    const QPointer<SwirlConnectionRows> guard(this);
    emit errorChanged();
    return bool(guard);
}

void SwirlConnectionRows::mark(const QPointer<QObject> &observer, bool entering) {
#ifdef SWIRL_ACTIVITY_PERF_TRACE
    if (observer && observer->thread() == QThread::currentThread())
        QMetaObject::invokeMethod(observer, "mark", Qt::DirectConnection,
                                 Q_ARG(int, 7), Q_ARG(bool, entering));
#else
    Q_UNUSED(observer);
    Q_UNUSED(entering);
#endif
}

bool SwirlConnectionRows::prepareEngine() {
    if (m_engineRetired) return false;
    if (m_engine && m_stringify.isCallable()) return true;
    const QPointer<SwirlConnectionRows> guard(this);
    const QPointer<QJSEngine> engine(qjsEngine(this));
    if (!engine || engine->thread() != QThread::currentThread()) {
        setError(QStringLiteral("Connection rows require their owning GUI JS engine"));
        return false;
    }
    if (!m_engine) {
        m_engine = engine;
        connect(engine, &QObject::destroyed, this, [this] {
            m_engineRetired = true;
            m_pending = false;
            // Finish an open begin/end model notification before resetting. No
            // further JavaScript is evaluated once the engine has been retired.
            if (!m_syncing) resetAfterEngineDestroyed();
        });
    }
    const QJSValue global = engine->globalObject();
    const QJSValue json = global.property(QStringLiteral("JSON"));
    if (!guard || !engine || m_engineRetired) return false;
    const QJSValue stringify = json.property(QStringLiteral("stringify"));
    if (!guard || !engine || m_engineRetired) return false;
    if (!stringify.isCallable()) {
        setError(QStringLiteral("Connection rows require JSON.stringify"));
        return false;
    }
    m_json = json;
    m_stringify = stringify;
    return true;
}

void SwirlConnectionRows::resetAfterEngineDestroyed() {
    const QPointer<SwirlConnectionRows> guard(this);
    beginResetModel();
    if (!guard) return;
    m_pending = false;
    m_source = QJSValue();
    m_json = QJSValue();
    m_stringify = QJSValue();
    m_rows.clear();
    m_index.clear();
    endResetModel();
    if (!guard) return;
    emit countChanged();
}

void SwirlConnectionRows::updateIndex(int first, int last) {
    for (int i = first; i <= last; ++i) m_index.insert(m_rows.at(i).key, i);
}

void SwirlConnectionRows::schedulePending() {
    if (!m_pending || m_queued || m_engineRetired || !m_engine) return;
    m_queued = true;
    QTimer::singleShot(0, this, [this] {
        m_queued = false;
        if (m_pending && !m_notifyingSource && !m_syncing && !m_engineRetired && m_engine) syncLatest();
    });
}

void SwirlConnectionRows::syncLatest() {
    if (m_syncing || !m_pending || m_engineRetired) return;
    const QPointer<SwirlConnectionRows> guard(this);
    const QPointer<QObject> observer = m_observer;
    m_syncing = true;
    m_pending = false;
    const auto finish = qScopeGuard([guard, observer] {
        mark(observer, false);
        if (!guard) return;
        guard->m_syncing = false;
        if (guard->m_engineRetired) guard->resetAfterEngineDestroyed();
        else guard->schedulePending();
    });
    mark(observer, true);
    if (!guard || !prepareEngine() || !guard) return;
    const QPointer<QJSEngine> engine = m_engine;
    const QJSValue source = m_source;
    const QJSValue json = m_json;
    const QJSValue stringify = m_stringify;
    const quint64 revision = m_sourceRevision;
    const auto inputCurrent = [&] {
        return guard && engine && !guard->m_engineRetired && revision == guard->m_sourceRevision;
    };
    if (!source.isArray() && !source.isNull() && !source.isUndefined()) {
        setError(QStringLiteral("Connection rows require an array"));
        return;
    }
    int size = 0;
    if (source.isArray()) {
        const QJSValue length = source.property(QStringLiteral("length"));
        if (!inputCurrent()) return;
        const double value = length.toNumber();
        if (!inputCurrent()) return;
        if (!std::isfinite(value) || value < 0 || value > std::numeric_limits<int>::max()
            || std::floor(value) != value) {
            setError(QStringLiteral("Connection row count exceeds the model index range"));
            return;
        }
        size = int(value);
    }
    QVector<Row> desired;
    desired.reserve(size);
    QSet<QString> incoming;
    incoming.reserve(size);
    for (int i = 0; i < size; ++i) {
        const QJSValue entry = source.property(quint32(i));
        if (!inputCurrent()) return;
        if (!entry.isObject() || entry.isNull()) {
            setError(QStringLiteral("Connection rows require objects with distinct nonempty ids"));
            return;
        }
        const QJSValue id = entry.property(QStringLiteral("id"));
        if (!inputCurrent()) return;
        const QString key = id.toString();
        if (!inputCurrent()) return;
        if (id.isUndefined() || id.isNull() || key.isEmpty() || incoming.contains(key)) {
            setError(QStringLiteral("Connection rows require objects with distinct nonempty ids"));
            return;
        }
        const QJSValue serialized = stringify.callWithInstance(json, {entry});
        if (!inputCurrent()) return;
        if (serialized.isError() || !serialized.isString()) {
            setError(QStringLiteral("Connection row is not serializable JSON"));
            return;
        }
        const QString signature = serialized.toString();
        if (!inputCurrent()) return;
        desired.push_back({key, signature, entry});
        incoming.insert(key);
    }
    // Validation is atomic. Even clearing a previous error can execute QML and
    // replace this source or destroy the model, so recheck before any mutation.
    if (!setError({}) || !inputCurrent()) return;
    bool changed = false;
    const auto beginChange = [&] {
        if (!changed) {
            changed = true;
            emit aboutToSync();
        }
        return guard && engine && !guard->m_engineRetired;
    };
    int last = count() - 1;
    while (last >= 0) {
        if (incoming.contains(m_rows.at(last).key)) { --last; continue; }
        const int end = last;
        while (last >= 0 && !incoming.contains(m_rows.at(last).key)) --last;
        if (!beginChange()) return;
        beginRemoveRows({}, last + 1, end);
        if (!guard) return;
        for (int i = last + 1; i <= end; ++i) m_index.remove(m_rows.at(i).key);
        m_rows.remove(last + 1, end - last);
        updateIndex(last + 1, count() - 1);
        endRemoveRows();
        if (!guard || !engine || m_engineRetired) return;
        emit countChanged();
        if (!guard || !engine || m_engineRetired) return;
    }
    for (int i = 0; i < desired.size(); ++i) {
        const auto &wanted = desired.at(i);
        const int found = i < count() && m_rows.at(i).key == wanted.key
            ? i : m_index.value(wanted.key, -1);
        if (found < 0) {
            if (!beginChange()) return;
            beginInsertRows({}, i, i);
            if (!guard) return;
            m_rows.insert(i, wanted);
            updateIndex(i, count() - 1);
            endInsertRows();
            if (!guard || !engine || m_engineRetired) return;
            emit countChanged();
            if (!guard || !engine || m_engineRetired) return;
        } else {
            if (found != i) {
                if (!beginChange()) return;
                const bool accepted = beginMoveRows({}, found, found, {}, found < i ? i + 1 : i);
                if (!guard) return;
                Q_ASSERT(accepted);
                if (!accepted) return;
                m_rows.move(found, i);
                updateIndex(std::min(found, i), std::max(found, i));
                endMoveRows();
                if (!guard || !engine || m_engineRetired) return;
            }
            if (m_rows.at(i).signature != wanted.signature) {
                if (!beginChange()) return;
                m_rows[i] = wanted;
                emit dataChanged(index(i), index(i), {EntryRole});
                if (!guard || !engine || m_engineRetired) return;
            }
        }
    }
    if (changed) emit synced();
}
