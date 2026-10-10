import QtQuick
import SwirlQuick
Rectangle {
    id:panel
    property string material:"content"
    property bool selected:false
    property int cornerRadius:19
    radius:cornerRadius
    color:Theme.material(material)
    border.color:selected?Theme.accent:Theme.border
    border.width:1
    gradient: Gradient {
        GradientStop { position:0.0; color:Theme.material(panel.material) }
        GradientStop { position:1.0; color:Theme.dark ? "#E91A2B3B" : "#F7FFFFFF" }
    }
    // A tinted component is not a promise of blur behind this component.
    // Native DWM system backdrop is applied exclusively at window level.
    Behavior on color { ColorAnimation { duration:Theme.motion } }
}