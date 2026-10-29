import QtQuick
import QtQuick.Layouts
import SwirlQuick
import "../controls"

ColumnLayout {
    id: state
    property string headline: qsTr("暂无内容")
    property string detail: qsTr("调整筛选条件后重试")
    property string iconName: "search"
    spacing: Theme.compactGap
    SwirlIcon {
        name: state.iconName; size: Theme.dp(28); color: Theme.muted
        visible: state.iconName.length > 0
        Layout.alignment: Qt.AlignHCenter
        Layout.bottomMargin: Theme.dp(4)
        Accessible.ignored: true
    }
    SwirlText {
        text: state.headline; textRole: "title"
        color: Theme.text; font.pixelSize: Theme.sectionTitleSize; font.weight: Font.DemiBold
        Layout.fillWidth: true; Layout.minimumWidth: 0
        horizontalAlignment: Text.AlignHCenter; wrapMode: Text.Wrap
        textFormat: Text.PlainText
    }
    SwirlText {
        visible: text.length > 0
        text: state.detail; textRole: "auxiliary"
        color: Theme.muted; font.pixelSize: Theme.captionSize
        Layout.fillWidth: true; Layout.minimumWidth: 0
        horizontalAlignment: Text.AlignHCenter; wrapMode: Text.Wrap
        textFormat: Text.PlainText
    }
}
