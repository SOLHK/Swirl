#include "DismissalController.h"
#include <QGuiApplication>
#include <QQuickWindow>
#include <QQuickItem>
#include <QKeyEvent>
#include <QCryptographicHash>
#include <QTimer>
#include <QVariant>
#include <QSet>
#include <functional>

DismissalController::DismissalController(QObject *parent):QObject(parent) { qApp->installEventFilter(this); }
void DismissalController::push(QObject *popup, QObject *owner) {
    auto *window=qobject_cast<QQuickWindow *>(owner);
    if(!popup || !window)return;
    for(const auto &layer:m_layers)if(layer.popup==popup)return;
    m_layers.append({popup,window,window->activeFocusItem()});
    connect(popup,&QObject::destroyed,this,[this,popup]{pop(popup);});
    emit changed();
}
void DismissalController::pop(QObject *popup) {
    QPointer<QQuickItem> focus;
    for(int i=m_layers.size()-1;i>=0;--i)if(!m_layers[i].popup || m_layers[i].popup==popup) {
        if(m_layers[i].popup==popup && i==m_layers.size()-1)focus=m_layers[i].focus;
        m_layers.removeAt(i);
    }
    emit changed();
    QTimer::singleShot(0,this,[focus]{if(focus && focus->isVisible() && focus->isEnabled())focus->forceActiveFocus(Qt::PopupFocusReason);});
}
bool DismissalController::hasPopup(QObject *window) const {
    for(const auto &layer:m_layers)if(layer.popup && layer.window==window)return true;
    return false;
}
bool DismissalController::dismiss(QObject *window) {
    for(int i=m_layers.size()-1;i>=0;--i)if(m_layers[i].popup && m_layers[i].window==window) {
        QMetaObject::invokeMethod(m_layers[i].popup,"requestDismiss");return true;
    }
    return false;
}
bool DismissalController::eventFilter(QObject *receiver,QEvent *event) {
    if(event->type()!=QEvent::ShortcutOverride && event->type()!=QEvent::KeyPress)return false;
    auto *key=static_cast<QKeyEvent *>(event);
    auto *window=qobject_cast<QQuickWindow *>(receiver);
    if(!window || key->key()!=Qt::Key_Escape)return false;
    // Let the focused editor cancel its IME composition before navigating.
    if(window->activeFocusItem()&&window->activeFocusItem()->property("inputMethodComposing").toBool())return false;
    const bool popup=hasPopup(window);
    const bool dismissible=window->property("swirlDismissibleWindow").toBool();
    const bool back=window->property("swirlBackAvailable").toBool();
    if(!popup && !dismissible && !back)return false;
    event->accept();
    if(event->type()==QEvent::KeyPress && !key->isAutoRepeat()) {
        if(popup)dismiss(window);else if(back)QMetaObject::invokeMethod(window,"handleEscape");else window->close();
    }
    return true;
}
QString DismissalController::fingerprint(QObject *root) const {
    QByteArray state;
    if(!root)return {};
    // Keep only a hash in QML; never expose form contents, URLs or passwords.
    const auto append=[&](QObject *object) {
        if(object->property("cursorPosition").isValid() && object->property("readOnly").isValid() && !object->property("readOnly").toBool())
            state+=object->property("text").toString().toUtf8().toHex()+';';
        if(object->property("checkable").toBool())state+=object->property("checked").toBool()?'1':'0';
        if(object->property("currentIndex").isValid() && object->property("editable").isValid())state+=QByteArray::number(object->property("currentIndex").toInt())+';';
    };
    // Controls reparent content visually without always changing QObject
    // ownership. Follow the scene tree as well as QObject ownership.
    QSet<QObject *> visited;
    std::function<void(QObject *)> visit=[&](QObject *object){
        if(!object || visited.contains(object))return;
        visited.insert(object);append(object);
        if(auto *item=qobject_cast<QQuickItem *>(object))for(auto *child:item->childItems())visit(child);
        for(auto *child:object->children())visit(child);
    };
    visit(root);
    return QString::fromLatin1(QCryptographicHash::hash(state,QCryptographicHash::Sha256).toHex());
}
