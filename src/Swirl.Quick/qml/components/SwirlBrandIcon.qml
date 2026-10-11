import QtQuick
Item {
    id:mark
    implicitWidth:48; implicitHeight:48
    Image {
        anchors.fill:parent
        source: "qrc:/swirl/icons/swirl_wave_mark.svg"
        sourceSize: Qt.size(mark.width * Screen.devicePixelRatio, mark.height * Screen.devicePixelRatio)
        fillMode: Image.PreserveAspectFit
    }
    Accessible.name: "Swirl"
}
