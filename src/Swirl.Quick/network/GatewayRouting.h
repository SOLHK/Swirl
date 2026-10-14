#pragma once
#include <QString>
#include <QProcess>
#include <QJsonObject>
namespace GatewayRouting {
QString startScript(const QString &journalPath);
QString cleanupScript(const QString &journalPath);
bool validJournal(const QJsonObject &journal);
void prepareProcess(QProcess &process,const QString &script);
bool cleanup(const QString &journalPath,QString *error=nullptr);
int guard(const QString &journalPath);
}
