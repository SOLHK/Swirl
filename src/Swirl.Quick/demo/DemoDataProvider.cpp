#include "DemoDataProvider.h"
#include <QStringList>
#include <QVariantMap>
#include <QChar>
#include <QGuiApplication>
#include <QClipboard>

QVariantList DemoDataProvider::connections() const
{
    QVariantList rows;
    const QStringList hosts={"api.github.com","cdn.jsdelivr.net","developer.apple.com","www.microsoft.com","fonts.gstatic.com","example.org","api.openai.com","updates.example.net"};
    const QStringList apps={"浏览器","系统","Swirl 演示","终端","开发工具","邮件"};
    const QStringList policy={"DIRECT","Global / SG","Auto Select","REJECT"};
    for(int i=0;i<54;++i)
        rows << QVariantMap{
            {"id",QString("C-%1").arg(i+1001)}, {"host",hosts.at(i%hosts.size())},
            {"ip",QString("203.0.113.%1").arg(10+i%150)}, // TEST-NET-3
            {"process",apps.at(i%apps.size())}, {"protocol",i%3 ? "HTTPS" : "TCP"},
            {"policy",policy.at(i%policy.size())},
            {"up",QString::number(12+i*7)+" KB"},{"down",QString::number(74+i*31)+" KB"},
            {"latency",QString::number(21+i*19%160)+" ms"},
            {"time",QString("14:%1:%2").arg(i*3%60,2,10,QChar('0')).arg(i*11%60,2,10,QChar('0'))},
            {"status",i%7==0 ? "已关闭" : "活动中"}};
    return rows;
}
QVariantList DemoDataProvider::requests() const
{
    QVariantList rows;
    const QStringList paths={"/v1/user","/assets/app.js","/api/status","/v3/search?q=swirl","/auth/session","/images/hero.webp","/config.json","/graphql"};
    const QStringList hosts={"api.example.test","cdn.example.test","assets.example.test"};
    const QStringList methods={"GET","GET","POST","GET","PUT","GET","DELETE","GET"};
    for(int i=0;i<62;++i)
        rows << QVariantMap{
            {"id",QString("R-%1").arg(i+1100)},{"method",methods.at(i%methods.size())},
            {"host",hosts.at(i%hosts.size())},{"path",paths.at(i%paths.size())},
            {"status",i%13==0 ? 404 : (i%11==0 ? 304 : 200)},
            {"version",i%4==0 ? "HTTP/3" : (i%3==0 ? "HTTP/1.1" : "HTTP/2")},
            {"duration",QString::number(25+i*23%600)+" ms"},
            {"size",QString::number(2+i*9%360)+" KB"},{"waterfall",i*17%70},
            {"tls","TLS 1.3 · AES_128_GCM_SHA256"}};
    return rows;
}
QVariantList DemoDataProvider::nodes() const
{
    QVariantList rows;
    const QStringList places={"香港","新加坡","东京","洛杉矶","首尔","法兰克福","台北","伦敦","悉尼"};
    const QStringList regions={"HK","SG","JP","US","KR","DE","TW","GB","AU"};
    for(int i=0;i<18;++i)
        rows << QVariantMap{
            {"name",places.at(i%places.size())+" · "+QString("%1").arg(i/places.size()+1,2,10,QChar('0'))},
            {"region",regions.at(i%regions.size())},{"protocol",i%2 ? "Trojan" : "Hysteria2"},
            {"latency",24+i*21%190},{"status",i%7==0 ? "未连接" : "可用"}};
    return rows;
}
QVariantList DemoDataProvider::events() const
{
    return {QVariantMap{{"time","14:08:21"},{"title","策略匹配：自动选择"},{"detail","api.github.com · HTTPS"},{"kind","info"}},
    QVariantMap{{"time","14:08:12"},{"title","DNS 解析已完成"},{"detail","cdn.jsdelivr.net · DoH"},{"kind","success"}},
    QVariantMap{{"time","14:07:58"},{"title","规则已拒绝请求"},{"detail","ads.example.test · REJECT"},{"kind","warn"}},
    QVariantMap{{"time","14:07:43"},{"title","演示数据已刷新"},{"detail","仅本地演示数据"},{"kind","info"}}};
}
QVariantList DemoDataProvider::traffic() const
{
    QVariantList rows;
    for(int i=0;i<60;++i)
        rows << QVariantMap{{"x",i},{"up",15.0+i*17%29+8.0*(i%6==0)},
                             {"down",42.0+i*23%67+10.0*(i%7==0)}};
    return rows;
}
QVariantList DemoDataProvider::logs() const
{
    QVariantList rows;
    const QStringList levels={"INFO","DEBUG","INFO","WARN","INFO","ERROR"};
    const QStringList messages={"演示连接的分流规则已匹配","DNS 缓存查询已完成","模拟请求已检查","界面演示的自动化事件"};
    for(int i=0;i<80;++i)
        rows << QVariantMap{{"time",QString("14:%1:%2").arg(i*3%60,2,10,QChar('0')).arg(i*9%60,2,10,QChar('0'))},
                            {"level",levels.at(i%levels.size())},{"source",i%2 ? "Rules" : "Core"},
                            {"message",messages.at(i%messages.size())}};
    return rows;
}

bool DemoDataProvider::copyText(const QString &value) const
{
    if (auto *clipboard = QGuiApplication::clipboard()) {
        clipboard->setText(value);
        return true;
    }
    return false;
}
