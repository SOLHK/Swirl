import QtQuick
import SwirlQuick
import "../controls"

SwirlControlSurface {
    id: surface
    radius: Theme.pillRadius(height)
    border.width: focused || Theme.increaseContrast ? 1 / Screen.devicePixelRatio : 0
    border.color: focused ? Theme.focusBorder : Theme.text
}
