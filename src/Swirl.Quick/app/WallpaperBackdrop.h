#pragma once
#include <QObject>
#include <QQuickImageProvider>
#include <QAbstractNativeEventFilter>
#include <QVariantMap>
#include <QCache>
#include <QMutex>

class WallpaperImages final : public QQuickImageProvider {
public:
    WallpaperImages();
    QImage requestImage(const QString &, QSize *, const QSize &) override;
private:
    QCache<QString,QImage> m_images{64*1024}; // KiB; bounded across monitors/revisions
    QMutex m_mutex;
};
class WallpaperBackdrop final : public QObject, public QAbstractNativeEventFilter {
    Q_OBJECT
    Q_PROPERTY(int revision READ revision NOTIFY changed)
public:
    explicit WallpaperBackdrop(bool fixture=false,QObject *parent=nullptr);
    ~WallpaperBackdrop() override;
    int revision() const { return m_revision; }
    Q_INVOKABLE QVariantMap describe(QObject *window) const;
    bool nativeEventFilter(const QByteArray &,void *,qintptr *) override;
signals:
    void changed();
private:
    int m_revision=0;
    bool m_fixture=false;
};
