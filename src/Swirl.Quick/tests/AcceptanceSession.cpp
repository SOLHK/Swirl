// Local-only real-subscription acceptance driver. It loads an encrypted COPY
// under the logged-in Windows account and never exports private node options.
#include "engine/RustCoreEngine.h"
#include "engine/NodeStore.h"
#include "engine/SystemProxySession.h"
#include "engine/NodeTestService.h"
#include <QCoreApplication>
#include <QFile>
#include <QJsonDocument>
#include <QJsonArray>
#include <QJsonObject>
#include <QTimer>
#include <cstdio>
static void output(const QJsonObject &o) { auto b=QJsonDocument(o).toJson(QJsonDocument::Compact);std::fwrite(b.constData(),1,b.size(),stdout);std::fputs("\n",stdout);std::fflush(stdout); }
int main(int argc,char **argv) {
    QCoreApplication app(argc,argv);app.setApplicationName("Swirl");app.setOrganizationName("SOLHK");
    if(app.arguments().size()<3)return 2;
    NodeStore store(app.arguments().at(1));
    if(!store.error().isEmpty()){output({{"error","DPAPI load failed"}});return 3;}
    if(app.arguments().at(2)=="list") {
        QJsonArray nodes;for(const auto &n:store.nodes())nodes.append(QJsonObject{{"name",n.name},{"protocol",n.protocol},{"selected",n.id==store.selectedId()}});
        output({{"nodes",nodes},{"subscriptions",store.subscriptions().size()}});return 0;
    }
    EngineStartOptions opts;opts.nodes=store.nodes();
    const auto name=app.arguments().at(2);
    for(const auto &n:opts.nodes)if(n.name==name)opts.selectedNodeId=n.id;
    if(opts.selectedNodeId.isEmpty()&&name!="test-all")return 4;
    opts.smartRouting=true;opts.rulesDirectory=app.applicationDirPath()+"/rules";
    opts.proxyPort=17988;
    if(name=="test-all") {
        NodeTestService tests;QStringList ids;for(const auto &n:opts.nodes)ids.append(n.id);
        QObject::connect(&tests,&NodeTestService::changed,&app,[&]{
            if(tests.busy()||tests.completed()!=tests.total()||tests.completed()==0)return;
            QJsonArray rows;for(const auto &n:opts.nodes){const auto result=tests.result(n.id);if(!result.isEmpty())rows.append(QJsonObject{{"name",n.name},{"success",result.value("success").toBool()},{"latencyMs",result.value("latency").toInt()},{"http",result.value("http").toInt()},{"error",result.value("error").toString()}});}
            output({{"complete",true},{"total",tests.total()},{"succeeded",tests.succeeded()},{"failed",tests.failed()},{"rows",rows},{"mainSelectionModified",false},{"systemProxyModified",false}});app.quit();
        });QTimer::singleShot(15*60*1000,&app,[&]{tests.cancel();app.exit(8);});tests.start(opts,ids,QUrl("https://www.gstatic.com/generate_204"));return app.exec();
    }
    RustCoreEngine engine;SystemProxySession proxy;
    const QString command=app.arguments().value(3);
    bool announced=false;
    QObject::connect(&engine,&ProxyEngine::statusChanged,&app,[&] {
        const auto s=engine.status();
        if(s.state==ProxyEngine::State::Failed){output({{"error",s.message}});app.exit(6);}
        if(s.apiHealthy&&!announced) {announced=true;
            output({{"ready",true},{"node",name},{"port",s.proxyPort},{"pid",double(s.processId)},{"configPath",s.configPath},{"mode",s.mode}});}
    });
    QTimer poll;poll.setInterval(200);
    QObject::connect(&poll,&QTimer::timeout,&app,[&] {
        if(command.isEmpty())return;QFile f(command);if(!f.open(QIODevice::ReadOnly))return;
        const auto o=QJsonDocument::fromJson(f.readAll()).object();f.close();QFile::remove(command);
        const auto action=o.value("action").toString();
        if(action=="stop"){proxy.disable();engine.stop();app.quit();}
        if(action=="proxy") {const auto s=engine.status();const bool on=o.value("enabled").toBool();
            const bool ok=on?(s.apiHealthy&&proxy.enable(s.proxyPort,s.processId)):proxy.disable();
            output({{"systemProxy",proxy.enabled()},{"success",ok},{"error",proxy.error()}});}
        if(action=="mode")engine.setRoutingMode(o.value("mode").toString());
        if(action=="switch") {QString id;for(const auto &n:opts.nodes)if(n.name==o.value("name").toString())id=n.id;if(!id.isEmpty())engine.selectNode(id);}
        if(action=="probe")engine.probeNode(QUrl(o.value("url").toString()));
        if(action=="status") {const auto s=engine.status();output({{"mode",s.mode},{"apiHealthy",s.apiHealthy},{"request",int(s.requestState)},{"nodeHealth",int(s.nodeHealth)},{"message",s.nodeMessage}});}
    });poll.start();
    QTimer::singleShot(20*60*1000,&app,&QCoreApplication::quit);
    engine.start(opts);return app.exec();
}
