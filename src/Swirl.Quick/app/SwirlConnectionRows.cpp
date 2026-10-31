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

namespace {
bool nativeValuesEqual(const QVariant &a, const QVariant &b);
bool nativeMapsEqual(const QVariantMap &a, const QVariantMap &b) {
    if (a.size() != b.size()) return false;
    auto left = a.cbegin(), right = b.cbegin();
    for (; left != a.cend(); ++left, ++right) {
        if (left.key() != right.key() || !nativeValuesEqual(left.value(), right.value())) return false;
    }
    return true;
}
bool nativeValuesEqual(const QVariant &a, const QVariant &b) {
    if (a.metaType() != b.metaType()) return false;
    if (a.metaType().id() == QMetaType::QVariantMap) return nativeMapsEqual(a.toMap(), b.toMap());
    if (a.metaType().id() == QMetaType::QVariantList) {
        const auto left = a.toList(), right = b.toList();
        if (left.size() != right.size()) return false;
        for (int i = 0; i < left.size(); ++i) {
            if (!nativeValuesEqual(left[i], right[i])) return false;
        }
        return true;
    }
    return a == b;
}
}

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

QJSValue SwirlConnectionRows::readSnapshot(QObject *source, const QString &missing) {
    if (QThread::currentThread() != thread() || m_engineRetired)
        return {};
    const QPointer<SwirlConnectionRows> guard(this);
    const QPointer<QObject> sourceGuard(source);
    const auto generation = ++m_snapshotGeneration;
    const auto revision = m_sourceRevision;
    if (!prepareEngine() || !guard)
        return {};
    const QPointer<QJSEngine> engine = m_engine;
    const auto current = [&] {
        return guard && engine && sourceGuard && QThread::currentThread() == guard->thread() && !guard->m_engineRetired
            && generation == guard->m_snapshotGeneration && revision == guard->m_sourceRevision;
    };
    if (!sourceGuard)
        return {};
    if (sourceGuard->thread() != thread()) {
        setError(QStringLiteral("Connection snapshot source requires the model thread"));
        return {};
    }
    QVariantList input;
    const bool invoked = QMetaObject::invokeMethod(sourceGuard.data(), "connectionSnapshot", Qt::DirectConnection,
                                                 Q_RETURN_ARG(QVariantList, input));
    if (!current())
        return {};
    if (!invoked) {
        setError(QStringLiteral("Connection snapshot source requires connectionSnapshot()"));
        return {};
    }
    const auto freeze = m_freeze, isFrozen = m_isFrozen;
    bool valid = true;
    const auto scalar = [&](const QVariant &value) -> QJSValue {
        switch (value.metaType().id()) {
        case QMetaType::UnknownType:
            return {};
        case QMetaType::Nullptr:
            return QJSValue(QJSValue::NullValue);
        case QMetaType::QString:
            return QJSValue(value.toString());
        case QMetaType::Bool:
            return QJSValue(value.toBool());
        case QMetaType::Int:
        case QMetaType::UInt:
        case QMetaType::LongLong:
        case QMetaType::ULongLong:
        case QMetaType::Double:
        case QMetaType::Float:
            return QJSValue(value.toDouble());
        default:
            valid = false;
            return {};
        }
    };
    const auto clone = [&](auto &&self, const QVariant &value, const QVariant &previous,
                           const QJSValue &previousEntry) -> QJSValue {
        if (previousEntry.isObject() && nativeValuesEqual(value, previous))
            return previousEntry;
        QJSValue result;
        if (value.metaType().id() == QMetaType::QVariantMap) {
            result = engine->newObject();
            result.setPrototype(QJSValue(QJSValue::NullValue));
            const auto map = value.toMap();
            const auto previousMap = previous.metaType().id() == QMetaType::QVariantMap
                ? previous.toMap() : QVariantMap();
            for (auto it = map.cbegin(); it != map.cend(); ++it) {
                const auto type = it.value().metaType().id();
                QJSValue child;
                if (type == QMetaType::QVariantMap || type == QMetaType::QVariantList || type == QMetaType::QStringList) {
                    const auto old = previousMap.constFind(it.key());
                    const bool found = old != previousMap.cend() && previousEntry.isObject();
                    child = self(self, it.value(), found ? old.value() : QVariant(),
                                 found ? previousEntry.property(it.key()) : QJSValue());
                } else {
                    child = scalar(it.value());
                }
                if (!valid || !current())
                    return {};
                result.setProperty(it.key(), child);
            }
        } else if (value.metaType().id() == QMetaType::QVariantList || value.metaType().id() == QMetaType::QStringList) {
            const auto list = value.toList();
            const auto previousList = previous.metaType() == value.metaType() ? previous.toList() : QVariantList();
            result = engine->newArray(uint(list.size()));
            const auto prototype = result.prototype();
            result.setPrototype(QJSValue(QJSValue::NullValue));
            for (int i = 0; i < list.size(); ++i) {
                const auto type = list[i].metaType().id();
                QJSValue child;
                if (type == QMetaType::QVariantMap || type == QMetaType::QVariantList || type == QMetaType::QStringList) {
                    const bool found = i < previousList.size() && previousEntry.isObject();
                    child = self(self, list[i], found ? previousList[i] : QVariant(),
                                 found ? previousEntry.property(i) : QJSValue());
                } else {
                    child = scalar(list[i]);
                }
                if (!valid || !current())
                    return {};
                result.setProperty(i, child);
                if (!current())
                    return {};
            }
            result.setPrototype(prototype);
        } else
            return scalar(value);
        const auto frozen = freeze.call({result});
        if (!current())
            return {};
        const auto immutable = isFrozen.call({result});
        if (!current())
            return {};
        if (frozen.isError() || !frozen.strictlyEquals(result) || immutable.isError() || !immutable.toBool()) {
            valid = false;
            return {};
        }
        return result;
    };
    QHash<QString, Row> owned;
    owned.reserve(input.size());
    auto result = engine->newArray(uint(input.size()));
    const auto prototype = result.prototype();
    result.setPrototype(QJSValue(QJSValue::NullValue));
    for (int i = 0; i < input.size(); ++i) {
        if (input[i].metaType().id() != QMetaType::QVariantMap) {
            valid = false;
            break;
        }
        auto row = input[i].toMap();
        const auto id = row.value(QStringLiteral("id"));
        const auto key = id.toString();
        if (id.metaType().id() != QMetaType::QString || key.isEmpty() || owned.contains(key)) {
            valid = false;
            break;
        }
        const auto chosen = row.value(QStringLiteral("route")).toMap().value(QStringLiteral("chosen_ip"));
        if (chosen.isValid()) {
            const auto ip = scalar(chosen);
            if (!valid)
                break;
            if (ip.toBool())
                row[QStringLiteral("ip")] = chosen;
        }
        for (const auto &field : {QStringLiteral("host"), QStringLiteral("ip"), QStringLiteral("process"),
                                 QStringLiteral("protocol"), QStringLiteral("latency")}) {
            const auto native = row.value(field);
            const auto value = scalar(native);
            if (!valid)
                break;
            const auto text = value.isNull() || value.isUndefined() || (value.isString() && value.toString().isEmpty())
                ? missing : value.toString();
            if (native.metaType().id() != QMetaType::QString || native.toString() != text)
                row[field] = text;
        }
        if (!valid)
            break;
        Row previous;
        {
            const auto cached = m_ownedRows.constFind(key);
            if (cached != m_ownedRows.cend())
                previous = *cached;
        }
        const auto entry = clone(clone, row, previous.native, previous.entry);
        if (!current())
            return {};
        if (!valid)
            break;
        owned.insert(key, Row{key, {}, entry, row});
        result.setProperty(i, entry);
        if (!current())
            return {};
    }
    if (!valid) {
        setError(QStringLiteral("Connection snapshot requires native JSON rows with distinct string ids"));
        return {};
    }
    result.setPrototype(prototype);
    const auto frozen = freeze.call({result});
    if (!current())
        return {};
    const auto immutable = isFrozen.call({result});
    if (!current())
        return {};
    if (frozen.isError() || !frozen.strictlyEquals(result) || immutable.isError() || !immutable.toBool()) {
        setError(QStringLiteral("Connection snapshot freeze failed"));
        return {};
    }
    m_ownedRows = std::move(owned);
    if (!setError({}) || !current())
        return {};
    return result;
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
    if (m_engine && m_stringify.isCallable() && m_freeze.isCallable() && m_isFrozen.isCallable()) return true;
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
    const auto object = global.property(QStringLiteral("Object"));
    if (!guard || !engine || m_engineRetired) return false;
    const auto freeze = object.property(QStringLiteral("freeze"));
    if (!guard || !engine || m_engineRetired) return false;
    const auto isFrozen = object.property(QStringLiteral("isFrozen"));
    if (!guard || !engine || m_engineRetired) return false;
    if (!freeze.isCallable() || !isFrozen.isCallable()) {
        setError(QStringLiteral("Connection snapshot requires Object.freeze and Object.isFrozen"));
        return false;
    }
    m_freeze = freeze;
    m_isFrozen = isFrozen;
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
    m_freeze = QJSValue();
    m_isFrozen = QJSValue();
    m_ownedRows.clear();
    ++m_snapshotGeneration;
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
        const auto owned = m_ownedRows.constFind(key);
        if (owned != m_ownedRows.cend() && owned->entry.strictlyEquals(entry)) {
            desired.push_back(*owned);
            incoming.insert(key);
            continue;
        }
        const QJSValue serialized = stringify.callWithInstance(json, {entry});
        if (!inputCurrent()) return;
        if (serialized.isError() || !serialized.isString()) {
            setError(QStringLiteral("Connection row is not serializable JSON"));
            return;
        }
        const QString signature = serialized.toString();
        if (!inputCurrent()) return;
        desired.push_back({key, signature, entry,{}});
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
    for (int i = 0; i < desired.size();) {
        const auto &wanted = desired.at(i);
        const int found = i < count() && m_rows.at(i).key == wanted.key
            ? i : m_index.value(wanted.key, -1);
        if (found < 0) {
            int end = i + 1;
            while (end < desired.size() && !m_index.contains(desired.at(end).key)) ++end;
            if (!beginChange()) return;
            beginInsertRows({}, i, end - 1);
            if (!guard) return;
            m_rows.insert(i, end - i, Row{});
            for (int row = i; row < end; ++row) m_rows[row] = desired.at(row);
            updateIndex(i, count() - 1);
            endInsertRows();
            if (!guard || !engine || m_engineRetired) return;
            emit countChanged();
            if (!guard || !engine || m_engineRetired) return;
            i = end;
        } else {
            int length = 1;
            while (found + length < count() && i + length < desired.size()
                   && m_rows.at(found + length).key == desired.at(i + length).key)
                ++length;
            if (found != i) {
                if (!beginChange()) return;
                // Earlier desired rows are fixed, so the remaining matching run
                // always moves toward the front without changing its identity.
                Q_ASSERT(found > i);
                const bool accepted = beginMoveRows({}, found, found + length - 1, {}, i);
                if (!guard) return;
                Q_ASSERT(accepted);
                if (!accepted) return;
                std::rotate(m_rows.begin() + i, m_rows.begin() + found,
                            m_rows.begin() + found + length);
                updateIndex(i, found + length - 1);
                endMoveRows();
                if (!guard || !engine || m_engineRetired) return;
            }
            i += length;
        }
    }
    const auto sameValue = [](const Row &a, const Row &b) {
        if (a.native.isEmpty() && b.native.isEmpty()) return a.signature == b.signature;
        return !a.native.isEmpty() && !b.native.isEmpty() && a.entry.strictlyEquals(b.entry);
    };
    for (int first = 0; first < desired.size();) {
        if (sameValue(m_rows.at(first),desired.at(first))) { ++first; continue; }
        int end = first + 1;
        while (end < desired.size() && !sameValue(m_rows.at(end),desired.at(end))) ++end;
        if (!beginChange()) return;
        for (int row = first; row < end; ++row) m_rows[row] = desired.at(row);
        emit dataChanged(index(first), index(end - 1), {EntryRole});
        if (!guard || !engine || m_engineRetired) return;
        first = end;
    }
    if (changed) emit synced();
}
