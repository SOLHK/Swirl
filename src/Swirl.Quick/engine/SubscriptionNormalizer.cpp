#include "SubscriptionNormalizer.h"
#include "NodeImporter.h"
#include <QJsonDocument>
#include <QUrl>
#include <QUrlQuery>
#include <QRegularExpression>
#include <QSet>

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
        else if(c==','){fields.append(clean(value));value.clear();}else value+=c;
    }
    if(!quote.isNull()||escaped)*ok=false;fields.append(clean(value));return fields;
}
QString protocol(QString value){value=value.trimmed().toLower();if(value=="shadowsocks")return "ss";if(value=="socks"||value=="socks5-tls")return "socks5";if(value=="https")return "http";return value;}
bool yes(const QString &v){return v=="1"||v.compare("true",Qt::CaseInsensitive)==0;}
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
    if(scheme=="https"||p=="trojan")node["tls"]=true;
    QString network,path,host;
    const QSet<QString> known{"sni","peer","security","type","path","host","serviceName","flow","fp","pbk","sid","alpn","allowInsecure","insecure","udp","plugin","encryption","headerType","quicSecurity"};
    QSet<QString> queryKeys;
    for(const auto &pair:q.queryItems(QUrl::FullyDecoded)){
        const auto &key=pair.first;const auto &value=pair.second;
        if(queryKeys.contains(key)){r.error="节点 URI 含重复参数，无法安全确定配置。";return;}queryKeys.insert(key);
        if(!known.contains(key)){issue(issues,"节点 URI 包含未映射选项，原始参数已保留。");continue;}
        if(key=="sni"||key=="peer")node["sni"]=value;
        else if(key=="security"){
            if(value=="tls"||value=="reality")node["tls"]=true;
            else if(value!="none")issue(issues,"此 URI 安全层尚未映射。");
        }else if(key=="type")network=value;
        else if(key=="path"||key=="serviceName")path=value;
        else if(key=="host")host=value;
        else if(key=="flow")node["flow"]=value;
        else if(key=="fp")node["client-fingerprint"]=value;
        else if(key=="alpn")node["alpn"]=QJsonArray::fromStringList(value.split(',',Qt::SkipEmptyParts));
        else if(key=="allowInsecure"||key=="insecure")node["skip-cert-verify"]=yes(value);
        else if(key=="udp")node["udp"]=yes(value);
        else if(key=="pbk"||key=="sid"){auto reality=node.value("reality-opts").toObject();reality[key=="pbk"?"public-key":"short-id"]=value;node["reality-opts"]=reality;}
        else if(key=="encryption"&&value!="none")issue(issues,"VLESS URI 的加密扩展尚未映射。");
        else if((key=="headerType"||key=="quicSecurity")&&!value.isEmpty()&&value!="none")issue(issues,"URI 的附加伪装或 QUIC 加密选项尚未映射。");
        else if(key=="plugin"){
            auto fields=value.split(';');auto plugin=fields.takeFirst();QJsonObject opts;
            for(const auto &field:fields){const auto at=field.indexOf('=');const auto k=at<0?field:field.left(at);opts[k]=at<0?QJsonValue(true):QJsonValue(field.mid(at+1));}
            if(plugin=="obfs-local"||plugin=="simple-obfs"){plugin="obfs";if(opts.contains("obfs"))opts["mode"]=opts.take("obfs");if(opts.contains("obfs-host"))opts["host"]=opts.take("obfs-host");}
            node["plugin"]=plugin;node["plugin-opts"]=opts;
        }
    }
    transport(node,network,path,host,issues);append(r,node,QJsonObject{{"uri",line}},issues);
}
void singBox(Result &r,const QJsonArray &array){
    r.handled=true;r.format="sing-box";
    for(const auto &value:array){
        const auto raw=value.toObject();const auto type=raw.value("type").toString();
        if(QStringList{"direct","block","dns","selector","urltest"}.contains(type))continue;
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
        const auto tls=raw.value("tls").toObject();
        if(type=="trojan"&&tls.isEmpty())issue(issues,"sing-box Trojan 未明确配置 TLS，不能静默改变传输语义。");
        if(!tls.isEmpty()){
            n["tls"]=tls.value("enabled");n["sni"]=tls.value("server_name");n["skip-cert-verify"]=tls.value("insecure");
            if(tls.contains("alpn"))n["alpn"]=tls.value("alpn");
            const auto utls=tls.value("utls").toObject();if(utls.value("enabled").toBool())n["client-fingerprint"]=utls.value("fingerprint");
            const auto reality=tls.value("reality").toObject();if(reality.value("enabled").toBool())n["reality-opts"]=QJsonObject{{"public-key",reality.value("public_key")},{"short-id",reality.value("short_id")}};
            for(auto it=tls.begin();it!=tls.end();++it)if(!QStringList{"enabled","server_name","insecure","alpn","utls","reality"}.contains(it.key()))issue(issues,"sing-box TLS 含未映射选项，原始配置已保留。");
            for(auto it=utls.begin();it!=utls.end();++it)if(!QStringList{"enabled","fingerprint"}.contains(it.key()))issue(issues,"sing-box uTLS 含未映射选项。");
            for(auto it=reality.begin();it!=reality.end();++it)if(!QStringList{"enabled","public_key","short_id"}.contains(it.key()))issue(issues,"sing-box Reality 含未映射选项。");
            if(type=="trojan"&&!tls.value("enabled").toBool())issue(issues,"未加密的 Trojan 出站尚未支持。");
        }
        const auto t=raw.value("transport").toObject();if(!t.isEmpty()){
            const auto net=t.value("type").toString();const auto path=t.value(net=="grpc"?"service_name":"path").toString();
            transport(n,net,path,{},issues);
            if(net=="ws"){auto opts=n.value("ws-opts").toObject();if(t.contains("headers"))opts["headers"]=t.value("headers");if(t.contains("max_early_data"))opts["max-early-data"]=t.value("max_early_data");if(t.contains("early_data_header_name"))opts["early-data-header-name"]=t.value("early_data_header_name");n["ws-opts"]=opts;}
            for(auto it=t.begin();it!=t.end();++it)if(!QStringList{"type","path","service_name","headers","max_early_data","early_data_header_name"}.contains(it.key()))issue(issues,"sing-box 传输含未映射选项，原始配置已保留。");
        }
        const QSet<QString> known{"tag","type","server","server_port","tls","transport","username","password","uuid","method","alter_id","security","flow","detour","up_mbps","down_mbps"};
        for(auto it=raw.begin();it!=raw.end();++it)if(!known.contains(it.key()))issue(issues,"sing-box 出站包含未映射扩展，原始配置已保留。");
        if(!QStringList{"http","socks","trojan","shadowsocks","vmess","vless","hysteria2"}.contains(type))issue(issues,"此 sing-box 协议适配尚在研发中。");
        append(r,n,raw,issues);if(!r.error.isEmpty())return;
    }
    if(r.nodes.isEmpty())r.error="sing-box 配置没有可导入的远端代理节点。";
}
void ini(Result &r,const QString &document){
    r.handled=true;r.format="Surge / Surfboard / Loon";QString section;
    for(const auto &rawLine:document.split('\n')){
        const auto line=rawLine.trimmed();if(line.isEmpty()||line.startsWith('#')||line.startsWith(';')||line.startsWith("//"))continue;
        if(line.startsWith('[')){section=line.toLower();if(section=="[server_local]")r.format="Quantumult X";continue;}
        if(!section.isEmpty()&&section!="[proxy]"&&section!="[server_local]")continue;
        const auto equal=line.indexOf('=');if(equal<=0){r.error="订阅代理行缺少赋值符号；未导入任何节点。";return;}
        bool ok;auto fields=csv(line.mid(equal+1),&ok);if(!ok||fields.size()<2){r.error="订阅代理行的引号或字段不完整。";return;}
        const auto left=clean(line.left(equal));const bool qx=section=="[server_local]"||(QStringList{"shadowsocks","trojan","vmess","http","socks5"}.contains(left.toLower())&&fields.first().contains(':'));
        QJsonObject n;QStringList issues;QString host,network,path,wsHost;int port=0;
        if(qx){r.format="Quantumult X";if(!endpoint(fields.takeFirst(),host,port)){r.error="Quantumult X 节点地址无效。";return;}n["type"]=protocol(left);}
        else {n["name"]=left;const auto type=fields.takeFirst();n["type"]=protocol(type);if(type.compare("https",Qt::CaseInsensitive)==0||type.compare("socks5-tls",Qt::CaseInsensitive)==0)n["tls"]=true;if(QStringList{"direct","reject","reject-tinygif"}.contains(n.value("type").toString()))continue;if(fields.size()<2){r.error="INI 节点缺少服务器或端口。";return;}host=clean(fields.takeFirst());port=fields.takeFirst().toInt();}
        n["server"]=host;n["port"]=port;const auto p=n.value("type").toString();
        int positional=0;
        QSet<QString> seenKeys;
        for(const auto &field:fields){
            const auto at=field.indexOf('=');if(at<0){
                if(p=="ss"){n[positional++==0?"cipher":"password"]=field;if(positional>2)issue(issues,"INI 节点存在未映射的位置参数。");}
                else if(p=="trojan"&&positional++==0)n["password"]=field;
                else if((p=="vless"||p=="vmess")&&positional++==0)n["uuid"]=field;
                else if((p=="http"||p=="socks5")&&positional<2)n[positional++==0?"username":"password"]=field;
                else issue(issues,"INI 节点存在未映射的位置参数。");continue;
            }
            const auto key=field.left(at).trimmed().toLower(),value=clean(field.mid(at+1));
            if(seenKeys.contains(key)){r.error="INI 节点含重复参数，无法安全确定配置。";return;}seenKeys.insert(key);
            if(key=="tag")n["name"]=value;
            else if(key=="username")n[p=="vmess"?"uuid":"username"]=value;
            else if(key=="password")n[p=="vmess"&&qx?"uuid":"password"]=value;
            else if(key=="uuid")n["uuid"]=value;
            else if(key=="encrypt-method"||key=="method")n["cipher"]=value;
            else if(key=="sni"||key=="tls-host"||key=="tls-name")n["sni"]=value;
            else if(key=="tls"||key=="over-tls")n["tls"]=yes(value);
            else if(key=="skip-cert-verify")n[key]=yes(value);
            else if(key=="tls-verification")n["skip-cert-verify"]=!yes(value);
            else if(key=="udp-relay"||key=="udp")n["udp"]=yes(value);
            else if(key=="tfo"||key=="fast-open")n["tfo"]=yes(value);
            else if(key=="flow")n["flow"]=value;
            else if(key=="transport"){
                if(value=="tls")n["tls"]=true;
                else if(value=="reality"){n["tls"]=true;}
                else network=value;
            }
            else if(key=="public-key"||key=="short-id"){auto reality=n.value("reality-opts").toObject();reality[key]=value;n["reality-opts"]=reality;n["tls"]=true;}
            else if(key=="client-fingerprint")n[key]=value;
            else if(key=="underlying-proxy")n["dialer-proxy"]=value;
            else if(key=="ws")network=yes(value)?"ws":QString();
            else if(key=="ws-path"||key=="obfs-uri")path=value;
            else if(key=="ws-headers"){
                const auto header=value.section(':',0,0);if(header.compare("Host",Qt::CaseInsensitive)==0)wsHost=value.section(':',1);else issue(issues,"INI WebSocket 头部映射尚未完成。");
            }else if(key=="obfs"){
                if(p=="ss"){n["plugin"]="obfs";auto opts=n.value("plugin-opts").toObject();opts["mode"]=value;n["plugin-opts"]=opts;}
                else if(value=="ws"||value=="wss"){network="ws";if(value=="wss")n["tls"]=true;}else issue(issues,"INI 节点的伪装传输尚未映射。");
            }else if(key=="obfs-host"){
                if(p=="ss"){auto opts=n.value("plugin-opts").toObject();opts["host"]=value;n["plugin-opts"]=opts;}else wsHost=value;
            }else if(key=="alterid")n["alterId"]=value.toInt();
            else if(key=="aead"){if(!yes(value))issue(issues,"旧 VMess 非 AEAD 行为需要原生 Clash 配置。");}
            else if(key!="group")issue(issues,"INI 节点包含未映射选项，原始配置已保留。");
        }
        if(p=="trojan"){
            if(n.contains("tls")&&!n.value("tls").toBool())issue(issues,"未加密的 Trojan 传输尚未支持。");
            else n["tls"]=true;
        }
        transport(n,network,path,wsHost,issues);append(r,n,QJsonObject{{"line",line}},issues);if(!r.error.isEmpty())return;
    }
    if(r.nodes.isEmpty())r.error="此 INI 配置不包含可导入的代理节点。";
}
}

