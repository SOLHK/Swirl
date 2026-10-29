#include "NodeSectionModel.h"

#include <algorithm>

namespace {
QString displayKey(const QVariantMap &row) { return row.value("displayKey").toString(); }
bool hasContentFilter(const QVariantMap &filters) {
    for(const auto *key:{"protocol","regionCode","status"})
        if(!filters.value(QLatin1String(key)).toString().isEmpty())return true;
    const auto group=filters.value("group").toString();
    return (group!=""&&group!="all")||filters.value("available").toBool()||filters.value("maxLatency",-1).toInt()>=0;
}
}

NodeSectionModel::NodeSectionModel(QObject *parent):QAbstractListModel(parent) {}
int NodeSectionModel::rowCount(const QModelIndex &parent) const { return parent.isValid()?0:m_rows.size(); }
QVariant NodeSectionModel::data(const QModelIndex &index,int role) const {
    if(!index.isValid()||index.column()!=0||index.row()<0||index.row()>=m_rows.size()||role!=Qt::UserRole)return {};
    return m_rows.at(index.row());
}
Qt::ItemFlags NodeSectionModel::flags(const QModelIndex &index) const {
    if(!index.isValid()||index.row()<0||index.row()>=m_rows.size())return Qt::NoItemFlags;
    return m_rows.at(index.row()).value("rowKind")=="section"?Qt::ItemIsEnabled:Qt::ItemIsEnabled|Qt::ItemIsSelectable;
}
QVariantMap NodeSectionModel::get(int row) const { return row>=0&&row<m_rows.size()?m_rows.at(row):QVariantMap{}; }
int NodeSectionModel::indexOfNode(const QString &id) const { return id.isEmpty()?-1:rowForDisplayKey("node:"+id); }
int NodeSectionModel::rowForDisplayKey(const QString &key) const { return m_rowByKey.value(key,-1); }

void NodeSectionModel::setSource(NodeViewModel *value) {
    if(m_source==value)return;
    if(m_source)disconnect(m_source,nullptr,this,nullptr);
    m_source=value;m_cachedCatalogRevision=-1;
    if(value) {
        // NodeViewModel emits one completion after the proxy has incorporated all
        // source notifications. Listening to each base row would rebuild N times.
        connect(value,&NodeViewModel::changed,this,&NodeSectionModel::rebuild);
        connect(value,&QObject::destroyed,this,[this]{m_source=nullptr;m_cachedCatalogRevision=-1;rebuild();emit sourceChanged();});
    }
    rebuild();emit sourceChanged();
}
void NodeSectionModel::setProviders(const QVariantList &value) {
    if(m_providers==value)return;
    m_providers=value;rebuild();emit providersChanged();
}
QString NodeSectionModel::sectionKey(const QVariantMap &row) {
    const auto kind=row.value("sourceKind").toString();
    if(kind=="legacy")return "legacy";
    const auto sourceId=row.value("sourceId").toString();
    return kind=="subscription"||(!sourceId.isEmpty()&&kind.isEmpty())?"subscription:"+sourceId:"manual";
}
void NodeSectionModel::toggleSection(const QString &key) {
    const int row=rowForDisplayKey("section:"+key);
    if(row<0||!get(row).value("collapsible").toBool())return;
    if(m_collapsed.contains(key))m_collapsed.remove(key);else m_collapsed.insert(key);
    rebuild();
}

