#pragma once
#include <QObject>
#include <QStringList>
#include <QUrl>

class FontManager final : public QObject {
    Q_OBJECT
    Q_PROPERTY(QString currentFamily READ currentFamily NOTIFY currentFamilyChanged)
    Q_PROPERTY(QString defaultFamily READ defaultFamily CONSTANT)
    Q_PROPERTY(QStringList families READ families NOTIFY familiesChanged)
    Q_PROPERTY(QString error READ error NOTIFY errorChanged)
    Q_PROPERTY(QString licenseText READ licenseText CONSTANT)
public:
    explicit FontManager(QObject *parent=nullptr, const QString &storageDirectory=QString());
    QString currentFamily() const { return m_family; }
    QString defaultFamily() const { return m_defaultFamily; }
    QStringList families() const;
    QString error() const { return m_error; }
    QString licenseText() const;
    Q_INVOKABLE bool selectFamily(const QString &family);
    Q_INVOKABLE bool importFont(const QUrl &file);
    Q_INVOKABLE void reset();
signals:
    void currentFamilyChanged();
    void familiesChanged();
    void errorChanged();
private:
    bool fail(const QString &message);
    void apply(const QString &family);
    QString m_family, m_defaultFamily, m_error, m_directory;
};
