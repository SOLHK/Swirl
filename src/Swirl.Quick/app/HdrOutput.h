#pragma once
#include <QObject>
#include <QPointer>
#include <atomic>
#include <rhi/qrhi.h>
#include <QVector>
#include <QRect>
class QQuickWindow;
class HdrOutput final : public QObject {
    Q_OBJECT
    Q_PROPERTY(bool active READ active NOTIFY changed)
    Q_PROPERTY(bool glowEnabled READ glowEnabled NOTIFY changed)
    Q_PROPERTY(qreal whiteScale READ whiteScale NOTIFY changed)
    Q_PROPERTY(qreal peakValue READ peakValue NOTIFY changed)
public:
    explicit HdrOutput(QObject *parent=nullptr):QObject(parent) {}
    void attach(QQuickWindow *window);
    void startDisplayTest(const QString &outputFile);
    bool active() const { return m_active; }
    bool glowEnabled() const { return m_glow; }
    qreal whiteScale() const { return m_white; }
    qreal peakValue() const { return m_peak; }
signals:
    void changed();
    void displayTestFinished(bool success);
private:
    QPointer<QQuickWindow> m_window;
    std::atomic_bool m_probe{true};
    bool m_active=false,m_glow=false,m_reported=false;
    qreal m_white=1,m_peak=1;
    std::atomic_bool m_capture{false};
    QRhiReadbackResult m_readback;
    QVector<QRect> m_lampBounds;
    QString m_captureFile;
    qreal m_captureWhite=1;
    QRect m_captureRect;
};