void NodeSectionModel::refreshCatalog() {
    const int revision=m_source?m_source->catalogRevision():-1;
    if(m_source&&revision==m_cachedCatalogRevision)return;
    m_cachedCatalogRevision=revision;
    m_catalogTotals.clear();m_catalogNames.clear();m_catalogSubscriptions.clear();
    QSet<QString> incoming;
    const auto catalog=m_source?m_source->catalogRows():QVariantList{};
    incoming.reserve(catalog.size());m_cachedNodes.reserve(catalog.size());
    for(const auto &value:catalog) {
        const auto row=value.toMap();const auto id=row.value("id").toString();
        if(id.isEmpty())continue;
        incoming.insert(id);const auto key=sectionKey(row);
        ++m_catalogTotals[key];
        if(m_catalogNames.value(key).isEmpty())m_catalogNames.insert(key,row.value("sourceName").toString());
        auto found=m_cachedNodes.find(id);
        if(found==m_cachedNodes.end()||found->base!=row) {
            CachedNode cached{row,row,key,{}};
            cached.entry.insert("rowKind","node");cached.entry.insert("displayKey","node:"+id);
            cached.entry.insert("sectionKey",key);
            if(found==m_cachedNodes.end())m_cachedNodes.insert(id,std::move(cached));
            else *found=std::move(cached);
        }
    }
    for(auto it=m_cachedNodes.begin();it!=m_cachedNodes.end();) {
        if(!incoming.contains(it.key()))it=m_cachedNodes.erase(it);else ++it;
    }
    for(auto it=m_catalogTotals.cbegin();it!=m_catalogTotals.cend();++it)
        if(it.key().startsWith("subscription:"))m_catalogSubscriptions.append(it.key());
    std::sort(m_catalogSubscriptions.begin(),m_catalogSubscriptions.end());
}

void NodeSectionModel::rebuild() {
    refreshCatalog();
    QStringList order;
    auto names=m_catalogNames;
    QHash<QString,QStringList> matching;
    QSet<QString> declared;
    QStringList nodeIds;
    const int total=m_source?m_source->total():0;
    const bool searching=m_source&&!m_source->query().isEmpty();
    const auto filters=m_source?m_source->filters():QVariantMap{};
    const bool showEmpty=!searching&&!hasContentFilter(filters);
    const auto wantedId=filters.value("sourceId").toString();
    const auto wantedKind=filters.value("sourceKind").toString();
    const auto sourceAllowed=[&](const QString &kind,const QString &id) {
        return (wantedKind.isEmpty()||wantedKind==kind)&&(wantedId.isEmpty()||wantedId==id);
    };

    // Fixed namespaces keep manual/unknown ownership separate from subscriptions
    // even when display names or legacy source IDs collide.
    if(sourceAllowed("manual",{})){order.append("manual");names.insert("manual",tr("手动添加"));}
    names.insert("legacy",tr("历史节点 · 归属待确认"));
    for(const auto &value:m_providers) {
        const auto provider=value.toMap();const auto id=provider.value("id").toString();
        const auto key="subscription:"+id;
        if(id.isEmpty()||declared.contains(key))continue;
        declared.insert(key);
        if(!sourceAllowed("subscription",id))continue;
        order.append(key);
        const auto name=provider.value("name").toString();if(!name.isEmpty())names.insert(key,name);
    }
    if(m_source) {
        for(const auto &key:m_catalogSubscriptions)
            if(!declared.contains(key)&&sourceAllowed("subscription",key.mid(13)))order.append(key);
        for(int index=0;index<m_source->rowCount();++index) {
            const auto id=m_source->get(index).value("id").toString();
            auto found=m_cachedNodes.find(id);if(found==m_cachedNodes.end())continue;
            auto &cached=found.value();const auto name=names.value(cached.sectionKey).isEmpty()?tr("订阅来源"):names.value(cached.sectionKey);
            if(cached.sectionName!=name){cached.sectionName=name;cached.entry.insert("sectionName",name);}
            matching[cached.sectionKey].append(id);
        }
    }
    if(sourceAllowed("legacy",{}))order.append("legacy");
    QList<QVariantMap> next;
    QSet<QString> included;
    for(const auto &key:order) {
        if(included.contains(key))continue;
        included.insert(key);
        const auto ids=matching.value(key);const int matched=ids.size();
        if(!matched&&(!showEmpty||!key.startsWith("subscription:")))continue;
        const bool expanded=searching||!m_collapsed.contains(key);
        const auto name=names.value(key).isEmpty()?tr("订阅来源"):names.value(key);
        next.append(QVariantMap{{"rowKind","section"},{"displayKey","section:"+key},{"id",QString()},
            {"sectionKey",key},{"sectionName",name},{"name",name},{"matchedCount",matched},
            {"totalCount",m_catalogTotals.value(key)},{"expanded",expanded},{"collapsible",!searching&&matched>0}});
        nodeIds.append(ids);
        if(expanded)for(const auto &id:ids)next.append(m_cachedNodes.constFind(id)->entry);
    }
    const bool rowChanges=next!=m_rows;
    const bool changed=rowChanges||nodeIds!=m_nodeIds||total!=m_total;
    if(!changed)return;
    if(rowChanges){emit aboutToSync();syncRows(next);}
    m_nodeIds=std::move(nodeIds);m_total=total;++m_revision;
    if(rowChanges)emit synced();
    emit this->changed();
}

