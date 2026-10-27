#pragma once
#include <QHostAddress>
#include <QJsonArray>
#include <QJsonObject>
#include <QRegularExpression>
#include <QVariantMap>

// Runtime observations only. Never forward arbitrary DLL fields, configuration
// payloads, source documents or private plan digests to connection details.
namespace SwirlRouteObservation {
inline QVariantMap sanitized(const QJsonObject &source) {
    QVariantMap result;
    const auto text=[](const QJsonValue &value,int limit){
        if(!value.isString()||value.toString().size()>limit||value.toString().contains(QRegularExpression("[\\x00-\\x1f\\x7f]")))return QString();
        return value.toString();
    };
    for(const auto &key:QStringList{"revision","generation"}){
        const auto value=text(source.value(key),20);
        if(QRegularExpression("^(0|[1-9][0-9]{0,19})$").match(value).hasMatch()){
            bool valid=false;value.toULongLong(&valid);if(valid)result.insert(key,value);
        }
    }
    const auto mode=text(source.value("mode"),8);
    if(QStringList{"rule","global","direct"}.contains(mode))result.insert("mode",mode);
    const auto tier=source.value("tier");
    if(tier.isDouble()&&tier.toDouble()==tier.toInt()&&
       ((tier.toInt()>=1&&tier.toInt()<=5)||(tier.toInt()==0&&mode=="direct")))result.insert("tier",tier.toInt());
    for(const auto &key:QStringList{"rule_id","service_policy_id","leaf_node_id","source_id"}){
        const auto value=text(source.value(key),128);if(!value.isEmpty())result.insert(key,value);
    }
    for(const auto &key:QStringList{"dns_profile","dns_path","classification_state","rejection_code","affinity_reason"}){
        const auto value=text(source.value(key),64);if(!value.isEmpty())result.insert(key,value);
    }
    const auto ip=text(source.value("chosen_ip"),64);const QHostAddress address(ip);
    if(!address.isNull()&&address.scopeId().isEmpty())result.insert("chosen_ip",address.toString());
    if(source.value("group_chain").isArray()&&source.value("group_chain").toArray().size()<=16){
        QStringList chain;bool valid=true;
        for(const auto &entry:source.value("group_chain").toArray()){const auto id=text(entry,128);if(id.isEmpty()){valid=false;break;}chain.append(id);}
        if(valid)result.insert("group_chain",chain);
    }
    return result;
}
}
