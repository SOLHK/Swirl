#pragma once

#include <QObject>
#include <QPointer>
#include <QWindow>
#include <QtQml/qqml.h>
#include <QtQml/qqmlregistration.h>

// A single observer is attached to each rendering window. Text items share it;
// moving a window or changing its screen never creates a per-frame font scan.
// Qt's generated QML registration derives QQmlElement<T> even for an attached,
// uncreatable type, so this class must not be final.
class FontDisplayContext : public QObject {
    Q_OBJECT
    QML_ELEMENT
    QML_UNCREATABLE("FontDisplayContext is attached to a Window")
    QML_ATTACHED(FontDisplayContext)
    Q_PROPERTY(qreal logicalDpi READ logicalDpi NOTIFY metricsChanged)
    Q_PROPERTY(qreal devicePixelRatio READ devicePixelRatio NOTIFY metricsChanged)
public:
    explicit FontDisplayContext(QObject *parent = nullptr);
    static FontDisplayContext *qmlAttachedProperties(QObject *object);
    qreal logicalDpi() const { return m_logicalDpi; }
    qreal devicePixelRatio() const { return m_devicePixelRatio; }
signals:
    void metricsChanged();
protected:
    bool eventFilter(QObject *watched, QEvent *event) override;
private:
    void observeScreen();
    void updateMetrics();
    QPointer<QWindow> m_window;
    QMetaObject::Connection m_logicalDpiConnection;
    QMetaObject::Connection m_physicalDpiConnection;
    qreal m_logicalDpi = 96.0;
    qreal m_devicePixelRatio = 1.0;
};

QML_DECLARE_TYPEINFO(FontDisplayContext, QML_HAS_ATTACHED_PROPERTIES)
