import QtQuick
import QtQuick.Layouts
import SwirlQuick
import "../components"
import "../controls"
SwirlGlassPanel {
    ColumnLayout {
        anchors.centerIn:parent; width:Math.min(Theme.dp(480),parent.width-Theme.dp(60)); spacing:Theme.dp(18)
        SwirlIcon { name:"folder"; size:Theme.dp(48); color:Theme.accent; Layout.alignment:Qt.AlignHCenter }
        Text { text:"外部工具"; font.pixelSize:Theme.fontSize(26); font.weight:Font.DemiBold; color:Theme.text; Layout.alignment:Qt.AlignHCenter }
        Text { text:"外部程序启动尚未接入。当前可查看内置网络检测的界面。"; font.pixelSize:Theme.fontSize(16); color:Theme.muted; Layout.fillWidth:true; wrapMode:Text.WordWrap; horizontalAlignment:Text.AlignHCenter }
        SwirlButton { text:"打开网络检测"; Layout.alignment:Qt.AlignHCenter; onClicked:AppState.navigate("toolbox") }
    }
}
