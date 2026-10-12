import QtQuick
import SwirlQuick
Item {
    id:mark
    implicitWidth:48; implicitHeight:48
    Image {
        anchors.fill:parent
        source: Theme.dark ? "qrc:/swirl/icons/swirl_knot_mark_dark.svg" : "qrc:/swirl/icons/swirl_knot_mark_light.svg"
        sourceSize: Qt.size(mark.width * Screen.devicePixelRatio, mark.height * Screen.devicePixelRatio)
        fillMode: Image.PreserveAspectFit
    }
    Accessible.name: "Swirl"
}
