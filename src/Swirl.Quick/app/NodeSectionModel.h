#pragma once

#include <QAbstractListModel>
#include <QHash>
#include <QPointer>
#include <QSet>
#include <QtQml/qqmlregistration.h>
#include "NodeViewModel.h"

// Public, presentation-only projection. Section IDs never become node IDs or
// runtime selections, and collapsed rows remain available for filtered testing.
class NodeSectionModel : public QAbstractListModel {
    Q_OBJECT
    QML_ELEMENT
    Q_PROPERTY(NodeViewModel* source READ source WRITE setSource NOTIFY sourceChanged)
    Q_PROPERTY(QVariantList providers READ providers WRITE setProviders NOTIFY providersChanged)
    Q_PROPERTY(int count READ count NOTIFY changed)
    Q_PROPERTY(int total READ total NOTIFY changed)
    Q_PROPERTY(int displayCount READ displayCount NOTIFY changed)
    Q_PROPERTY(int revision READ revision NOTIFY changed)
public:
    explicit NodeSectionModel(QObject *parent=nullptr);
    NodeViewModel *source() const { return m_source; }
    void setSource(NodeViewModel *value);
    QVariantList providers() const { return m_providers; }
    void setProviders(const QVariantList &value);
    int count() const { return m_nodeIds.size(); }
    int total() const { return m_total; }
    int displayCount() const { return m_rows.size(); }
    int revision() const { return m_revision; }
    int rowCount(const QModelIndex &parent={}) const override;
    QVariant data(const QModelIndex &index,int role) const override;
    Qt::ItemFlags flags(const QModelIndex &index) const override;
    QHash<int,QByteArray> roleNames() const override { return {{Qt::UserRole,"entry"}}; }
    Q_INVOKABLE QVariantMap get(int row) const;
    Q_INVOKABLE int indexOfNode(const QString &id) const;
    Q_INVOKABLE int rowForDisplayKey(const QString &key) const;
    Q_INVOKABLE QStringList nodeIds() const { return m_nodeIds; }
    Q_INVOKABLE void toggleSection(const QString &key);
signals:
    void sourceChanged();
    void providersChanged();
    void aboutToSync();
    void synced();
    void changed();
private:
    struct CachedNode {
        QVariantMap base;
        QVariantMap entry;
        QString sectionKey;
        QString sectionName;
    };
    void refreshCatalog();
    void rebuild();
    void syncRows(const QList<QVariantMap> &next);
    void rebuildIndex();
    static QString sectionKey(const QVariantMap &row);
    QPointer<NodeViewModel> m_source;
    QVariantList m_providers;
    QList<QVariantMap> m_rows;
    QHash<QString,int> m_rowByKey;
    QStringList m_nodeIds;
    QSet<QString> m_collapsed;
    QHash<QString,CachedNode> m_cachedNodes;
    QHash<QString,int> m_catalogTotals;
    QHash<QString,QString> m_catalogNames;
    QStringList m_catalogSubscriptions;
    int m_cachedCatalogRevision=-1;
    int m_total=0;
    int m_revision=0;
};
