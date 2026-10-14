#pragma once
#include <QObject>
#include <QPointer>
#include <QList>
class QQuickWindow;
class QQuickItem;

// One key event belongs to one layer. Qt still owns native file/menu popups.
class DismissalController final : public QObject {
    Q_OBJECT
    Q_PROPERTY(int count READ count NOTIFY changed)
public:
    explicit DismissalController(QObject *parent=nullptr);
    Q_INVOKABLE void push(QObject *popup, QObject *window);
    Q_INVOKABLE void pop(QObject *popup);
    Q_INVOKABLE bool hasPopup(QObject *window) const;
    Q_INVOKABLE bool dismiss(QObject *window);
    Q_INVOKABLE QString fingerprint(QObject *root) const;
    int count() const { return m_layers.size(); }
signals:
    void changed();
protected:
    bool eventFilter(QObject *, QEvent *) override;
private:
    struct Layer { QPointer<QObject> popup; QPointer<QQuickWindow> window; QPointer<QQuickItem> focus; };
    QList<Layer> m_layers;
};
