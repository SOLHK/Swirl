import QtQuick
import SwirlQuick
Rectangle {
    id:surface
    property bool selected:false
    property bool pressed:false
    property bool hovered:false
    property bool primary:false
    radius:Theme.pillRadius(height); antialiasing:true
    color:primary ? Theme.primaryControl : pressed ? Theme.pressed : selected ? Theme.selected : hovered ? Theme.hover : Theme.buttonBase
    border.width:Theme.increaseContrast ? Theme.borderWidth : 0
    border.color:Theme.pillRim
}
