#pragma once
#include <QObject>
#include <QStringList>
#include <QUrl>
#include <QVariantMap>
#include <QHash>
#include <QTimer>
#include <QCache>
#include <QFont>

class QSettings;

class FontManager final : public QObject {
    Q_OBJECT
    Q_PROPERTY(QString currentFamily READ currentFamily NOTIFY currentFamilyChanged)
    Q_PROPERTY(QString defaultFamily READ defaultFamily CONSTANT)
    Q_PROPERTY(QStringList families READ families NOTIFY familiesChanged)
    Q_PROPERTY(QString error READ error NOTIFY errorChanged)
    Q_PROPERTY(QString previewFamily READ previewFamily NOTIFY previewFamilyChanged)
    Q_PROPERTY(QVariantList previewAxes READ previewAxes NOTIFY previewAxesChanged)
    Q_PROPERTY(QVariantMap previewValues READ previewValues NOTIFY previewValuesChanged)
    Q_PROPERTY(QStringList importedFamilies READ importedFamilies NOTIFY familiesChanged)
    Q_PROPERTY(int configurationRevision READ configurationRevision NOTIFY configurationChanged)
    Q_PROPERTY(bool automatic READ automatic NOTIFY configurationChanged)
    Q_PROPERTY(bool previewAutomatic READ previewAutomatic NOTIFY previewAutomaticChanged)
    Q_PROPERTY(QString licenseText READ licenseText CONSTANT)
public:
    explicit FontManager(QObject *parent=nullptr, const QString &storageDirectory=QString());
    ~FontManager() override;
    QString currentFamily() const { return m_family; }
    QString defaultFamily() const { return m_defaultFamily; }
    QStringList families() const;
    QString error() const { return m_error; }
    QString licenseText() const;
    QString previewFamily() const { return m_previewFamily; }
    QVariantList previewAxes() const { return axesFor(m_previewFamily); }
    QVariantMap previewValues() const { return m_previewValues; }
    QStringList importedFamilies() const { return m_importedFamilies; }
    int configurationRevision() const { return m_revision; }
    bool automatic() const { return m_automatic; }
    bool previewAutomatic() const { return m_previewAutomatic; }
    Q_INVOKABLE QVariantList axesFor(const QString &family) const;
    Q_INVOKABLE bool choosePreviewFamily(const QString &family);
    Q_INVOKABLE bool setPreviewAxis(const QString &tag, double value);
    Q_INVOKABLE void setPreviewAutomatic(bool automatic);
    Q_INVOKABLE void resetPreviewAxes();
    Q_INVOKABLE bool applyPreview();
    Q_INVOKABLE void discardPreview();
    Q_INVOKABLE bool selectFamily(const QString &family);
    Q_INVOKABLE bool importFont(const QUrl &file);
    // On-demand evidence; never called by a text layout or animation binding.
    Q_INVOKABLE QVariantMap sourceIdentityForFont(const QFont &font) const;
    Q_INVOKABLE QVariantMap variableAxesFor(const QString &family, int weight) const;
    Q_INVOKABLE QVariantMap resolvedAxes(const QString &family, int weight,
        double pixelSize, double pointSize, double logicalDpi, double dpr,
        const QString &role) const;
    Q_INVOKABLE QVariantMap previewResolvedAxes(int weight, double pixelSize,
        double pointSize, double logicalDpi, double dpr, const QString &role) const;
    Q_INVOKABLE QVariantMap resolvedAxesForFont(const QFont &font,
        double logicalDpi, double dpr, const QString &role) const;
    Q_INVOKABLE QVariantMap previewResolvedAxesForFont(const QFont &font,
        double logicalDpi, double dpr, const QString &role) const;
    Q_INVOKABLE QVariantMap fittedText(const QFont &font, const QString &text,
        double logicalDpi, double dpr, const QString &role, double availableWidth,
        double previousWidth) const;
    Q_INVOKABLE void reset();
#ifdef SWIRL_UI_TESTS
    int metadataCacheSize() const { return m_axisMetadata.size(); }
    int resolutionCacheSize() const { return m_resolvedAxes.size(); }
#endif
signals:
    void currentFamilyChanged();
    void familiesChanged();
    void errorChanged();
    void previewFamilyChanged();
    void previewValuesChanged();
    void previewAxesChanged();
    void previewAutomaticChanged();
    void configurationChanged();
private:
    bool fail(const QString &message);
    void apply(const QString &family, bool clearError = true);
    QString m_family, m_defaultFamily, m_harmonyFamily, m_error, m_directory;
    QVariantMap normalizedAxes(const QString &family, const QVariantMap &values) const;
    void savePreview();
    void refreshFamilies();
    void refreshFontDatabase();
    int loadFontFile(const QString &path);
    bool verifyImportedFamily(const QString &family);
    void migrateSettings();
    struct Profile { bool automatic = true; QVariantMap values; };
    Profile profileFor(const QString &family) const;
    void writeProfile(QSettings &settings, const QString &family,
                      const QVariantMap &values, bool automatic) const;
    void writePreview(QSettings &settings) const;
    QString m_previewFamily;
    QStringList m_availableFamilies, m_importedFamilies;
    QVariantMap m_previewValues, m_values;
    mutable QHash<QString,QVariantList> m_axisMetadata;
    mutable QCache<QByteArray,QVariantMap> m_resolvedAxes{256};
    mutable QCache<QByteArray,qreal> m_textWidths{256};
    QHash<QString,int> m_loadedPaths;
    QHash<QString,QString> m_familySources;
    QTimer m_saveTimer;
    QTimer m_databaseTimer;
    bool m_automatic = true, m_previewAutomatic = true;
    int m_revision=0;
    QList<int> m_fontIds;
};
