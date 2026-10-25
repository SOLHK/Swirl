#pragma once
#include <QObject>
#include <QPointer>
#include <QSize>
#include <QRectF>
#include <QAbstractNativeEventFilter>
class QQuickWindow;
// QML uses the effective composition result, never just the requested setting.
class WindowsBackdrop final : public QObject, public QAbstractNativeEventFilter {
    Q_OBJECT
    Q_PROPERTY(bool active READ active NOTIFY changed)
    Q_PROPERTY(bool translucent READ translucent NOTIFY changed)
    Q_PROPERTY(bool blurActive READ blurActive NOTIFY changed)
    Q_PROPERTY(bool micaActive READ micaActive NOTIFY changed)
    Q_PROPERTY(bool nativeCorners READ nativeCorners NOTIFY changed)
    Q_PROPERTY(bool exactCorners READ exactCorners NOTIFY changed)
    Q_PROPERTY(qreal cornerRadius READ cornerRadius NOTIFY changed)
    Q_PROPERTY(bool compatibilityShadow READ compatibilityShadow NOTIFY changed)
    Q_PROPERTY(QString status READ status NOTIFY changed)
public:
    explicit WindowsBackdrop(QObject *parent = nullptr);
    ~WindowsBackdrop() override;
    bool active() const { return m_active; }
    bool translucent() const { return m_translucent; }
    bool blurActive() const { return m_blurActive; }
    bool micaActive() const { return m_micaActive; }
    quintptr materialWindowHandle() const { return m_blurHandle; }
    bool nativeCorners() const { return m_nativeCorners; }
    bool exactCorners() const { return m_exactCorners; }
    qreal cornerRadius() const { return m_cornerRadius; }
    bool compatibilityShadow() const { return m_shadowVisible; }
    quintptr compatibilityShadowHandle() const { return m_shadowHandle; }
    quint64 compatibilityShadowBuildCount() const { return m_shadowBuildCount; }
    QString status() const { return m_status; }
    Q_INVOKABLE void apply(QObject *window, bool enabled, bool dark = false);
    Q_INVOKABLE void showSystemMenu();
    // Clip a separate short-lived transition HWND without changing the normal
    // shell's contour ownership. The coordinates are local Qt logical pixels.
    Q_INVOKABLE void applyTransientClip(QObject *window, const QRectF &logicalRect, qreal logicalRadius);
    Q_INVOKABLE void clearTransientClip(QObject *window);
    // Explicit screenshot CLI only; ordinary application windows never become
    // topmost. Prevent occluded screenshots from masquerading as UI evidence.
    bool prepareNativeCapture();
    bool isCaptureForeground() const;
    void finishNativeCapture();
    bool nativeEventFilter(const QByteArray &, void *, qintptr *) override;
signals:
    void changed();
protected:
    bool eventFilter(QObject *, QEvent *) override;
private:
    QPointer<QQuickWindow> m_window;
    quintptr m_handle = 0;
    bool m_captureWasTopmost = false;
    bool m_enabled = false, m_dark = false, m_active = false, m_nativeCorners = false;
    bool m_translucent = false;
    bool m_blurActive = false;
    bool m_micaActive = false;
    bool m_materialEligible = false, m_materialAttempted = false;
    quintptr m_blurHandle = 0;
    QSize m_blurRegionSize;
    qreal m_blurRegionRadius = -1;
    void updateBackdropBlur();
    void destroyBackdropBlur();
    bool m_exactCorners = false;
    qreal m_cornerRadius = 0;
    QSize m_regionSize;
    qreal m_regionDpr = 0;
    bool m_cornerUpdateQueued = false;
    quintptr m_shadowHandle = 0;
    bool m_shadowVisible = false, m_shadowActive = false;
    QSize m_shadowSize;
    qreal m_shadowRadius = 0, m_shadowDpr = 0;
    quint64 m_shadowBuildCount = 0;
    QString m_status = QStringLiteral("Opaque: not initialized");
    void refresh();
    void updateCornerMask();
    void scheduleCornerUpdate();
    void updateCompatibilityShadow();
    void destroyCompatibilityShadow();
};
