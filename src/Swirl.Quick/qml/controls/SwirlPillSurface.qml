import QtQuick
import QtQuick.Effects
import SwirlQuick
Rectangle {
    id:surface
    property bool selected:false
    property bool pressed:false
    property bool hovered:false
    property bool primary:false
    property bool subtleShadow:true
    radius:Theme.pillRadius(height); antialiasing:true
    color:primary ? Theme.accent : pressed ? Theme.pressed : selected ? Theme.selected : hovered ? Theme.hover : Theme.buttonBase
    gradient:Gradient {
        GradientStop { position:0; color:surface.primary ? "#389BFF" : surface.selected ? "#D4EAFF" : surface.pressed ? Theme.pressed : surface.hovered ? Theme.hover : Theme.pillTop }
        GradientStop { position:1; color:surface.primary ? "#087EFF" : surface.selected ? Theme.selected : surface.pressed ? Theme.pressed : surface.hovered ? Theme.hover : Theme.pillBottom }
    }
    border.width:Theme.borderWidth
    border.color:Theme.pillRim
    layer.enabled:subtleShadow
    layer.effect:MultiEffect {
        shadowEnabled:true; shadowBlur:0.35; shadowVerticalOffset:3
        shadowOpacity:Theme.dark ? 0.15 : 0.12; shadowColor:"#5378A3"
    }
}
