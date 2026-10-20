#include "SubscriptionNormalizer.h"
#include "NodeImporter.h"
#include <QJsonDocument>
#include <QUrl>
#include <QUrlQuery>
#include <QRegularExpression>
#include <QSet>
#include <algorithm>
#include <optional>
#include <QStringDecoder>

namespace {
using Result=SubscriptionNormalizer::Result;
QString clean(QString s){s=s.trimmed();if(s.size()>=2&&((s.front()=='"'&&s.back()=='"')||(s.front()=='\''&&s.back()=='\''))){const auto quote=s.front();s=s.mid(1,s.size()-2);s.replace(QString('\\')+quote,QString(quote));s.replace("\\\\","\\");}return s;}
QByteArray base64(QByteArray text){
    text=text.trimmed();text.replace('\r',"");text.replace('\n',"");
    if(QRegularExpression("[^A-Za-z0-9+/=_-]").match(QString::fromLatin1(text)).hasMatch())return {};
    text.replace('-','+');text.replace('_','/');
    const auto r=QByteArray::fromBase64Encoding(text,QByteArray::AbortOnBase64DecodingErrors);
    return r?r.decoded:QByteArray();
}
QStringList csv(const QString &line,bool *ok){
    QStringList fields;QString value;QChar quote;bool escaped=false;*ok=true;
    for(auto c:line){
        if(escaped){value+=c;escaped=false;continue;}
        if(c=='\\'&&!quote.isNull()){escaped=true;value+=c;continue;}
        if(!quote.isNull()){value+=c;if(c==quote)quote=QChar();continue;}
        if(c=='"'||c=='\''){quote=c;value+=c;}
        else if(c==','){fields.append(value.trimmed());value.clear();}else value+=c;
    }
    if(!quote.isNull()||escaped)*ok=false;fields.append(value.trimmed());return fields;
}
QString protocol(QString value){value=value.trimmed().toLower();if(value=="shadowsocks")return "ss";if(value=="socks"||value=="socks5-tls")return "socks5";if(value=="https")return "http";return value;}
std::optional<bool> boolean(const QString &value,bool uri=false){
    const auto v=uri?value:value.toLower();
    if(v=="true"||(uri&&v=="1"))return true;
    if(v=="false"||(uri&&v=="0"))return false;
    return std::nullopt;
}
int assignment(const QString &field){return field.startsWith('"')||field.startsWith('\'')?-1:field.indexOf('=');}
QString userInfo(const QUrl &url){auto auth=url.userName(QUrl::FullyDecoded);if(url.userInfo(QUrl::FullyEncoded).contains(':'))auth+=':'+url.password(QUrl::FullyDecoded);return auth;}
void issue(QStringList &issues,const QString &message){if(!issues.contains(message))issues.append(message);}
void append(Result &r,QJsonObject node,QJsonObject original,QStringList issues={}){
    if(r.nodes.size()>=2000){r.error="节点数量超过 2000；原节点保持不变。";return;}
    if(node.value("name").toString().isEmpty())node["name"]=node.value("server").toString()+":"+node.value("port").toVariant().toString();
    // Reality requires uTLS in Mihomo. Some INI clients omit the implicit
    // fingerprint; make Swirl's default explicit and retain an inspectable note.
    if(node.contains("reality-opts")&&!node.contains("client-fingerprint")){
        node["client-fingerprint"]="chrome";original["_swirl-default-client-fingerprint"]=true;
    }
    r.nodes.append(node);r.originals.append(original);r.issues.append(issues);
}
bool endpoint(const QString &text,QString &host,int &port){
    const QUrl url("tcp://"+text,QUrl::StrictMode);host=url.host();port=url.port(-1);
    return url.isValid()&&!host.isEmpty()&&port>0&&port<=65535&&url.userInfo().isEmpty()&&url.path().isEmpty()&&!url.hasQuery()&&!url.hasFragment();
}
void transport(QJsonObject &node,const QString &network,const QString &path,const QString &host,QStringList &issues){
    if(network.isEmpty()||network=="tcp")return;
    node["network"]=network;
    if(network=="ws")node["ws-opts"]=QJsonObject{{"path",path.isEmpty()?"/":path},{"headers",host.isEmpty()?QJsonObject():QJsonObject{{"Host",host}}}};
    else if(network=="grpc")node["grpc-opts"]=QJsonObject{{"grpc-service-name",path}};
    else if(network=="h2")node["h2-opts"]=QJsonObject{{"path",path.isEmpty()?"/":path},{"host",host.isEmpty()?QJsonArray():QJsonArray{host}}};
    else issue(issues,"此传输层尚未完成到 Mihomo 的映射。");
}
void uri(Result &r,const QString &line){
    const auto split=line.indexOf("://");if(split<1){r.error="通用订阅中存在无效 URI；未导入任何节点。";return;}
    const auto scheme=line.left(split).toLower();QJsonObject node;QStringList issues;
    if(scheme=="vmess"){
        const auto json=NodeImporter::strictJsonObject(base64(line.mid(split+3).toUtf8()));
        if(json.isEmpty()){r.error="VMess URI 需要有效的 Base64 JSON。";return;}
        node={{"name",json.value("ps")},{"type","vmess"},{"server",json.value("add")},{"port",json.value("port")},{"uuid",json.value("id")},{"alterId",json.value("aid").toVariant().toInt()},{"cipher",json.value("scy").toString("auto")}};
        const auto tls=json.value("tls").toString();node["tls"]=tls=="tls";
        node["servername"]=json.value("sni");
        transport(node,json.value("net").toString(),json.value("path").toString(),json.value("host").toString(),issues);
        if(json.value("type").toString()!="none"&&!json.value("type").toString().isEmpty())issue(issues,"VMess URI 的头部伪装尚未映射。");
        const QSet<QString> known{"v","ps","add","port","id","aid","scy","net","type","host","path","tls","sni","alpn","fp"};
        for(auto it=json.begin();it!=json.end();++it)if(!known.contains(it.key()))issue(issues,"VMess URI 包含未映射扩展，原始参数已保留。");
        if(json.contains("alpn"))node["alpn"]=QJsonArray::fromStringList(json.value("alpn").toString().split(',',Qt::SkipEmptyParts));
        if(json.contains("fp"))node["client-fingerprint"]=json.value("fp");
        append(r,node,QJsonObject{{"uri",line},{"vmess",json}},issues);return;
    }
    if(scheme=="ssr"){
        const auto decoded=QString::fromUtf8(base64(line.mid(split+3).toUtf8()));const auto queryAt=decoded.indexOf("/?");const auto main=decoded.left(queryAt<0?decoded.size():queryAt);
        const auto fields=main.split(':');if(fields.size()!=6){r.error="SSR URI 格式无效；IPv6 旧式冒号格式需提供无歧义配置。";return;}
        QUrlQuery q(queryAt<0?QString():decoded.mid(queryAt+2));
        node={{"name",QString::fromUtf8(base64(q.queryItemValue("remarks").toUtf8()))},{"type","ssr"},{"server",fields[0]},{"port",fields[1]},{"protocol",fields[2]},{"cipher",fields[3]},{"obfs",fields[4]},{"password",QString::fromUtf8(base64(fields[5].toUtf8()))}};
        for(const auto &key:{"protoparam","obfsparam"})if(q.hasQueryItem(key))node[QString(key)=="protoparam"?"protocol-param":"obfs-param"]=QString::fromUtf8(base64(q.queryItemValue(key).toUtf8()));
        for(const auto &pair:q.queryItems())if(!QStringList{"remarks","group","protoparam","obfsparam"}.contains(pair.first))issue(issues,"SSR URI 包含未映射扩展，原始参数已保留。");
        append(r,node,QJsonObject{{"uri",line}},issues);return;
    }
    QString effective=line;
    if(scheme=="ss"&&!line.mid(split+3).section('#',0,0).contains('@')){
        const auto body=line.mid(split+3).section('#',0,0);const auto decoded=QString::fromUtf8(base64(body.toUtf8()));
        if(!decoded.contains('@')){r.error="Shadowsocks URI 的编码无效。";return;}
        effective="ss://"+decoded+(line.contains('#')?"#"+line.section('#',1):QString());
    }
    const QUrl url(effective,QUrl::StrictMode);QUrlQuery q(url);
    if(!url.isValid()||url.host().isEmpty()||url.port(-1)<1||url.port()>65535){r.error="节点 URI 的服务器或端口无效。";return;}
    const auto p=protocol(scheme);if(!QStringList{"ss","trojan","vless","socks4","socks4a","socks5","http"}.contains(p)){r.error="尚未支持此 URI 协议；请提供原生 Clash 配置。";return;}
    node={{"name",url.fragment(QUrl::FullyDecoded)},{"type",p},{"server",url.host()},{"port",url.port()}};
    if(p=="ss"){
        QString auth=userInfo(url);if(!auth.contains(':'))auth=QString::fromUtf8(base64(auth.toUtf8()));
        const auto at=auth.indexOf(':');if(at<=0){r.error="SIP002 节点缺少加密方式或密码。";return;}
        node["cipher"]=auth.left(at);node["password"]=auth.mid(at+1);
    }else if(p=="trojan"){node["password"]=userInfo(url);}
    else if(p=="vless"){node["uuid"]=url.userName(QUrl::FullyDecoded);}
    else {
        node["username"]=url.userName(QUrl::FullyDecoded);node["password"]=url.password(QUrl::FullyDecoded);
        if(p!="socks4"&&p!="socks4a"&&url.password().isEmpty()&&!url.userName().isEmpty()){
            const auto auth=QString::fromUtf8(base64(url.userName(QUrl::FullyDecoded).toUtf8()));const auto at=auth.indexOf(':');
            if(at>0){node["username"]=auth.left(at);node["password"]=auth.mid(at+1);}
        }
    }
    if(p=="socks4"||p=="socks4a"){
        if(!url.path().isEmpty()&&url.path()!="/"){r.error="SOCKS4/4a URI 不支持路径参数。";return;}
        if(!q.isEmpty())issue(issues,"SOCKS4/4a URI 的查询扩展尚未映射，原始配置已保留。");
        append(r,node,QJsonObject{{"uri",line}},issues);return;
    }
    if(scheme=="https"||scheme=="socks5-tls"||p=="trojan")node["tls"]=true;
    QString network,path,host;
    const QSet<QString> known{"sni","peer","security","type","path","host","serviceName","flow","fp","pbk","sid","alpn","allowInsecure","insecure","skip-cert-verify","network","udp","plugin","encryption","headerType","quicSecurity"};
    QSet<QString> queryKeys;QJsonObject queryValues;
    for(const auto &pair:q.queryItems(QUrl::FullyDecoded)){
        const auto &key=pair.first;const auto &value=pair.second;
        if(queryKeys.contains(key)){r.error="节点 URI 含重复参数，无法安全确定配置。";return;}queryKeys.insert(key);
        if(!known.contains(key)){issue(issues,"节点 URI 包含未映射选项，原始参数已保留。");continue;}
        const auto canonical=key=="peer"?QString("sni"):key=="type"?QString("network"):key=="allowInsecure"||key=="insecure"?QString("skip-cert-verify"):key=="serviceName"?QString("path"):key;
        QJsonValue typed=value;
        if(canonical=="skip-cert-verify"||canonical=="udp"){
            const auto b=boolean(value,true);if(!b){r.error="节点 URI 布尔参数无效；未应用配置。";return;}typed=*b;
        }
        if(queryValues.contains(canonical)){
            if(queryValues.value(canonical)!=typed){r.error="节点 URI 别名参数冲突；未应用配置。";return;}
            continue;
        }
        queryValues[canonical]=typed;
        if(key=="sni"||key=="peer")node["sni"]=value;
        else if(key=="security"){
            if(value=="tls"||value=="reality")node["tls"]=true;
            else if(value=="none"&&node.value("tls").toBool()){r.error="节点 URI TLS 参数冲突；未应用配置。";return;}
            else if(value!="none")issue(issues,"此 URI 安全层尚未映射。");
        }else if(key=="type"||key=="network")network=value;
        else if(key=="path"||key=="serviceName")path=value;
        else if(key=="host")host=value;
        else if(key=="flow")node["flow"]=value;
        else if(key=="fp")node["client-fingerprint"]=value;
        else if(key=="alpn")node["alpn"]=QJsonArray::fromStringList(value.split(',',Qt::KeepEmptyParts));
        else if(canonical=="skip-cert-verify")node["skip-cert-verify"]=typed;
        else if(key=="udp")node["udp"]=typed;
        else if(key=="pbk"||key=="sid"){auto reality=node.value("reality-opts").toObject();reality[key=="pbk"?"public-key":"short-id"]=value;node["reality-opts"]=reality;}
        else if(key=="encryption"&&value!="none")issue(issues,"VLESS URI 的加密扩展尚未映射。");
        else if((key=="headerType"||key=="quicSecurity")&&!value.isEmpty()&&value!="none")issue(issues,"URI 的附加伪装或 QUIC 加密选项尚未映射。");
        else if(key=="plugin"){
            auto fields=value.split(';');auto plugin=fields.takeFirst();QJsonObject opts;
            const bool obfs=plugin=="obfs-local"||plugin=="simple-obfs"||plugin=="obfs";
            for(const auto &field:fields){
                const auto at=field.indexOf('=');const auto rawKey=at<0?field:field.left(at);
                const auto k=obfs&&rawKey=="obfs"?QString("mode"):obfs&&rawKey=="obfs-host"?QString("host"):rawKey;
                if(k.isEmpty()||opts.contains(k)){r.error="SIP002 插件参数重复或无效；未应用配置。";return;}
                opts[k]=at<0?QJsonValue(true):QJsonValue(field.mid(at+1));
            }
            if(obfs)plugin="obfs";
            node["plugin"]=plugin;node["plugin-opts"]=opts;
        }
    }
    // A REALITY declaration must survive normalization even before a native
    // implementation exists. Missing credentials cannot turn it into TLS.
    const auto security=queryValues.value("security").toString();
    if(security=="reality"){
        if(node.value("reality-opts").toObject().value("public-key").toString().trimmed().isEmpty()){
            r.error="节点 URI REALITY 缺少公钥；未降级为普通 TLS。";return;
        }
    }else if(node.contains("reality-opts")){
        r.error="节点 URI REALITY 参数与安全层冲突；未应用配置。";return;
    }
    transport(node,network,path,host,issues);append(r,node,QJsonObject{{"uri",line}},issues);
}
// Match the closed Xray subset in swirl-subscription/inspect_reality_xray.rs.
// Keep each complete source object; never pick one endpoint/user from a list.
bool xrayKeys(Result &r,const QJsonValue &value,const QStringList &allowed){
    if(!value.isObject()){r.error="Xray 参数必须为对象；未应用配置。";return false;}
    const auto object=value.toObject();
    for(auto it=object.begin();it!=object.end();++it)if(!allowed.contains(it.key())){r.error="Xray 节点含未映射字段；未丢弃字段或应用配置。";return false;}
    return true;
}
void xrayReality(Result &r,const QJsonArray &array){
    r.handled=true;r.format="Xray / V2Ray JSON";
    for(const auto &value:array){
        if(!value.isObject()){r.error="Xray 出站必须为对象；未应用配置。";return;}
        const auto raw=value.toObject();const auto kind=raw.value("protocol").toString();
        if(QStringList{"freedom","blackhole","dns"}.contains(kind)){
            // These are source policy objects, not native executable nodes.
            auto policies=r.configuration.value("outbounds").toArray();policies.append(raw);r.configuration["outbounds"]=policies;continue;
        }
        if(!xrayKeys(r,raw,{"protocol","tag","settings","streamSettings","mux"}))return;
        if(kind!="vless"||(raw.contains("tag")&&!raw.value("tag").isString())){r.error="Xray 当前仅映射明确的 VLESS REALITY 节点；未应用配置。";return;}
        if(raw.contains("mux")){
            if(!xrayKeys(r,raw.value("mux"),{"enabled"}))return;
            if(raw.value("mux").toObject().value("enabled")!=QJsonValue(false)){r.error="Xray mux 尚未支持；必须明确禁用。";return;}
        }
        if(!raw.value("settings").isObject()){r.error="Xray VLESS settings 必须为对象。";return;}
        const auto settings=raw.value("settings").toObject();QJsonObject endpoint,user;
        if(settings.contains("vnext")){
            if(!xrayKeys(r,settings,{"vnext"}))return;
            const auto endpoints=settings.value("vnext");
            if(!endpoints.isArray()||endpoints.toArray().size()!=1){r.error="Xray VLESS 必须明确包含一个端点；未选择或合并多个端点。";return;}
            if(!xrayKeys(r,endpoints.toArray().first(),{"address","port","users"}))return;
            endpoint=endpoints.toArray().first().toObject();const auto users=endpoint.value("users");
            if(!users.isArray()||users.toArray().size()!=1){r.error="Xray VLESS 必须明确包含一个用户；未选择或合并多个用户。";return;}
            if(!xrayKeys(r,users.toArray().first(),{"id","encryption","flow"}))return;
            user=users.toArray().first().toObject();
        }else{
            if(!xrayKeys(r,settings,{"address","port","id","encryption","flow"}))return;
            endpoint=settings;user=settings;
        }
        const auto port=endpoint.value("port");
        if(!endpoint.value("address").isString()||endpoint.value("address").toString()!=endpoint.value("address").toString().trimmed()||!port.isDouble()||port.toDouble()!=port.toInt(-1)||port.toInt()<1||port.toInt()>65535||!user.value("id").isString()){
            r.error="Xray VLESS 服务器、端口或 UUID 类型无效。";return;
        }
        if(user.value("encryption")!=QJsonValue(QStringLiteral("none"))){r.error="Xray VLESS encryption 必须明确为 none；未丢弃加密要求。";return;}
        if(user.contains("flow")&&!user.value("flow").isString()){r.error="Xray VLESS flow 必须为字符串。";return;}
        if(!xrayKeys(r,raw.value("streamSettings"),{"network","security","realitySettings","tcpSettings","rawSettings"}))return;
        const auto stream=raw.value("streamSettings").toObject();
        if(!QStringList{"tcp","raw"}.contains(stream.value("network").toString())){r.error="Xray REALITY 当前仅映射明确的 tcp 或 raw 传输。";return;}
        if(stream.value("security")!=QJsonValue(QStringLiteral("reality"))){r.error="Xray REALITY 安全层缺失或冲突；未降级为普通 TLS。";return;}
        if(stream.contains("tcpSettings")&&stream.contains("rawSettings")&&stream.value("tcpSettings")!=stream.value("rawSettings")){r.error="Xray tcpSettings 与 rawSettings 冲突；未覆盖原值。";return;}
        if(stream.contains("tcpSettings")||stream.contains("rawSettings")){
            const auto tcp=stream.contains("tcpSettings")?stream.value("tcpSettings"):stream.value("rawSettings");
            if(!xrayKeys(r,tcp,{"header"}))return;
            if(tcp.toObject().contains("header")){
                const auto header=tcp.toObject().value("header");if(!xrayKeys(r,header,{"type"}))return;
                if(header.toObject().value("type")!=QJsonValue(QStringLiteral("none"))){r.error="Xray TCP 头部伪装尚未支持；未丢弃原值。";return;}
            }
        }
        if(!xrayKeys(r,stream.value("realitySettings"),{"serverName","fingerprint","publicKey","password","shortId","spiderX","show"}))return;
        const auto reality=stream.value("realitySettings").toObject();
        if(reality.contains("spiderX")){r.error="Xray REALITY spiderX 行为尚未支持；未丢弃原值。";return;}
        if(reality.contains("show")&&reality.value("show")!=QJsonValue(false)){r.error="Xray REALITY 诊断扩展尚未支持；未应用配置。";return;}
        if(reality.contains("publicKey")&&reality.contains("password")&&reality.value("publicKey")!=reality.value("password")){r.error="Xray REALITY publicKey 与 password 冲突；未覆盖原值。";return;}
        const auto key=reality.contains("publicKey")?reality.value("publicKey"):reality.value("password");
        if(!key.isString()||!reality.value("serverName").isString()||!reality.value("fingerprint").isString()||!reality.value("shortId").isString()){
            r.error="Xray REALITY 公钥、SNI、指纹及 shortId 必须明确提供字符串。";return;
        }
        QJsonObject node{{"type","vless"},{"name",raw.value("tag")},{"server",endpoint.value("address")},{"port",port},{"uuid",user.value("id")},
            {"encryption","none"},{"tls",true},{"network","tcp"},{"sni",reality.value("serverName")},{"client-fingerprint",reality.value("fingerprint")},
            {"reality-opts",QJsonObject{{"public-key",key},{"short-id",reality.value("shortId")}}}};
        if(user.contains("flow"))node["flow"]=user.value("flow");
        append(r,node,raw);if(!r.error.isEmpty())return;
    }
    if(r.nodes.isEmpty())r.error="Xray 配置没有可导入的 VLESS REALITY 节点。";
}
void singBox(Result &r,const QJsonArray &array){
    r.handled=true;r.format="sing-box";
    for(const auto &value:array){
        const auto raw=value.toObject();const auto type=raw.value("type").toString();
        if(QStringList{"direct","block","dns","selector","urltest"}.contains(type)){
            auto policies=r.configuration.value("outbounds").toArray();policies.append(raw);r.configuration["outbounds"]=policies;continue;
        }
        QStringList issues;QJsonObject n{{"name",raw.value("tag")},{"type",protocol(type)},{"server",raw.value("server")},{"port",raw.value("server_port")}};
        // sing-box's SOCKS version is a string. Keep 4 versus 4a explicit so
        // destination DNS never changes silently while normalizing the node.
        const auto version=raw.value("version").toString();
        if(type=="socks"&&(version=="4"||version=="4a")){
            n["type"]="socks"+version;
            for(const auto &key:QStringList{"username","password","network"})if(raw.contains(key))n[key]=raw.value(key);
            const QSet<QString> known{"type","tag","server","server_port","version","username","password","network"};
            for(auto it=raw.begin();it!=raw.end();++it)if(!known.contains(it.key()))issue(issues,"sing-box SOCKS4/4a 含未映射扩展，原始配置已保留。");
            append(r,n,raw,issues);if(!r.error.isEmpty())return;continue;
        }
        const QMap<QString,QString> mappings{{"username","username"},{"password","password"},{"uuid","uuid"},{"method","cipher"},{"alter_id","alterId"},{"security","cipher"},{"flow","flow"},{"detour","dialer-proxy"},{"up_mbps","up"},{"down_mbps","down"}};
        for(auto it=mappings.begin();it!=mappings.end();++it)if(raw.contains(it.key()))n[it.value()]=raw.value(it.key());
        if(raw.contains("tls")&&!raw.value("tls").isObject()){
            r.error="sing-box TLS 必须为对象；未应用配置。";return;
        }
        const auto tls=raw.value("tls").toObject();
        for(const auto &key:QStringList{"enabled","insecure"})if(tls.contains(key)&&!tls.value(key).isBool()){
            r.error="sing-box TLS 布尔参数类型无效；未应用配置。";return;
        }
        for(const auto &key:QStringList{"utls","reality"})if(tls.contains(key)){
            if(!tls.value(key).isObject()){
                r.error="sing-box TLS 扩展必须为对象；未应用配置。";return;
            }
            const auto extension=tls.value(key).toObject();
            if(extension.contains("enabled")&&!extension.value("enabled").isBool()){
                r.error="sing-box TLS 扩展开关类型无效；未应用配置。";return;
            }
            if(extension.value("enabled").toBool()&&!tls.value("enabled").toBool()){
                r.error="sing-box TLS 未启用却启用了 TLS 扩展；未应用配置。";return;
            }
            const auto strings=key=="utls"?QStringList{"fingerprint"}:QStringList{"public_key","short_id"};
            for(const auto &field:strings)if(extension.contains(field)&&!extension.value(field).isString()){
                r.error="sing-box TLS 扩展字符串类型无效；未应用配置。";return;
            }
        }
        if(type=="trojan"&&tls.isEmpty())issue(issues,"sing-box Trojan 未明确配置 TLS，不能静默改变传输语义。");
        if(!tls.isEmpty()){
            n["tls"]=tls.value("enabled");n["sni"]=tls.value("server_name");n["skip-cert-verify"]=tls.value("insecure");
            if(tls.contains("alpn"))n["alpn"]=tls.value("alpn");
            const auto utls=tls.value("utls").toObject();
            if(utls.value("enabled").toBool()){
                const auto fingerprint=utls.value("fingerprint").toString();
                // sing-box defaults an enabled uTLS profile to chrome. Keep
                // that import metadata; the native gate still requires an
                // explicit supported profile in the untouched source object.
                n["client-fingerprint"]=fingerprint.isEmpty()?QString("chrome"):fingerprint;
            }else if(utls.contains("fingerprint"))issue(issues,"sing-box uTLS 未启用却含指纹要求，原始配置已保留。");
            for(const auto &key:QStringList{"fp","client-fingerprint"})if(raw.contains(key)&&utls.contains("fingerprint")&&raw.value(key)!=utls.value("fingerprint"))issue(issues,"sing-box 顶层指纹别名与 uTLS 指纹冲突，原始配置已保留。");
            const auto reality=tls.value("reality").toObject();
            if(reality.value("enabled").toBool()){
                if(!utls.value("enabled").toBool()||reality.value("public_key").toString().trimmed().isEmpty()){
                    r.error="sing-box REALITY 需要已启用的 uTLS 和公钥；未降级为普通 TLS。";return;
                }
                n["reality-opts"]=QJsonObject{{"public-key",reality.value("public_key")},{"short-id",reality.value("short_id")}};
            }
            for(auto it=tls.begin();it!=tls.end();++it)if(!QStringList{"enabled","server_name","insecure","alpn","utls","reality"}.contains(it.key()))issue(issues,"sing-box TLS 含未映射选项，原始配置已保留。");
            for(auto it=utls.begin();it!=utls.end();++it)if(!QStringList{"enabled","fingerprint"}.contains(it.key()))issue(issues,"sing-box uTLS 含未映射选项。");
            for(auto it=reality.begin();it!=reality.end();++it)if(!QStringList{"enabled","public_key","short_id"}.contains(it.key()))issue(issues,"sing-box Reality 含未映射选项。");
            if(type=="trojan"&&!tls.value("enabled").toBool())issue(issues,"未加密的 Trojan 出站尚未支持。");
        }
        if(raw.contains("transport")&&!raw.value("transport").isNull()){
            // The optional sing-box transport pointer treats null as absent.
            // Wrong JSON types must not become an empty object or default path.
            if(!raw.value("transport").isObject()){
                r.error="sing-box 传输必须为对象；未应用配置。";return;
            }
            auto t=raw.value("transport").toObject();const auto net=t.value("type").toString();
            if(!t.value("type").isString()||!QStringList{"http","ws","quic","grpc","httpupgrade"}.contains(net)){
                r.error="sing-box 传输类型缺失、无效或未识别；未降级为 TCP。";return;
            }
            QSet<QString> mapped{"type"};
            if(net=="ws")mapped.unite(QSet<QString>{"path","headers","max_early_data","early_data_header_name"});
            else if(net=="grpc")mapped.insert("service_name");
            // Go decoding leaves these optional null fields at their zero value;
            // normalize only mapped fields and retain the untouched original.
            for(const auto &key:mapped)if(key!="type"&&t.value(key).isNull())t.remove(key);
            for(const auto &key:QStringList{"path","service_name","early_data_header_name"})if(t.contains(key)&&!t.value(key).isString()){
                r.error="sing-box 传输字符串类型无效；未应用配置。";return;
            }
            if(t.contains("headers")){
                if(!t.value("headers").isObject()){
                    r.error="sing-box 传输请求头必须为对象；未应用配置。";return;
                }
                auto headers=t.value("headers").toObject();
                for(auto h=headers.begin();h!=headers.end();){
                    // A null Listable has no entries. Null string-array entries
                    // are empty strings, not an instruction to omit the header.
                    if(h.value().isNull()){h=headers.erase(h);continue;}
                    const auto value=h.value();auto values=value.isArray()?value.toArray():QJsonArray{value};
                    for(qsizetype i=0;i<values.size();++i){
                        if(values.at(i).isNull())values[i]="";
                        else if(!values.at(i).isString()){
                            r.error="sing-box 传输请求头值类型无效；未应用配置。";return;
                        }
                    }
                    if(value.isArray())h.value()=values;
                    ++h;
                }
                t["headers"]=headers;
            }
            if(t.contains("max_early_data")){
                const auto value=t.value("max_early_data");const auto count=value.toInteger(-1);
                if(!value.isDouble()||count<0||count>0xffffffffLL){
                    r.error="sing-box 传输早期数据上限必须为 uint32；未应用配置。";return;
                }
            }
            const auto path=t.value(net=="grpc"?"service_name":"path").toString();
            transport(n,net,path,{},issues);
            if(net=="ws"){auto opts=n.value("ws-opts").toObject();if(t.contains("headers"))opts["headers"]=t.value("headers");if(t.contains("max_early_data"))opts["max-early-data"]=t.value("max_early_data");if(t.contains("early_data_header_name"))opts["early-data-header-name"]=t.value("early_data_header_name");n["ws-opts"]=opts;}
            for(auto it=t.begin();it!=t.end();++it)if(!mapped.contains(it.key()))issue(issues,"sing-box 传输含未映射选项，原始配置已保留。");
        }
        const QSet<QString> known{"tag","type","server","server_port","tls","transport","username","password","uuid","method","alter_id","security","flow","detour","up_mbps","down_mbps"};
        for(auto it=raw.begin();it!=raw.end();++it)if(!known.contains(it.key()))issue(issues,"sing-box 出站包含未映射扩展，原始配置已保留。");
        if(!QStringList{"http","socks","trojan","shadowsocks","vmess","vless","hysteria2"}.contains(type))issue(issues,"此 sing-box 协议适配尚在研发中。");
        append(r,n,raw,issues);if(!r.error.isEmpty())return;
    }
    if(r.nodes.isEmpty())r.error="sing-box 配置没有可导入的远端代理节点。";
}
// A deliberately closed, complete INI profile: manual groups and domain rules.
// Source text is retained independently. Any additional section/option keeps
// the profile unexecutable rather than silently inheriting different semantics.
QJsonObject iniProfile(const QString &document,const QJsonArray &nodes){
    QString section;QJsonArray groups,rules;QSet<QString> proxyNames,nodeNames,groupNames,declaredProxyNames;bool final=false,hasRules=false;
    auto nameValid=[](const QString &name){return !name.isEmpty()&&!name.contains(',')&&!name.contains('=')&&!name.contains('\n');};
    for(const auto &value:nodes){const auto name=value.toObject().value("name").toString();if(!nameValid(name)||nodeNames.contains(name))return {};nodeNames.insert(name);}
    for(const auto &raw:document.split('\n')){
        const auto line=raw.trimmed();if(line.isEmpty()||line.startsWith('#')||line.startsWith(';')||line.startsWith("//"))continue;
        if(line.startsWith('[')){
            const auto close=line.indexOf(']');if(close<0)return {};section=line.mid(1,close-1).trimmed().toLower();
            if(section!="proxy"&&section!="proxy group"&&section!="rule")return {};
            if(section=="rule")hasRules=true;continue;
        }
        if(section=="proxy"||section=="proxy group"){
            const auto equal=line.indexOf('=');if(equal<1)return {};const auto name=clean(line.left(equal));if(!nameValid(name))return {};
            bool ok=false;const auto fields=csv(line.mid(equal+1),&ok);if(!ok||fields.isEmpty())return {};const auto kind=clean(fields.first()).toLower();
            if(section=="proxy"){
                if(declaredProxyNames.contains(name))return {};declaredProxyNames.insert(name);
                if(kind=="direct"||kind=="reject"){
                    if(fields.size()!=1||name!=(kind=="direct"?"DIRECT":"REJECT"))return {};
                }else {if(proxyNames.contains(name))return {};proxyNames.insert(name);}
            }else {
                if(kind!="select"||fields.size()<2||groupNames.contains(name))return {};groupNames.insert(name);QJsonArray members;QSet<QString> seen;
                for(auto it=fields.cbegin()+1;it!=fields.cend();++it){const auto member=clean(*it);if(!nameValid(member)||seen.contains(member))return {};seen.insert(member);members.append(member);}
                groups.append(QJsonObject{{"name",name},{"type","select"},{"proxies",members}});
            }
        }else if(section=="rule"){
            if(final)return {};bool ok=false;auto fields=csv(line,&ok);if(!ok||fields.isEmpty())return {};for(auto &field:fields)field=clean(field);
            const auto kind=fields.first().toUpper();
            if(kind=="FINAL"){
                if(fields.size()!=2||!nameValid(fields[1]))return {};rules.append("MATCH,"+fields[1]);final=true;
            }else {
                if(!QStringList{"DOMAIN","DOMAIN-SUFFIX","DOMAIN-KEYWORD"}.contains(kind)||fields.size()!=3||fields[1].isEmpty()||fields[1].contains(',')||!nameValid(fields[2]))return {};
                rules.append(kind+","+fields[1]+","+fields[2]);
            }
        }else return {};
    }
    if(!hasRules||!final||proxyNames!=nodeNames)return {};
    return {{"proxy-groups",groups},{"rules",rules}};
}
void ini(Result &r,const QString &document){
    r.handled=true;r.format="Surge / Surfboard / Loon";r.configurationFormat="ini";QString section;
    QSet<QString> sections;
    const bool sectioned=document.contains(QRegularExpression("^\\s*\\[",QRegularExpression::MultilineOption));
    auto preserve=[&]{r.configuration["document"]=document;};
    for(const auto &rawLine:document.split('\n')){
        const auto line=rawLine.trimmed();if(line.isEmpty()||line.startsWith('#')||line.startsWith(';')||line.startsWith("//"))continue;
        if(line.startsWith('[')){
            const auto close=line.indexOf(']');const auto name=line.mid(1,close-1).trimmed();const auto tail=line.mid(close+1).trimmed();
            if(close<0||name.isEmpty()||name.toUtf8().size()>128||name.contains('[')||name.contains(']')||name.contains('\t')
                ||(!tail.isEmpty()&&!tail.startsWith('#')&&!tail.startsWith(';'))){r.error="INI 区段标题无效；未应用配置。";return;}
            section="["+name.toLower()+"]";
            if(sections.contains(section)||sections.size()>=256){r.error="INI 区段重复或超过数量限制；未应用配置。";return;}
            sections.insert(section);
            if(section=="[server_local]")r.format="Quantumult X";
            if(section!="[proxy]"&&section!="[server_local]")preserve();
            continue;
        }
        if(sectioned&&section.isEmpty()){r.error="INI 内容缺少所属区段；未应用配置。";return;}
        if(!section.isEmpty()&&section!="[proxy]"&&section!="[server_local]")continue;
        const auto equal=line.indexOf('=');if(equal<=0){r.error="订阅代理行缺少赋值符号；未导入任何节点。";return;}
        bool ok;auto fields=csv(line.mid(equal+1),&ok);if(!ok||fields.isEmpty()){r.error="订阅代理行的引号或字段不完整。";return;}
        const auto left=clean(line.left(equal));const bool qx=section=="[server_local]"||(QStringList{"shadowsocks","trojan","vmess","http","socks5"}.contains(left.toLower())&&fields.first().contains(':'));
        if(left.isEmpty()){r.error="INI 节点名称或协议为空；未应用配置。";return;}
        const bool loonObfs=!qx&&clean(fields.first()).compare("shadowsocks",Qt::CaseInsensitive)==0&&fields.size()>=7
            &&std::all_of(fields.cbegin()+3,fields.cbegin()+7,[](const QString &f){return assignment(f)<0;});
        QJsonObject n;QStringList issues;QString host,network,path,wsHost,security;bool networkSet=false;int port=0;
        if(qx){r.format="Quantumult X";if(!endpoint(clean(fields.takeFirst()),host,port)){r.error="Quantumult X 节点地址无效。";return;}n["type"]=protocol(left);if(left.compare("https",Qt::CaseInsensitive)==0||left.compare("socks5-tls",Qt::CaseInsensitive)==0)n["tls"]=true;}
        else {n["name"]=left;const auto type=clean(fields.takeFirst());n["type"]=protocol(type);if(type.compare("https",Qt::CaseInsensitive)==0||type.compare("socks5-tls",Qt::CaseInsensitive)==0)n["tls"]=true;if(QStringList{"direct","reject","reject-tinygif"}.contains(n.value("type").toString())){preserve();continue;}if(fields.size()<2){r.error="INI 节点缺少服务器或端口。";return;}host=clean(fields.takeFirst());port=clean(fields.takeFirst()).toInt();}
        n["server"]=host;n["port"]=port;const auto p=n.value("type").toString();
        auto setNetwork=[&](const QString &value){
            if(value.isEmpty() || (networkSet && network!=value)){r.error="INI 传输参数冲突或为空；未应用配置。";return false;}
            network=value;networkSet=true;return true;
        };
        auto setSecurity=[&](const QString &value){
            if(!security.isEmpty() && security!=value){r.error="INI 安全传输参数冲突；未应用配置。";return false;}
            security=value;return true;
        };
        auto setTls=[&](bool enabled){
            if(n.contains("tls")&&n.value("tls")!=QJsonValue(enabled)){r.error="INI TLS 参数冲突；未应用配置。";return false;}
            n["tls"]=enabled;return true;
        };
        if(p=="trojan")n["tls"]=true;
        int positional=0;
        QSet<QString> seenKeys;
        for(const auto &rawField:fields){
            const auto field=clean(rawField);auto at=assignment(rawField);
            // A quoted positional password may contain both ':' and '='.
            if(at<0&&!rawField.startsWith('"')&&!rawField.startsWith('\'')&&!qx&&p=="trojan"&&n.contains("password")){
                const auto colon=field.indexOf(':');
                if(colon>0&&QRegularExpression("^[A-Za-z0-9_-]+$").match(field.left(colon).trimmed()).hasMatch())at=colon;
            }
            if(at<0){
                if(p=="ss"){
                    const auto key=positional==0?QStringLiteral("cipher"):positional==1?QStringLiteral("password"):
                        loonObfs&&positional==2?QStringLiteral("obfs"):loonObfs&&positional==3?QStringLiteral("obfs-host"):QString();
                    ++positional;
                    if(key.isEmpty()){issue(issues,"INI 节点存在未映射的位置参数。");continue;}
                    if(seenKeys.contains(key)||n.contains(key)){r.error="INI 节点含重复参数，无法安全确定配置。";return;}seenKeys.insert(key);
                    if(key=="obfs"){n["plugin"]="obfs";auto opts=n.value("plugin-opts").toObject();opts["mode"]=field;n["plugin-opts"]=opts;}
                    else if(key=="obfs-host"){auto opts=n.value("plugin-opts").toObject();opts["host"]=field;n["plugin-opts"]=opts;}
                    else n[key]=field;
                }
                else {
                    const auto key=p=="trojan"&&positional==0?QString("password"):(p=="vless"||p=="vmess")&&positional==0?QString("uuid"):(p=="http"||p=="socks5")&&positional<2?(positional==0?QString("username"):QString("password")):QString();
                    ++positional;
                    if(key.isEmpty())issue(issues,"INI 节点存在未映射的位置参数。");
                    else {if(seenKeys.contains(key)||n.contains(key)){r.error="INI 节点含重复参数，无法安全确定配置。";return;}seenKeys.insert(key);n[key]=field;}
                }
                continue;
            }
            const auto key=field.left(at).trimmed().toLower(),value=clean(field.mid(at+1));
            const auto canonical=key=="encrypt-method"||key=="method"?QString("cipher"):key=="tls-host"||key=="tls-name"?QString("sni"):key=="over-tls"?QString("tls"):key=="udp-relay"?QString("udp"):key=="fast-open"?QString("tfo"):key=="tls-verification"?QString("skip-cert-verify"):key=="obfs-name"&&p=="ss"?QString("obfs"):p=="vmess"&&(key=="username"||(qx&&key=="password"))?QString("uuid"):key=="ws-path"||(key=="obfs-uri"&&p!="ss")?QString("path"):key;
            if(seenKeys.contains(canonical)){r.error="INI 节点含重复参数，无法安全确定配置。";return;}seenKeys.insert(canonical);
            const bool isBoolean=QStringList{"tls","over-tls","skip-cert-verify","tls-verification","udp-relay","udp","tfo","fast-open","ws","aead"}.contains(key);
            const auto parsedBoolean=boolean(value);
            if(isBoolean&&!parsedBoolean){r.error="INI 布尔参数无效；未应用配置。";return;}
            const bool enabled=parsedBoolean.value_or(false);
            if(key=="tag")n["name"]=value;
            else if(key=="username")n[p=="vmess"?"uuid":"username"]=value;
            else if(key=="password")n[p=="vmess"&&qx?"uuid":"password"]=value;
            else if(key=="uuid")n["uuid"]=value;
            else if(key=="encrypt-method"||key=="method"||key=="cipher")n["cipher"]=value;
            else if(key=="sni"||key=="tls-host"||key=="tls-name")n["sni"]=value;
            else if(key=="tls"||key=="over-tls"){if(!setTls(enabled))return;}
            else if(key=="skip-cert-verify")n[key]=enabled;
            else if(key=="tls-verification")n["skip-cert-verify"]=!enabled;
            else if(key=="udp-relay"||key=="udp")n["udp"]=enabled;
            else if(key=="tfo"||key=="fast-open")n["tfo"]=enabled;
            else if(key=="flow")n["flow"]=value;
            else if(key=="transport"){
                if(value=="tls"||value=="reality"){
                    if(!setSecurity(value)||!setTls(true))return;
                    if(value=="reality"&&!n.contains("reality-opts"))n["reality-opts"]=QJsonObject();
                }else if(value=="wss"){if(!setNetwork("ws")||!setTls(true))return;}
                else if(!setNetwork(value))return;
            }
            else if(key=="public-key"||key=="short-id"){if(!setSecurity("reality"))return;auto reality=n.value("reality-opts").toObject();reality[key]=value;n["reality-opts"]=reality;if(!setTls(true))return;}
            else if(key=="client-fingerprint")n[key]=value;
            else if(key=="underlying-proxy")n["dialer-proxy"]=value;
            else if(key=="ws"){if(!setNetwork(enabled?"ws":"tcp"))return;}
            else if(key=="obfs-uri"&&p=="ss"){auto opts=n.value("plugin-opts").toObject();opts[key]=value;n["plugin-opts"]=opts;issue(issues,"INI Shadowsocks 混淆路径尚未支持，原始配置已保留。");}
            else if(key=="ws-path"||key=="obfs-uri")path=value;
            else if(key=="ws-headers"){
                const auto header=value.section(':',0,0);if(header.compare("Host",Qt::CaseInsensitive)==0)wsHost=value.section(':',1);else issue(issues,"INI WebSocket 头部映射尚未完成。");
            }else if(key=="obfs"||(key=="obfs-name"&&p=="ss")){
                if(p=="ss"){n["plugin"]="obfs";auto opts=n.value("plugin-opts").toObject();opts["mode"]=value;n["plugin-opts"]=opts;}
                else if(value=="ws"||value=="wss"){if(!setNetwork("ws"))return;if(value=="wss"&&!setTls(true))return;}else issue(issues,"INI 节点的伪装传输尚未映射。");
            }else if(key=="obfs-host"){
                if(p=="ss"){auto opts=n.value("plugin-opts").toObject();opts["host"]=value;n["plugin-opts"]=opts;}else wsHost=value;
            }else if(key=="alterid")n["alterId"]=value.toInt();
            else if(key=="aead"){if(!enabled)issue(issues,"旧 VMess 非 AEAD 行为需要原生 Clash 配置。");}
            else if(key!="group")issue(issues,"INI 节点包含未映射选项，原始配置已保留。");
        }
        if(security=="reality"&&n.value("reality-opts").toObject().value("public-key").toString().isEmpty()) {
            r.error="INI REALITY 缺少公钥；未降级为普通 TLS。";return;
        }
        if(p=="trojan"){
            if(n.contains("tls")&&!n.value("tls").toBool())issue(issues,"未加密的 Trojan 传输尚未支持。");
            else n["tls"]=true;
        }
        transport(n,network,path,wsHost,issues);append(r,n,QJsonObject{{"line",line}},issues);if(!r.error.isEmpty())return;
    }
    if(r.nodes.isEmpty())r.error="此 INI 配置不包含可导入的代理节点。";
    else if(!r.configuration.isEmpty())r.executionConfiguration=iniProfile(document,r.nodes);
}
}

