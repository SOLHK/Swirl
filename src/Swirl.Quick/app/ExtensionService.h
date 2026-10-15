#pragma once
#include <QObject>
#include <QVariantList>
#include <QProcess>
#include <QTimer>
#include <QUrl>
class EngineController;
class ExtensionService final : public QObject {
    Q_OBJECT
    Q_PROPERTY(QVariantList scripts READ scripts NOTIFY changed)
    Q_PROPERTY(QVariantList modules READ modules NOTIFY changed)
    Q_PROPERTY(QVariantList profiles READ profiles NOTIFY changed)
    Q_PROPERTY(QString profileName READ profileName NOTIFY changed)
    Q_PROPERTY(QString error READ error NOTIFY changed)
    Q_PROPERTY(bool busy READ busy NOTIFY changed)
    Q_PROPERTY(QString output READ output NOTIFY changed)
public:
    explicit ExtensionService(EngineController *engine,QString path={},QObject *parent=nullptr);
    ~ExtensionService() override;
    QVariantList scripts() const {return m_scripts;}
    QVariantList modules() const {return m_modules;}
    QVariantList profiles() const {return m_profiles;}
    QString profileName() const;
    QString error() const {return m_error;}
    QString output() const {return m_output;}
    void shutdown();
    bool busy() const {return m_process.state()!=QProcess::NotRunning;}
    Q_INVOKABLE bool saveScript(const QString &id,const QString &name,const QString &source);
    Q_INVOKABLE bool importScript(const QUrl &source);
    Q_INVOKABLE bool removeScript(const QString &id);
    Q_INVOKABLE bool runScript(const QString &id,const QString &inputJson="{}");
    Q_INVOKABLE bool importModule(const QUrl &source);
    Q_INVOKABLE bool setModuleEnabled(const QString &id,bool enabled);
    Q_INVOKABLE bool moveModule(const QString &id,int step);
    Q_INVOKABLE bool removeModule(const QString &id);
    Q_INVOKABLE bool saveProfile(const QString &id,const QString &name,const QString &networkJson,const QString &mode);
    Q_INVOKABLE bool importProfile(const QUrl &source);
    Q_INVOKABLE bool exportProfile(const QString &id,const QUrl &destination);
    Q_INVOKABLE bool useProfile(const QString &id);
    Q_INVOKABLE bool removeProfile(const QString &id);
signals:
    void changed();
private:
    bool persist();
    void load();
    bool fail(const QString &error);
    QVariantMap merged(const QVariantList &modules,const QVariantMap &base) const;
    bool applyModules(const QVariantList &modules);
    bool finishConfigurationTransaction();
    EngineController *m_engine=nullptr;
    QString m_path,m_error,m_output;
    QVariantList m_scripts,m_modules,m_profiles;
    QString m_activeProfile,m_profileBaseMode="rule";
    QVariantMap m_profileBase;
    QVariantMap m_base;
    QVariantMap m_pendingConfiguration;
    QString m_pendingMode;
    bool m_configurationPending=false;
    QProcess m_process;
    QTimer m_timeout;
    QByteArray m_stdout;
    bool m_timedOut=false,m_outputExceeded=false,m_baseCaptured=false,m_storageReadable=true;
    void *m_workerJob=nullptr;
};
