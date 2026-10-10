import QtQuick
import SwirlQuick
Rectangle {
    id:panel
    property string material:"content"
    property bool selected:false
    property int cornerRadius:16
    radius:cornerRadius
    color:Theme.material(material)
    border.color:selected?Theme.accent:Theme.border
    border.width:1
    // A tinted component is not a promise of blur behind this component.
    // Native DWM system backdrop is applied exclusively at window level.
    Behavior on color { ColorAnimation { duration:Theme.motion } }
}