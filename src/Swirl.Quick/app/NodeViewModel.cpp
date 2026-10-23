#include "NodeViewModel.h"
#include "engine/EngineController.h"
#include <QSettings>
#include <QGuiApplication>
#include <QClipboard>
#include <limits>

QVariant NodeRows::data(const QModelIndex &index,int role) const {
    return index.isValid()&&index.row()<rows.size()&&role==Qt::UserRole?QVariant(rows[index.row()]):QVariant();
}
void NodeRows::update(const QVariantList &values) {
    QSet<QString> incoming;for(const auto &v:values)incoming.insert(v.toMap().value("id").toString());
    for(int i=rows.size()-1;i>=0;--i)if(!incoming.contains(rows[i].value("id").toString())){beginRemoveRows({},i,i);rows.removeAt(i);endRemoveRows();}
    QHash<QString,int> indices;for(int i=0;i<rows.size();++i)indices.insert(rows[i].value("id").toString(),i);
    QList<QVariantMap> added;
    for(const auto &v:values){const auto row=v.toMap();const auto id=row.value("id").toString();if(id.isEmpty())continue;
        const int index=indices.value(id,-1);
        if(index<0){indices.insert(id,rows.size()+added.size());added.append(row);}
        else if(index<rows.size()&&rows[index]!=row){rows[index]=row;emit dataChanged(this->index(index),this->index(index),{Qt::UserRole});}
    }
    if(!added.isEmpty()){beginInsertRows({},rows.size(),rows.size()+added.size()-1);rows.append(added);endInsertRows();}
}
NodeViewModel::NodeViewModel(QObject *parent):QSortFilterProxyModel(parent),m_rows(this) {
    QSettings settings;const auto saved=settings.value("NodePreferences/favorites").toStringList();m_favorites=QSet<QString>(saved.begin(),saved.end());
    m_recent=settings.value("NodePreferences/recent").toStringList();m_recent=m_recent.mid(0,32);
    setSourceModel(&m_rows);setDynamicSortFilter(true);setSortRole(Qt::UserRole);sort(0);
}
void NodeViewModel::notify(){++m_revision;emit changed();}
void NodeViewModel::setController(EngineController *value){
    if(m_controller==value)return;if(m_controller)disconnect(m_controller,nullptr,this,nullptr);m_controller=value;
    if(value){connect(value,&EngineController::nodesChanged,this,&NodeViewModel::refresh);connect(value,&EngineController::statusChanged,this,[this]{
        if(m_controller->connected()&&m_controller->requestSucceeded()&&!m_controller->activeNodeId().isEmpty()){
            const auto id=m_controller->activeNodeId();if(id!=m_lastConnected){m_lastConnected=id;m_recent.removeAll(id);m_recent.prepend(id);m_recent=m_recent.mid(0,32);QSettings().setValue("NodePreferences/recent",m_recent);}
        }else m_lastConnected.clear();refresh();
    });}
    refresh();emit controllerChanged();
}
void NodeViewModel::refresh(){updateRows(m_controller?m_controller->nodes():QVariantList());}
void NodeViewModel::updateRows(const QVariantList &values){
    QVariantList rows;rows.reserve(values.size());
    for(const auto &v:values){auto row=v.toMap();const auto id=row.value("id").toString();row["favorite"]=m_favorites.contains(id);row["recentIndex"]=m_recent.indexOf(id);rows.append(row);}
    m_rows.update(rows);notify();
}
void NodeViewModel::setQuery(const QString &value){const auto query=value.trimmed();if(m_query==query)return;m_query=query;invalidateFilter();notify();}
void NodeViewModel::setFilters(const QVariantMap &value){if(m_filters==value)return;m_filters=value;invalidate();sort(0,value.value("descending").toBool()?Qt::DescendingOrder:Qt::AscendingOrder);notify();}
QVariantMap NodeViewModel::get(int row) const{return data(index(row,0),Qt::UserRole).toMap();}
QVariantMap NodeViewModel::find(const QString &id) const{for(const auto &row:m_rows.rows)if(row.value("id")==id)return row;return {};}
void NodeViewModel::toggleFavorite(const QString &id){
    if(find(id).isEmpty())return;if(m_favorites.contains(id))m_favorites.remove(id);else m_favorites.insert(id);
    QSettings().setValue("NodePreferences/favorites",QStringList(m_favorites.begin(),m_favorites.end()));
    QVariantList rows;for(const auto &row:m_rows.rows)rows.append(row);updateRows(rows);
}
void NodeViewModel::copySafeInfo(const QString &id) const {
    const auto row=find(id);if(row.isEmpty())return;
    QStringList lines;for(const auto &key:{"name","protocol","host","port","regionName","latency","status"})lines.append(QString::fromLatin1(key)+": "+row.value(key).toString());
    QGuiApplication::clipboard()->setText(lines.join('\n'));
}
bool NodeViewModel::filterAcceptsRow(int index,const QModelIndex &) const {
    const auto &r=m_rows.rows[index];
    for(const auto &key:{"protocol","regionCode","sourceId","status"}){const auto f=m_filters.value(key).toString();if(!f.isEmpty()&&r.value(key).toString()!=f)return false;}
    const auto group=m_filters.value("group").toString();if(group=="favorites"&&!r.value("favorite").toBool())return false;if(group=="recent"&&r.value("recentIndex").toInt()<0)return false;
    const int maximum=m_filters.value("maxLatency",-1).toInt();bool measured=false;const int latency=r.value("latency").toString().toInt(&measured);
    if(maximum>=0&&(!measured||latency>maximum))return false;
    if(m_filters.value("available").toBool()&&!r.value("testAvailable").toBool())return false;
    if(m_query.isEmpty())return true;
    for(const auto &key:{"name","host","protocol","regionName","regionCode"})if(r.value(key).toString().contains(m_query,Qt::CaseInsensitive))return true;
    return false;
}
bool NodeViewModel::lessThan(const QModelIndex &left,const QModelIndex &right) const {
    const auto &a=m_rows.rows[left.row()],&b=m_rows.rows[right.row()];
    const auto key=m_filters.value("sort","name").toString();
    if(m_filters.value("group")==QStringLiteral("recent")&&a.value("recentIndex")!=b.value("recentIndex"))return a.value("recentIndex").toInt()<b.value("recentIndex").toInt();
    if(key=="latency"){
        bool av=false,bv=false;const int x=a.value(key).toString().toInt(&av),y=b.value(key).toString().toInt(&bv);
        if(av!=bv)return sortOrder()==Qt::AscendingOrder?av:!av;
        if(av&&x!=y)return x<y;
    }else{const int order=QString::localeAwareCompare(a.value(key).toString(),b.value(key).toString());if(order)return order<0;}
    return a.value("id").toString()<b.value("id").toString();
}
