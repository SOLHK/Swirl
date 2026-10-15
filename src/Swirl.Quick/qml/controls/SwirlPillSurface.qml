import QtQuick
import QtQuick.Effects
import SwirlQuick
Rectangle {
    id:surface
    property bool selected:false
    property bool pressed:false
    property bool hovered:false
    property bool primary:false
    property bool subtleShadow:false
    radius:Theme.pillRadius(height); antialiasing:true
    color:primary ? Theme.primaryControl : pressed ? Theme.pressed : selected ? Theme.selected : hovered ? Theme.hover : Theme.buttonBase
    gradient:Gradient {
        GradientStop { position:0; color:surface.primary ? Theme.primaryControl : surface.selected ? Theme.selected : surface.pressed ? Theme.pressed : surface.hovered ? Theme.hover : Theme.pillTop }
        GradientStop { position:1; color:surface.primary ? Theme.primaryControl : surface.selected ? Theme.selected : surface.pressed ? Theme.pressed : surface.hovered ? Theme.hover : Theme.pillBottom }
    }
    border.width:Theme.borderWidth
    border.color:Theme.pillRim
    RectangularShadow {
        anchors.fill:parent; z:-1
        visible:surface.subtleShadow && Theme.effectsSupported
        radius:surface.radius; blur:Theme.dp(8)
        offset:Qt.vector2d(0,Theme.dp(3))
        color:Theme.withAlpha("#000000",Theme.dark ? 0.12 : 0.05)
    }
}
