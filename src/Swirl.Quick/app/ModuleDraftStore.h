#pragma once
#include <QObject>
#include <QVariantMap>
#include <QUrl>
class ModuleDraftStore : public QObject {
    Q_OBJECT
    Q_PROPERTY(QString lastError READ lastError NOTIFY errorChanged)
public:
    explicit ModuleDraftStore(QObject *parent=nullptr);
    QString lastError() const {return m_error;}
    Q_INVOKABLE QVariantMap load(const QString &id) const;
    Q_INVOKABLE bool save(const QString &id,const QVariantMap &draft);
    Q_INVOKABLE bool exportFile(const QUrl &url,const QString &id,const QVariantMap &draft);
    Q_INVOKABLE QVariantMap importFile(const QUrl &url,const QString &id);
signals:
    void errorChanged();
private:
    bool fail(const QString &message);
    QString m_path,m_error;
};
