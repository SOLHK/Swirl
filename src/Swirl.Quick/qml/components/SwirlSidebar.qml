import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import SwirlQuick
import "../controls"
SwirlGlassPanel {
    id:sidebar
    material:"sidebar"
    cornerRadius:0
    Layout.preferredWidth:AppState.sidebarCollapsed?76:247
    Layout.fillHeight:true
    border.width:0
    Behavior on Layout.preferredWidth { NumberAnimation { duration:Theme.motion; easing.type:Easing.OutCubic } }
    ColumnLayout {
        anchors.fill:parent
        spacing:4
        Item {
            Layout.fillWidth:true
            Layout.preferredHeight:79
            RowLayout {
                anchors.fill:parent
                anchors.leftMargin:19; anchors.rightMargin:12
                spacing:11
                Image {
                    source:"qrc:/swirl/swirl-256.png"
                    sourceSize.width:43; sourceSize.height:43
                    Layout.preferredWidth:38; Layout.preferredHeight:38
                    fillMode:Image.PreserveAspectFit
                    smooth:true
                }
                Column {
                    visible:!AppState.sidebarCollapsed
                    Layout.fillWidth:true
                    spacing:2
                    Text { text:"Swirl"; color:Theme.text; font.pixelSize:21; font.weight:Font.DemiBold }
                    Text { text:"NETWORK STUDIO"; color:Theme.muted; font.pixelSize:9; font.letterSpacing:1.5 }
                }
            }
        }
        ScrollView {
            id:scroll
            Layout.fillWidth:true
            Layout.fillHeight:true
            clip:true
            ScrollBar.horizontal.policy:ScrollBar.AlwaysOff
            Column {
                id:menuStack
                width:scroll.availableWidth
                spacing:12
                Repeater {
                    model:AppState.groups
                    delegate:Column {
                        width:menuStack.width
                        spacing:2
                        Text {
                            visible:!AppState.sidebarCollapsed
                            text:modelData.title
                            color:Theme.muted
                            font.pixelSize:10
                            font.weight:Font.DemiBold
                            font.letterSpacing:1.15
                            leftPadding:20
                            topPadding:14
                            bottomPadding:7
                        }
                        Rectangle {
                            visible:AppState.sidebarCollapsed
                            width:36; height:1; color:Theme.border
                            anchors.horizontalCenter:parent.horizontalCenter
                        }
                        Repeater {
                            model:modelData.pages
                            delegate:SwirlNavigationItem {
                                width:menuStack.width
                                pageId:modelData.id
                                title:modelData.title
                                iconName:modelData.icon
                                compact:AppState.sidebarCollapsed
                                onActivated:AppState.currentPage=pageId
                            }
                        }
                    }
                }
            }
        }
        Rectangle { Layout.fillWidth:true; height:1; color:Theme.border }
        SwirlNavigationItem {
            Layout.fillWidth:true
            pageId:"toggle-sidebar"
            title:AppState.sidebarCollapsed?"Expand":"Collapse sidebar"
            iconName:"layers"
            compact:AppState.sidebarCollapsed
            onActivated:AppState.sidebarCollapsed=!AppState.sidebarCollapsed
        }
        Item { Layout.preferredHeight:8 }
    }
}