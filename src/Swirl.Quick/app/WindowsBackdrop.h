#pragma once
#include <QObject>
#include <QPointer>

class QQuickWindow;
class QEvent;

// Applies the native backdrop and enforces real top-level rounded window bounds.
class WindowsBackdrop final : public QObject
{
    Q_OBJECT
public:
    using QObject::QObject;
    Q_INVOKABLE void apply(QObject *window, bool enabled);
protected:
    bool eventFilter(QObject *watched, QEvent *event) override;
private:
    QPointer<QQuickWindow> m_window;
    void updateCornerMask(QQuickWindow *window);
};