SubscriptionNormalizer::Result SubscriptionNormalizer::normalize(const QByteArray &document,int depth){
    Result r;if(depth>2){r.error="订阅编码嵌套过深。";return r;}
    auto bytes=document.trimmed();if(bytes.startsWith("\xef\xbb\xbf"))bytes.remove(0,3);
    const auto json=QJsonDocument::fromJson(bytes);
    if(json.isObject()&&json.object().value("outbounds").isArray()){singBox(r,json.object().value("outbounds").toArray());return r;}
    const auto text=QString::fromUtf8(bytes);
    if(text.startsWith("STATUS=")){
        const auto end=text.indexOf('\n');if(end<0||end>4096){r.error="Shadowrocket 状态头无效。";return r;}
        r=normalize(text.mid(end+1).toUtf8(),depth+1);
        if(!r.originals.isEmpty())r.originals[0]["subscription-status-header"]=text.left(end);
        return r;
    }
    if(text.startsWith('[')&&!json.isArray()&&(text.contains("[Proxy]",Qt::CaseInsensitive)||text.contains("[server_local]",Qt::CaseInsensitive))){ini(r,text);return r;}
    if(QRegularExpression("^(ss|ssr|trojan|vmess|vless|socks4a|socks4|socks5|socks|http|https)://",QRegularExpression::CaseInsensitiveOption).match(text).hasMatch()){
        r.handled=true;r.format="通用 URI / Shadowrocket";
        for(const auto &line:text.split('\n')){const auto value=line.trimmed();if(value.isEmpty()||value.startsWith('#'))continue;uri(r,value);if(!r.error.isEmpty())break;}return r;
    }
    if(QRegularExpression("^(shadowsocks|trojan|vmess|http|socks5)\\s*=",QRegularExpression::CaseInsensitiveOption).match(text).hasMatch()){ini(r,text);return r;}
    if(QRegularExpression("^[^=\\r\\n]{1,128}\\s*=\\s*(Shadowsocks|Trojan|VMess|VLESS|socks5|http|https|ss)\\s*,",QRegularExpression::CaseInsensitiveOption|QRegularExpression::MultilineOption).match(text).hasMatch()){ini(r,text);return r;}
    const auto decoded=base64(bytes);
    if(!decoded.isEmpty()&&decoded!=bytes&&(decoded.contains("://")||decoded.contains("proxies:")||decoded.contains("[Proxy]")||decoded.contains("outbounds"))){
        r=normalize(decoded,depth+1);if(!r.handled&&r.error.isEmpty())r.decodedDocument=decoded;r.format="Base64 / "+(r.format.isEmpty()?QString("Clash"):r.format);return r;
    }
    r.format="Clash YAML / JSON";return r;
}
