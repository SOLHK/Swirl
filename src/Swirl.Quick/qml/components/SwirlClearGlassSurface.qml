import QtQuick
import SwirlQuick
import "../controls"

SwirlControlSurface {
    id: surface
    radius: Theme.pillRadius(height)
    border.width:Theme.increaseContrast ? 1 / Screen.devicePixelRatio : 0
    border.color:Theme.text
}
