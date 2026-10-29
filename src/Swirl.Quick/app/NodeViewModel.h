#pragma once
#include <QAbstractListModel>
#include <QSortFilterProxyModel>
#include <QPointer>
#include <QSet>
#include <QTimer>
#include <QtQml/qqmlregistration.h>
#include "engine/EngineController.h"

class NodeRows final : public QAbstractListModel {
public:
    using QAbstractListModel::QAbstractListModel;
    int rowCount(const QModelIndex &parent={}) const override { return parent.isValid()?0:rows.size(); }
    QVariant data(const QModelIndex &index,int role) const override;
    QHash<int,QByteArray> roleNames() const override { return {{Qt::UserRole,"entry"}}; }
    bool update(const QVariantList &values);
    QList<QVariantMap> rows;
};

class NodeViewModel : public QSortFilterProxyModel {
    Q_OBJECT
    QML_ELEMENT
    Q_PROPERTY(EngineController* controller READ controller WRITE setController NOTIFY controllerChanged)
    Q_PROPERTY(QString query READ query WRITE setQuery NOTIFY changed)
    Q_PROPERTY(QVariantMap filters READ filters WRITE setFilters NOTIFY changed)
    Q_PROPERTY(int count READ rowCount NOTIFY changed)
    Q_PROPERTY(int total READ total NOTIFY changed)
    Q_PROPERTY(int revision READ revision NOTIFY changed)
    Q_PROPERTY(int catalogRevision READ catalogRevision NOTIFY changed)
public:
    explicit NodeViewModel(QObject *parent=nullptr);
    EngineController *controller() const { return m_controller; }
    void setController(EngineController *value);
    QString query() const { return m_query; }
    void setQuery(const QString &value);
    QVariantMap filters() const { return m_filters; }
    void setFilters(const QVariantMap &value);
    int total() const { return m_rows.rowCount(); }
    int revision() const { return m_revision; }
    int catalogRevision() const { return m_catalogRevision; }
    QVariantList catalogRows() const;
    Q_INVOKABLE QVariantMap get(int row) const;
    Q_INVOKABLE QVariantMap find(const QString &id) const;
    Q_INVOKABLE void toggleFavorite(const QString &id);
    Q_INVOKABLE void copySafeInfo(const QString &id) const;
    // Public data only. Also used by isolated tests; never mutates NodeStore.
    void updateRows(const QVariantList &values);
signals:
    void controllerChanged();
    void changed();
protected:
    bool filterAcceptsRow(int row,const QModelIndex &parent) const override;
    bool lessThan(const QModelIndex &left,const QModelIndex &right) const override;
private:
    void refresh();
    void scheduleRefresh();
    void notify();
    NodeRows m_rows;
    QPointer<EngineController> m_controller;
    QString m_query,m_lastConnected;
    QVariantMap m_filters;
    QSet<QString> m_favorites;
    QStringList m_recent;
    int m_revision=0;
    int m_catalogRevision=0;
    QTimer m_refreshTimer;
};
