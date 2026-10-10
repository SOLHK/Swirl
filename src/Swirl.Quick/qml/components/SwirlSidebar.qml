import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import QtQuick.Effects
import SwirlQuick
import "../controls"
SwirlGlassPanel {
    id:sidebar
    material:"sidebar"
    property bool compactByWindow:false
    readonly property bool effectivelyCollapsed:AppState.sidebarCollapsed||compactByWindow
    cornerRadius:18
    Layout.preferredWidth:sidebar.effectivelyCollapsed?76:247
    Layout.fillHeight:true
    border.width:0

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
                    layer.enabled:Theme.transparency
                    layer.effect:MultiEffect {
                        shadowEnabled:true
                        shadowBlur:0.16
                        shadowVerticalOffset:2
                        shadowColor:Theme.dark?"#45000000":"#25000000"
                    }
                }
                Column {
                    visible:!sidebar.effectivelyCollapsed
                    Layout.fillWidth:true
                    spacing:2
                    Text { text:"Swirl"; color:Theme.text; font.pixelSize:21; font.weight:Font.DemiBold }
                    Text { text:"专业网络工具"; color:Theme.muted; font.pixelSize:9; font.letterSpacing:1.5 }
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
                            visible:!sidebar.effectivelyCollapsed
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
                            visible:sidebar.effectivelyCollapsed
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
                                compact:sidebar.effectivelyCollapsed
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
            title:sidebar.effectivelyCollapsed?"展开":"收起侧边栏"
            iconName:"layers"
            compact:sidebar.effectivelyCollapsed
            onActivated:{
                if(sidebar.compactByWindow) AppState.toast="请放大窗口以展开导航"
                else AppState.sidebarCollapsed=!AppState.sidebarCollapsed
            }
        }
        Item { Layout.preferredHeight:8 }
    }
}