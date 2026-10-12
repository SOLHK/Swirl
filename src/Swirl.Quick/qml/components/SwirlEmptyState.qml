import QtQuick
import QtQuick.Layouts
import SwirlQuick
ColumnLayout {
    id:state
    property string headline:"Nothing here yet"
    property string detail:"Try another filter"
    spacing:Theme.dp(8)
    SwirlIcon { name:"search"; size:Theme.dp(32); color:Theme.muted; Layout.alignment:Qt.AlignHCenter }
    Text {
        text:state.headline; color:Theme.text
        font.pixelSize:Theme.fontSize(16); font.weight:Font.DemiBold
        Layout.alignment:Qt.AlignHCenter
    }
    Text {
        text:state.detail; color:Theme.muted
        font.pixelSize:Theme.fontSize(12)
        Layout.alignment:Qt.AlignHCenter
    }
}