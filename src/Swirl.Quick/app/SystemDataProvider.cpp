#include "SystemDataProvider.h"
#include "network/CaptureService.h"
#include "engine/EngineController.h"
#include <QGuiApplication>
#include <QClipboard>
#include <QNetworkInterface>
#include <QDateTime>
#include <QUrl>

SystemDataProvider::SystemDataProvider(CaptureService *capture,EngineController *engine):m_capture(capture),m_engine(engine) {
    connect(capture,&CaptureService::sessionsChanged,this,[this]{++m_revision;emit dataChanged();});
    connect(engine,&EngineController::statusChanged,this,[this]{
        m_logs.prepend(QVariantMap{{"time",QDateTime::currentDateTime().toString("HH:mm:ss")},
            {"level",m_engine->error().isEmpty()?"INFO":"ERROR"},{"source","Engine"},{"message",m_engine->stateText()}});
        if(m_logs.size()>100)m_logs.removeLast();
        ++m_revision; emit dataChanged();
    });
}
QVariantMap SystemDataProvider::currentNetwork() const {
    for(const auto &iface:QNetworkInterface::allInterfaces()) {
        const auto flags=iface.flags();
        if(!(flags&QNetworkInterface::IsUp) || !(flags&QNetworkInterface::IsRunning) || (flags&QNetworkInterface::IsLoopBack))continue;
        if(iface.type()!=QNetworkInterface::Wifi && iface.type()!=QNetworkInterface::Ethernet)continue;
        if(!iface.addressEntries().isEmpty())return {{"type",iface.type()==QNetworkInterface::Wifi?"Wi-Fi":"以太网"},{"name",iface.humanReadableName()}};
    }
    return {{"type","未连接"},{"name","无活动网络接口"}};
}
QVariantList SystemDataProvider::requests() const {
    auto result=m_capture->sessions();
    for(auto &value:result){auto row=value.toMap();row.insert("path",QUrl(row.value("url").toString()).path());row.insert("version","—");value=row;}
    return result;
}
QVariantList SystemDataProvider::nodes() const { return m_engine->nodes(); }
bool SystemDataProvider::copyText(const QString &text) const { if(auto *clipboard=QGuiApplication::clipboard()){clipboard->setText(text);return true;}return false; }
