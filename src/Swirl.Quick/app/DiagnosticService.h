#pragma once
#include <QObject>
#include <QVariantList>
#include <QVariantMap>
#include <QMutex>
#include <QUrl>
class DiagnosticService final : public QObject {
 Q_OBJECT
 Q_PROPERTY(QVariantList records READ records NOTIFY changed)
 Q_PROPERTY(int eventCount READ eventCount NOTIFY changed)
 Q_PROPERTY(QString exportMessage READ exportMessage NOTIFY changed)
public:
 explicit DiagnosticService(QString directory={},QObject *parent=nullptr);
 ~DiagnosticService() override;
 void record(const QString &level,const QString &module,const QString &code,const QString &message,const QString &correlation={});
 QVariantList records() const;
 int eventCount() const;
 QString exportMessage() const { return m_exportMessage; }
 static QString redact(QString text);
 void installQtHandler();
 Q_INVOKABLE void acknowledge();
 Q_INVOKABLE bool exportReport(const QUrl &file,const QVariantMap &snapshot);
 Q_INVOKABLE void clearView();
signals:
 void changed();
private:
 QString m_directory,m_exportMessage;
 mutable QMutex m_mutex;
 QVariantList m_records;
 int m_events=0;
};
