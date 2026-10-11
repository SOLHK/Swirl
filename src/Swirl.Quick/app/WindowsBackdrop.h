#pragma once
#include <QObject>
#include <QPointer>
#include <QAbstractNativeEventFilter>
class QQuickWindow;
// QML uses the effective composition result, never just the requested setting.
class WindowsBackdrop final : public QObject, public QAbstractNativeEventFilter {
    Q_OBJECT
    Q_PROPERTY(bool active READ active NOTIFY changed)
    Q_PROPERTY(bool nativeCorners READ nativeCorners NOTIFY changed)
    Q_PROPERTY(QString status READ status NOTIFY changed)
public:
    explicit WindowsBackdrop(QObject *parent = nullptr);
    ~WindowsBackdrop() override;
    bool active() const { return m_active; }
    bool nativeCorners() const { return m_nativeCorners; }
    QString status() const { return m_status; }
    Q_INVOKABLE void apply(QObject *window, bool enabled, bool dark = false);
    Q_INVOKABLE void showSystemMenu();
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
    QString m_status = QStringLiteral("Opaque: not initialized");
    void refresh();
    void updateCornerMask();
};
