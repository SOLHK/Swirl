#include "NodeImporter.h"
#include "SubscriptionNormalizer.h"
#include "../third_party/fkYAML/node.hpp"
#include <QJsonArray>
#include <QJsonDocument>
#include <QJsonObject>
#include <QRegularExpression>
#include <QSet>
#include <QUuid>
#include <stdexcept>

namespace {
QJsonValue convert(const fkyaml::node &value, int depth, int &budget) {
    if (depth > 32 || --budget < 0) throw std::runtime_error("limit");
    if (value.is_null()) return QJsonValue();
    if (value.is_boolean()) return value.as_bool();
    if (value.is_integer()) return qint64(value.as_int());
    if (value.is_float_number()) return value.as_float();
    if (value.is_string()) return QString::fromStdString(value.as_str());
    if (value.is_sequence()) {
        QJsonArray out;
        for (const auto &entry : value.as_seq()) out.append(convert(entry, depth+1, budget));
        return out;
    }
    QJsonObject out;
    for (const auto &[key, entry] : value.as_map()) {
        if (!key.is_string()) throw std::runtime_error("key");
        const auto name=QString::fromStdString(key.as_str());
        if (name=="<<") {
            const auto merged=convert(entry,depth+1,budget);
            const auto sources=merged.isArray()?merged.toArray():QJsonArray{merged};
            for (const auto &source:sources) {
                if (!source.isObject()) throw std::runtime_error("merge");
                const auto object=source.toObject();
                for (auto it=object.begin();it!=object.end();++it) if (!out.contains(it.key()))out.insert(it.key(),it.value());
            }
        }
    }
    for (const auto &[key,entry]:value.as_map()) {
        const auto name=QString::fromStdString(key.as_str());
        if (name!="<<")out.insert(name,convert(entry,depth+1,budget));
    }
    return out;
}
QJsonValue singleDocument(const QByteArray &bytes) {
    const auto documents=fkyaml::node::deserialize_docs(bytes.constData(),bytes.constData()+bytes.size());
    if(documents.size()!=1)throw std::runtime_error("document count");
    int budget=100000;return convert(documents.front(),0,budget);
}
bool safeShape(const QByteArray &bytes) {
    // Bound nesting before the YAML parser allocates an AST. A conservative
    // limit is preferable to accepting a document which could exhaust the UI.
    int flow=0, indent=0; char quote=0; bool escaped=false, lineStart=true, comment=false;
    for (const char c:bytes) {
        if(c=='\n'){lineStart=true;indent=0;comment=false;continue;}
        if(comment)continue;
        if(lineStart && c==' '){if(++indent>256)return false;continue;}
        lineStart=false;
        if(quote){if(escaped){escaped=false;continue;}if(c=='\\'&&quote=='"'){escaped=true;continue;}if(c==quote)quote=0;continue;}
        if(c=='"'||c=='\''){quote=c;continue;}
        if(c=='#'){comment=true;continue;}
        if(c=='['||c=='{'){if(++flow>64)return false;}
        if(c==']'||c=='}')--flow;
    }
    return true;
}
bool safeOptions(const QJsonValue &value) {
    // Subscription documents cannot read local keys/config files, choose a
    // host interface, execute plugins, or alter the host routing table.
    if(value.isArray()){for(const auto &v:value.toArray())if(!safeOptions(v))return false;}
    if(value.isObject()){
        const auto obj=value.toObject();
        for(auto it=obj.begin();it!=obj.end();++it){
            const auto key=it.key().toLower();
            if(key.endsWith("-path") || key.endsWith("-file") || key=="interface-name" || key=="routing-mark" ||
                key=="iproute2-table-index" || key=="auto-route" || key=="script" || key=="command" || key=="plugin-path")return false;
            if(!safeOptions(it.value()))return false;
        }
    }
    return true;
}
}
QJsonObject NodeImporter::strictJsonObject(const QByteArray &bytes){
    if(bytes.isEmpty()||bytes.size()>MaximumBytes||!safeShape(bytes))return {};
    QJsonParseError error;const auto json=QJsonDocument::fromJson(bytes,&error);if(error.error!=QJsonParseError::NoError||!json.isObject())return {};
    try{return singleDocument(bytes).toObject();}catch(...){return {};}
}
NodeImporter::Result NodeImporter::parse(const QByteArray &bytes) {
    Result result;
    if(bytes.isEmpty() || bytes.size()>MaximumBytes || !safeShape(bytes)) {
        result.error=QStringLiteral("导入内容为空、超过 4 MiB 或嵌套过深；原节点保持不变。"); return result;
    }
    QJsonValue root;
    const auto normalized=SubscriptionNormalizer::normalize(bytes);
    result.format=normalized.format;
    result.configuration=normalized.configuration;
    result.executionConfiguration=normalized.executionConfiguration;
    result.configurationFormat=normalized.configurationFormat;
    if(!normalized.error.isEmpty()){result.error=normalized.error;return result;}
    const auto effective=normalized.decodedDocument.isEmpty()?bytes:normalized.decodedDocument;
    if(!safeShape(effective)){result.error=QStringLiteral("订阅解码后嵌套过深。");return result;}
    if(normalized.handled){
        // QJsonDocument accepts duplicate keys. Validate the original JSON
        // with the existing strict parser before adapting sing-box objects.
        if(normalized.configurationFormat=="sing-box"||effective.trimmed().startsWith('{')){
            try{singleDocument(effective);}
            catch(...){result.error=QStringLiteral("JSON 含重复键、无效结构或过深嵌套。");return result;}
        }
        root=normalized.nodes;
    }
    else {
    try {
        root=singleDocument(effective);
    } catch(...) {
        // Parser messages can quote password/token-bearing input; never expose them.
        result.error=QStringLiteral("无法解析 Clash YAML/JSON：请检查格式、重复键、锚点循环和嵌套层数。"); return result;
    }
    }
    QJsonArray array;
    if(root.isArray())array=root.toArray();
    else if(root.isObject()) {
        const auto obj=root.toObject();
        if(obj.contains("proxies")) {
            array=obj.value("proxies").toArray();
            result.configuration=obj;result.configuration.remove("proxies");result.configurationFormat="clash";
        }
        else if(obj.contains("type"))array.append(obj);
    }
    if(array.isEmpty() || array.size()>2000) {
        result.error=QStringLiteral("需要包含 1–2000 个节点的 proxies 列表或单个节点；只导入节点，不执行订阅内的全局配置。");return result;
    }
    QSet<QString> names;
    for(int i=0;i<array.size();++i) {
        auto params=array[i].toObject(); ProxyNode n;
        n.sourceFormat=normalized.format;
        if(normalized.handled){n.originalConfiguration=normalized.originals.value(i);n.conversionIssues=normalized.issues.value(i);}
        else n.originalConfiguration=params;
        if(!n.conversionIssues.isEmpty())++result.incompleteNodes;
        n.id=QUuid::createUuid().toString(QUuid::WithoutBraces);
        n.name=params.take("name").toString().trimmed();n.protocol=params.take("type").toString().toLower();
        if(!result.configuration.isEmpty() && names.contains(n.name)) {
            result.nodes.clear();result.error=QStringLiteral("完整配置含重复节点名称，策略引用不明确；未应用配置。");return result;
        }
        if(n.protocol=="socks4"||n.protocol=="socks4a"){
            const auto port=params.value("port");
            if(!port.isDouble()||port.toDouble()!=port.toInt()||port.toInt()<1||port.toInt()>65535){
                result.nodes.clear();result.error=QStringLiteral("第 %1 个节点：SOCKS4/4a 端口须为 1–65535 的整数。").arg(i+1);return result;
            }
            for(const auto &key:QStringList{"username","password","cipher","sni"})if(params.contains(key)&&!params.value(key).isString()){
                result.nodes.clear();result.error=QStringLiteral("第 %1 个节点：SOCKS4/4a 凭据或安全参数类型无效。").arg(i+1);return result;
            }
        }
        n.host=params.take("server").toString().trimmed();
        const auto portValue=params.take("port");bool portOk=false;
        const auto port=portValue.toVariant().toString().toInt(&portOk);
        if(!portOk && n.protocol=="ssh" && portValue.isUndefined()){n.port=22;portOk=true;}
        else if(portOk && port>=1 && port<=65535)n.port=quint16(port);
        n.username=params.take("username").toVariant().toString();n.password=params.take("password").toVariant().toString();
        n.cipher=params.take("cipher").toString();n.serverName=params.take("sni").toString();
        if(n.serverName.isEmpty())n.serverName=params.value("servername").toString();
        n.parameters=params;
        auto error=ProxyNode::validate(n);
        if(!safeOptions(params))error=QStringLiteral("节点含本地文件、脚本或系统网络设置；请移除此类字段后导入。");
        if(names.contains(n.name))error=QStringLiteral("节点名称重复，无法安全确定链式代理引用。");
        if(!error.isEmpty()) {
            result.nodes.clear();result.error=QStringLiteral("第 %1 个节点：%2").arg(i+1).arg(error);return result;
        }
        names.insert(n.name);result.nodes.append(n);
    }
    for(const auto &n:result.nodes){
        const auto dialer=n.parameters.value("dialer-proxy").toString();
        if(!dialer.isEmpty() && !names.contains(dialer)){
            result.nodes.clear();result.error=QStringLiteral("链式代理引用了未导入的节点；请导入完整节点列表。");return result;
        }
        QSet<QString> visited;auto cursor=n.name;
        while(!cursor.isEmpty()) {
            if(visited.contains(cursor)){result.nodes.clear();result.error=QStringLiteral("节点存在循环的链式代理引用；请检查 dialer-proxy。");return result;}
            visited.insert(cursor);QString next;
            for(const auto &candidate:result.nodes)if(candidate.name==cursor){next=candidate.parameters.value("dialer-proxy").toString();break;}
            cursor=next;
        }
    }
    return result;
}