SubscriptionNormalizer::Result SubscriptionNormalizer::normalize(const QByteArray &document,int depth){
    Result r;if(depth>2){r.error="订阅编码嵌套过深。";return r;}
    QStringDecoder decoder(QStringDecoder::Utf8,QStringConverter::Flag::Stateless);const QString completeText=decoder(document);
    if(decoder.hasError()){r.error="订阅不是合法 UTF-8 文本；未应用配置。";return r;}
    for(const auto c:completeText)if(c.category()==QChar::Other_Control&&c!='\t'&&c!='\r'&&c!='\n'){
        r.error="订阅含非法控制字符；未应用配置。";return r;
    }
    auto bytes=document.trimmed();if(bytes.startsWith("\xef\xbb\xbf"))bytes.remove(0,3);
    if(bytes.startsWith("\xef\xbb\xbf")){r.error="订阅含重复 UTF-8 BOM；未应用配置。";return r;}
    r.decodedDocument=bytes;
    const auto json=QJsonDocument::fromJson(bytes);
    if(json.isObject()&&json.object().value("outbounds").isArray()){
        const auto outbounds=json.object().value("outbounds").toArray();
        const bool xray=std::any_of(outbounds.cbegin(),outbounds.cend(),[](const QJsonValue &node){return node.toObject().contains("protocol");});
        r.configurationFormat=xray?"xray-v2ray-json":"sing-box";r.configuration=json.object();r.configuration.remove("outbounds");
        if(xray)xrayReality(r,outbounds);else singBox(r,outbounds);
        if(!r.configuration.isEmpty())r.configuration=json.object();
        return r;
    }
    const auto text=QString::fromUtf8(bytes);
    if(text.startsWith("STATUS=")){
        const auto end=text.indexOf('\n');if(end<0||end>4096){r.error="Shadowrocket 状态头无效。";return r;}
        r=normalize(text.mid(end+1).toUtf8(),depth+1);
        if(r.decodedDocument.isEmpty())r.decodedDocument=text.mid(end+1).toUtf8();
        if(!r.originals.isEmpty())r.originals[0]["subscription-status-header"]=text.left(end);
        return r;
    }
    const auto firstContent=[&]{for(const auto &line:text.split('\n')){const auto value=line.trimmed();if(!value.isEmpty()&&!value.startsWith('#')&&!value.startsWith(';')&&!value.startsWith("//"))return value;}return QString();}();
    const bool iniHeading=QRegularExpression("^\\[\\s*[A-Za-z][A-Za-z0-9 _-]*(?:\\]|$)").match(firstContent).hasMatch();
    if(iniHeading&&!json.isArray()){ini(r,text);return r;}
    if(QRegularExpression("^(ss|ssr|trojan|vmess|vless|socks4a|socks4|socks5|socks5-tls|socks|http|https)://",QRegularExpression::CaseInsensitiveOption).match(text).hasMatch()){
        r.handled=true;r.format="通用 URI / Shadowrocket";
        for(const auto &line:text.split('\n')){const auto value=line.trimmed();if(value.isEmpty()||value.startsWith('#'))continue;uri(r,value);if(!r.error.isEmpty())break;}return r;
    }
    if(QRegularExpression("^(shadowsocks|trojan|vmess|http|socks5)\\s*=",QRegularExpression::CaseInsensitiveOption).match(text).hasMatch()){ini(r,text);return r;}
    if(QRegularExpression("^[^=\\r\\n]{1,128}\\s*=\\s*(Shadowsocks|Trojan|VMess|VLESS|socks5|http|https|ss)\\s*,",QRegularExpression::CaseInsensitiveOption|QRegularExpression::MultilineOption).match(text).hasMatch()){ini(r,text);return r;}
    const auto decoded=base64(bytes);
    if(!decoded.isEmpty()&&decoded!=bytes&&(decoded.contains("://")||decoded.contains("proxies:")||decoded.contains("[")||decoded.contains("outbounds"))){
        r=normalize(decoded,depth+1);if(r.decodedDocument.isEmpty())r.decodedDocument=decoded;r.format="Base64 / "+(r.format.isEmpty()?QString("Clash"):r.format);return r;
    }
    r.format="Clash YAML / JSON";return r;
}
