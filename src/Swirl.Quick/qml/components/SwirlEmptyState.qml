import QtQuick
import QtQuick.Layouts
import SwirlQuick
ColumnLayout {
    id:state
    property string headline:"Nothing here yet"
    property string detail:"Try another filter"
    spacing:8
    SwirlIcon { name:"search"; size:32; color:Theme.muted; Layout.alignment:Qt.AlignHCenter }
    Text {
        text:state.headline; color:Theme.text
        font.pixelSize:16; font.weight:Font.DemiBold
        Layout.alignment:Qt.AlignHCenter
    }
    Text {
        text:state.detail; color:Theme.muted
        font.pixelSize:12
        Layout.alignment:Qt.AlignHCenter
    }
}