pragma ComponentBehavior: Bound
import QtQuick
import QtQuick.Layouts
import SwirlQuick
import "../controls"

Item {
    id:header
    required property var record
    RowLayout {
        anchors.fill:parent
        anchors.leftMargin:Theme.dp(8)
        anchors.rightMargin:Theme.dp(8)
        spacing:Theme.dp(8)
        SwirlIcon {
            name:"chevron-right"
            size:Theme.dp(12)
            rotation:header.record.expanded?90:0
            opacity:header.record.collapsible?1:0.45
            Behavior on rotation {enabled:!SwirlMotion.reduced;NumberAnimation {duration:SwirlMotion.statusDuration;easing.type:Easing.OutCubic}}
        }
        SwirlText {
            text:header.record.sectionName||""
            color:Theme.muted
            font.pixelSize:Theme.fontSize(12)
            font.weight:Font.DemiBold
            Layout.fillWidth:true
            elide:Text.ElideRight
        }
        SwirlText {
            text:qsTr("%1 / %2").arg(header.record.matchedCount||0).arg(header.record.totalCount||0)
            color:Theme.muted
            font.pixelSize:Theme.fontSize(11)
        }
    }
    Accessible.ignored:true
}
