import QtQuick
import QtQuick.Layouts
import SwirlQuick
SwirlGlassPanel {
    id: card
    material: "secondary"
    property string label: "下载速度"
    property string value: "0 MB/s"
    property string secondary: "本次会话"
    property string iconName: "activity"
    property color valueColor: Theme.text
    implicitHeight: 137
    implicitWidth: 175
    ColumnLayout {
        anchors.fill: parent; anchors.margins: 19
        spacing: 9
        RowLayout {
            Layout.fillWidth: true
            SwirlIcon { name: card.iconName; size: 17; color: Theme.accent }
            Text { text: card.label; font.pixelSize: 12; color: Theme.muted; Layout.fillWidth: true }
        }
        Text {
            text: card.value; color: card.valueColor
            font.pixelSize: 24; font.weight: Font.DemiBold
            font.family: "Segoe UI Variable"
            elide: Text.ElideRight
            Layout.fillWidth: true
        }
        Text { text: card.secondary; font.pixelSize: 11; color: Theme.muted; Layout.fillWidth: true; elide: Text.ElideRight }
    }
}
