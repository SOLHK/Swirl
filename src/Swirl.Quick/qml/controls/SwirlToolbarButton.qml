import QtQuick
import SwirlQuick

SwirlMotionButton {
    id: control
    implicitHeight: Theme.toolbarHeight
    leftPadding: Theme.toolbarPadding
    rightPadding: Theme.toolbarPadding
    topPadding: 0
    bottomPadding: 0
    hoverEnabled: true
    pressMotion: false
    motionScale: 1
    transform: []
    background: SwirlControlSurface {
        radius: Theme.pillRadius(height)
        hovered: control.hovered; pressed: control.down
        focused: control.visualFocus; controlEnabled: control.enabled
        color: control.down ? (Theme.dark ? "#383838" : "#E3E3E3")
            : control.hovered ? (Theme.dark ? "#323232" : "#E8E8E8")
            : Theme.dark ? "#292929" : "#EEEEEE"
    }
}
