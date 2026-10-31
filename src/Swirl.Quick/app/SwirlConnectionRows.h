#pragma once

#include <QAbstractListModel>
#include <QHash>
#include <QJSValue>
#include <QPointer>
#include <QVector>
#include <QtQml/qqmlregistration.h>

class QJSEngine;

// readSnapshot produces frozen JSON values in this model's engine and retains
// their complete native values for comparison. Other JS sources keep the strict
// JSON comparison path. get() returns an owned entry, not a writable row wrapper.
// This model is confined to the engine thread.
class SwirlConnectionRows : public QAbstractListModel {
    Q_OBJECT
    QML_ELEMENT
    Q_PROPERTY(int count READ count NOTIFY countChanged)
    Q_PROPERTY(QJSValue sourceRows READ sourceRows WRITE setSourceRows NOTIFY sourceRowsChanged)
    Q_PROPERTY(QObject *performanceObserver READ performanceObserver WRITE setPerformanceObserver NOTIFY performanceObserverChanged)
    Q_PROPERTY(QString error READ error NOTIFY errorChanged)
public:
    enum Role { EntryRole = Qt::UserRole };
    explicit SwirlConnectionRows(QObject *parent = nullptr);
    int count() const { return int(m_rows.size()); }
    int rowCount(const QModelIndex &parent = {}) const override;
    QVariant data(const QModelIndex &index, int role) const override;
    QHash<int, QByteArray> roleNames() const override;
    QJSValue sourceRows() const;
    void setSourceRows(const QJSValue &source);
    Q_INVOKABLE QJSValue readSnapshot(QObject *source, const QString &missing);
    QObject *performanceObserver() const { return m_observer.data(); }
    void setPerformanceObserver(QObject *observer);
    QString error() const { return m_error; }
    Q_INVOKABLE QJSValue get(int row) const;
    Q_INVOKABLE int rowForDisplayKey(const QString &key) const;
signals:
    void countChanged();
    void sourceRowsChanged();
    void performanceObserverChanged();
    void errorChanged();
    void aboutToSync();
    void synced();
private:
    struct Row { QString key, signature; QJSValue entry; QVariantMap native; };
    bool setError(const QString &error);
    bool prepareEngine();
    void resetAfterEngineDestroyed();
    void updateIndex(int first, int last);
    void schedulePending();
    void syncLatest();
    static void mark(const QPointer<QObject> &observer, bool entering);
    QVector<Row> m_rows;
    QHash<QString, int> m_index;
    QHash<QString, Row> m_ownedRows;
    QJSValue m_source, m_json, m_stringify;
    QJSValue m_freeze, m_isFrozen;
    QPointer<QJSEngine> m_engine;
    QPointer<QObject> m_observer;
    QString m_error;
    quint64 m_sourceRevision = 0;
    quint64 m_snapshotGeneration = 0;
    bool m_pending = false;
    bool m_syncing = false;
    bool m_queued = false;
    bool m_notifyingSource = false;
    bool m_engineRetired = false;
};
