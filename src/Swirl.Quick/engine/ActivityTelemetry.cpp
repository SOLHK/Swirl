#include "ActivityTelemetry.h"
#include <QJsonArray>
#include <QSet>
#include <algorithm>
#include <QFile>
#include <QDir>
#include <QFileInfo>
#include <QSaveFile>
#include <QJsonDocument>

void ActivityTelemetry::setHistoryPath(const QString &path) {
    m_historyPath=path;QFile file(path);
    if(file.open(QIODevice::ReadOnly) && file.size()<512*1024)m_days=QJsonDocument::fromJson(file.readAll()).object().toVariantMap();
}
void ActivityTelemetry::saveHistory() {
    if(m_historyPath.isEmpty())return;
    QDir().mkpath(QFileInfo(m_historyPath).absolutePath());QSaveFile file(m_historyPath);
    if(file.open(QIODevice::WriteOnly)){file.write(QJsonDocument::fromVariant(m_days).toJson(QJsonDocument::Compact));file.commit();}
}
void ActivityTelemetry::reset(){saveHistory();m_lastTime=0;m_lastUp=0;m_lastDown=0;m_previous.clear();m_upHistory.clear();m_downHistory.clear();m_snapshot.clear();}
bool ActivityTelemetry::ingest(const QJsonObject &object,qint64 now) {
    const auto connections=object.value("connections");
    // Mihomo serializes an empty active-connection slice as JSON null.
    if((!connections.isArray() && !connections.isNull()) || !object.value("uploadTotal").isDouble() || !object.value("downloadTotal").isDouble())return false;
    const auto up=object.value("uploadTotal").toInteger(-1),down=object.value("downloadTotal").toInteger(-1);
    if(up<0 || down<0)return false;
    if(m_lastTime && (up<m_lastUp || down<m_lastDown || now<=m_lastTime))reset();
    const bool sampled=m_lastTime>0;
    const double seconds=sampled?(now-m_lastTime)/1000.0:0;
    const double upRate=sampled?(up-m_lastUp)/seconds:0,downRate=sampled?(down-m_lastDown)/seconds:0;
    if(sampled){m_upHistory.append(upRate);m_downHistory.append(downRate);}
    while(m_upHistory.size()>60){m_upHistory.removeFirst();m_downHistory.removeFirst();}
    QSet<QString> processes,devices;
    QVariantList rows;
    QHash<QString,qint64> clients,domains,policies,proxyClients,proxyDomains,proxyPolicies;
    qint64 direct=0,proxied=0;
    QHash<QString,qint64> nextPrevious;
    for(const auto &entry:object.value("connections").toArray()) {
        const auto c=entry.toObject(),meta=c.value("metadata").toObject();
        const auto id=c.value("id").toString();if(id.isEmpty())continue;
        const auto process=meta.value("process").toString();
        const auto source=meta.value("sourceIP").toString();
        const auto host=meta.value("host").toString(meta.value("destinationIP").toString());
        const auto chain=c.value("chains").toArray();
        const auto policy=chain.isEmpty()?QStringLiteral("Unknown"):chain.first().toString();
        const bool isDirect=chain.contains(QStringLiteral("DIRECT"));
        const auto uploaded=qMax<qint64>(0,c.value("upload").toInteger()),downloaded=qMax<qint64>(0,c.value("download").toInteger());
        const auto bytes=uploaded+downloaded;
        nextPrevious.insert(id,bytes);
        const auto delta=sampled?qMax<qint64>(0,bytes-m_previous.value(id,0)):0;
        if(!process.isEmpty())processes.insert(process);
        if(!source.isEmpty())devices.insert(source);
        const auto client=process.isEmpty()?source:process;
        clients[client]+=bytes;domains[host]+=bytes;policies[policy]+=bytes;
        if(isDirect)direct+=delta;else {proxied+=delta;proxyClients[client]+=bytes;proxyDomains[host]+=bytes;proxyPolicies[policy]+=bytes;}
        rows.append(QVariantMap{{"id",id},{"host",host},{"ip",meta.value("destinationIP").toString()},{"process",process.isEmpty()?QStringLiteral("—"):process},
            {"protocol",meta.value("network").toString()},{"policy",policy},{"up",uploaded},{"down",downloaded},{"latency",QStringLiteral("—")},
            {"time",c.value("start").toString()},{"status",QStringLiteral("Active")}});
    }
    const auto ranked=[](const QHash<QString,qint64> &source){
        QVariantList result;for(auto it=source.cbegin();it!=source.cend();++it)result.append(QVariantMap{{"name",it.key().isEmpty()?QStringLiteral("Unknown"):it.key()},{"bytes",it.value()}});
        std::sort(result.begin(),result.end(),[](const QVariant &a,const QVariant &b){return a.toMap().value("bytes").toLongLong()>b.toMap().value("bytes").toLongLong();});
        if(result.size()>5)result=result.mid(0,5);return result;
    };
    const auto date=QDateTime::fromMSecsSinceEpoch(now);const auto key=date.date().toString(Qt::ISODate);
    auto day=m_days.value(key).toMap();auto hours=day.value("hours").toList();auto proxyHours=day.value("proxyHours").toList();
    while(hours.size()<24)hours.append(0);while(proxyHours.size()<24)proxyHours.append(0);
    // A sample spanning midnight cannot be assigned precisely; leave that gap
    // uncounted rather than attributing yesterday's bytes to today's total.
    const bool sameDay=sampled && QDateTime::fromMSecsSinceEpoch(m_lastTime).date()==date.date();
    const qint64 delta=sameDay?(up-m_lastUp)+(down-m_lastDown):0;
    day["total"]=day.value("total").toLongLong()+delta;
    day["direct"]=day.value("direct").toLongLong()+(sameDay?direct:0);
    day["proxy"]=day.value("proxy").toLongLong()+(sameDay?proxied:0);
    hours[date.time().hour()]=hours[date.time().hour()].toLongLong()+delta;
    proxyHours[date.time().hour()]=proxyHours[date.time().hour()].toLongLong()+(sameDay?proxied:0);
    day["hours"]=hours;day["proxyHours"]=proxyHours;m_days[key]=day;
    for(const auto &old:m_days.keys())if(QDate::fromString(old,Qt::ISODate)<date.date().addDays(-62))m_days.remove(old);
    qint64 month=0,monthDirect=0,monthProxy=0;
    for(auto it=m_days.cbegin();it!=m_days.cend();++it)if(it.key().startsWith(key.left(7))){const auto d=it.value().toMap();month+=d.value("total").toLongLong();monthDirect+=d.value("direct").toLongLong();monthProxy+=d.value("proxy").toLongLong();}
    m_snapshot={{"available",true},{"sampled",sampled},{"up",upRate},{"down",downRate},{"total",up+down},{"connections",rows},
        {"processes",processes.size()},{"devices",devices.size()},{"direct",day.value("direct")},{"proxy",day.value("proxy")},
        {"today",day.value("total")},{"month",month},{"monthDirect",monthDirect},{"monthProxy",monthProxy},{"hours",hours},{"proxyHours",proxyHours},
        {"upHistory",m_upHistory},{"downHistory",m_downHistory},{"clients",ranked(clients)},{"domains",ranked(domains)},{"policies",ranked(policies)},
        {"proxyClients",ranked(proxyClients)},{"proxyDomains",ranked(proxyDomains)},{"proxyPolicies",ranked(proxyPolicies)}};
    m_previous=nextPrevious;m_lastTime=now;m_lastUp=up;m_lastDown=down;
    if(now-m_lastSave>=30000){saveHistory();m_lastSave=now;}return true;
}
