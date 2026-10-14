import QtQuick
import QtQuick.Effects
import SwirlQuick
Rectangle {
    id:panel
    property string material: "content"
    property bool selected: false
    property real cornerRadius: floating ? Theme.popupRadius : Theme.cardRadius
    property bool independentCard: Theme.pageBranch === "A" && !floating
    readonly property bool floating: material === "floating"
    radius: cornerRadius
    antialiasing: true
    color: independentCard ? Theme.independentCard : Theme.material(material)
    border.width: independentCard ? 0 : Theme.borderWidth
    border.color: selected ? Theme.focusBorder : Theme.border
    layer.enabled: independentCard && Theme.effectsSupported
    layer.effect: MultiEffect {
        shadowEnabled:true
        shadowBlur:0.25
        shadowVerticalOffset:3
        shadowOpacity:Theme.cardShadowOpacity
        shadowColor:"#000000"
    }
    Behavior on color { ColorAnimation { duration: Theme.motion } }
}
