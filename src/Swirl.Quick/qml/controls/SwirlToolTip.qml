import QtQuick
import QtQuick.Controls.Basic
import SwirlQuick

// Own the complete surface here. Overriding a derived popup's deferred content
// while a font binding reads that content can leave Qt creation unfinished.
ToolTip {
    id: control
    padding: Theme.dp(8)
    delay: 600
    font.pixelSize: Theme.captionSize
    font.family: Theme.fontFamily
    font.hintingPreference: Font.PreferFullHinting
    SwirlFontBinding {
        target: control
        when: control.visible
        textRole: "auxiliary"
        fontWindow: control.parent ? control.parent.Window.window : null
    }
    enter: Transition {
        enabled: !SwirlMotion.reduced
        OpacityAnimator { from: 0; to: 1; duration: SwirlMotion.menuExitDuration }
    }
    exit: Transition {
        enabled: !SwirlMotion.reduced
        OpacityAnimator { from: 1; to: 0; duration: SwirlMotion.pressDuration }
    }
    contentItem: Text {
        text: control.text; font: control.font; color: Theme.text
        wrapMode: Text.Wrap; renderType: Text.NativeRendering
    }
    background: Rectangle {
        color: Theme.material("floating"); radius: Theme.controlRadius
        border.width: Theme.borderWidth; border.color: Theme.border
    }
}
