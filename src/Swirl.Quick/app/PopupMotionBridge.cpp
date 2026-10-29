#include "MotionPolicy.h"
#include <QPointer>
#include <QtQuickTemplates2/private/qquickpopup_p.h>
#include <QtQuickTemplates2/private/qquickpopup_p_p.h>

// Qt 6.12's Popup owns the animation job: changing Transition.enabled or
// completing its QML child animation cannot cancel an in-flight transition.
// Keep this SDK-specific bridge in the UI layer. Cancel the owned job first,
// then invoke Qt's normal finalizer so overlays, focus, opened/closed signals
// and native popup windows retire exactly as on an ordinary completion.
void MotionPolicy::finishPopup(QObject *object) {
    auto *popup=qobject_cast<QQuickPopup *>(object);
    if(!popup)return;
    auto *state=QQuickPopupPrivate::get(popup);
    const auto transition=state->transitionState;
    if(transition==QQuickPopupPrivate::NoTransition)return;
    QPointer<QQuickPopup> guard(popup);
    state->transitionManager.cancel();
    // Cancellation emits running-state notifications. A QML handler may
    // destroy the owner or retarget it; never finalize that newer operation.
    if(!guard)return;
    state=QQuickPopupPrivate::get(guard);
    if(state->transitionState!=transition)return;
    if(transition==QQuickPopupPrivate::ExitTransition)state->finalizeExitTransition();
    else state->finalizeEnterTransition();
}

bool MotionPolicy::reversePopupExit(QObject *object) {
    auto *popup=qobject_cast<QQuickPopup *>(object);
    if(!popup || popup->popupType()!=QQuickPopup::Item)return false;
    if(QQuickPopupPrivate::get(popup)->transitionState!=QQuickPopupPrivate::ExitTransition)return false;
    // QQuickMenu::setVisible has an early visible==requested guard that does
    // not account for an active exit. Popup's base implementation explicitly
    // supports that reversal. Restrict this workaround to our item popups.
    popup->QQuickPopup::setVisible(true);
    return true;
}