void NodeSectionModel::rebuildIndex() {
    m_rowByKey.clear();m_rowByKey.reserve(m_rows.size());
    for(int row=0;row<m_rows.size();++row)m_rowByKey.insert(displayKey(m_rows.at(row)),row);
}
void NodeSectionModel::syncRows(const QList<QVariantMap> &next) {
    QSet<QString> keys;keys.reserve(next.size());
    for(const auto &row:next)keys.insert(displayKey(row));
    for(int last=m_rows.size()-1;last>=0;) {
        if(keys.contains(displayKey(m_rows.at(last)))){--last;continue;}
        const int end=last;
        while(last>=0&&!keys.contains(displayKey(m_rows.at(last))))--last;
        beginRemoveRows({},last+1,end);m_rows.remove(last+1,end-last);endRemoveRows();
    }
    rebuildIndex();
    QList<QVariantMap> added;
    for(const auto &row:next)if(!m_rowByKey.contains(displayKey(row)))added.append(row);
    if(!added.isEmpty()) {
        const int first=m_rows.size();beginInsertRows({},first,first+added.size()-1);
        m_rows.append(added);endInsertRows();rebuildIndex();
    }
    int misplaced=0;
    for(int row=0;row<next.size();++row)if(displayKey(m_rows.at(row))!=displayKey(next.at(row)))++misplaced;
    if(misplaced>32) {
        // A reversal of 2000 rows should be one permutation, not 1999 moves.
        // Explicit persistent-index remapping preserves the selected identity.
        emit layoutAboutToBeChanged({},QAbstractItemModel::VerticalSortHint);
        const auto before=persistentIndexList();QModelIndexList after;after.reserve(before.size());
        QHash<QString,QVariantMap> old;old.reserve(m_rows.size());
        for(const auto &row:m_rows)old.insert(displayKey(row),row);
        QHash<QString,int> targetRows;targetRows.reserve(next.size());
        QList<QVariantMap> reordered;reordered.reserve(next.size());
        for(int row=0;row<next.size();++row){const auto key=displayKey(next.at(row));targetRows.insert(key,row);reordered.append(old.value(key));}
        for(const auto &index:before)after.append(this->index(targetRows.value(displayKey(m_rows.at(index.row()))),0));
        m_rows=std::move(reordered);changePersistentIndexList(before,after);rebuildIndex();
        emit layoutChanged({},QAbstractItemModel::VerticalSortHint);
    } else if(misplaced) {
        for(int target=0;target<next.size();++target) {
            const auto key=displayKey(next.at(target));const int current=m_rowByKey.value(key);
            if(current==target)continue;
            beginMoveRows({},current,current,{},target);m_rows.move(current,target);endMoveRows();
            for(int row=target;row<=current;++row)m_rowByKey[displayKey(m_rows.at(row))]=row;
        }
    }
    QList<int> updated;
    for(int row=0;row<next.size();++row)if(m_rows.at(row)!=next.at(row)){m_rows[row]=next.at(row);updated.append(row);}
    for(qsizetype position=0;position<updated.size();) {
        const int first=updated.at(position);int last=first;
        while(++position<updated.size()&&updated.at(position)==last+1)last=updated.at(position);
        emit dataChanged(index(first,0),index(last,0),{Qt::UserRole});
    }
    rebuildIndex();
}
