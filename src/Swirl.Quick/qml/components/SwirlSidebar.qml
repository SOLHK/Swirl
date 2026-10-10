import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import SwirlQuick
import "../controls"
Item {
    id: sidebar
    property bool compactByWindow: false
    readonly property bool effectivelyCollapsed: AppState.sidebarCollapsed || compactByWindow
    implicitWidth: Theme.sidebarWidth
    ColumnLayout {
        anchors.fill:parent; anchors.leftMargin:sidebar.effectivelyCollapsed ? 8 : 14; anchors.rightMargin:sidebar.effectivelyCollapsed ? 8 : 12; anchors.bottomMargin:20
        spacing:0
        Item {
            Layout.fillWidth:true; Layout.preferredHeight:148
            Row {
                x:sidebar.effectivelyCollapsed ? 5 : 7; y:20; spacing:sidebar.effectivelyCollapsed ? 5 : 10
                Repeater {
                    model:["#FF6055","#FFBD2E","#00C84D"]
                    Button {
                        required property int index
                        required property string modelData
                        width:sidebar.effectivelyCollapsed ? 15 : 18; height:width; hoverEnabled:true
                        background:Rectangle { radius:Theme.pillRadius(height); color:parent.modelData; opacity:parent.down ? 0.7 : 1 }
                        contentItem: Text { text:parent.hovered ? parent.index===0 ? "×" : parent.index===1 ? "−" : "+" : ""; font.pixelSize:14; color:"#703030"; horizontalAlignment:Text.AlignHCenter; verticalAlignment:Text.AlignVCenter }
                        onClicked:{ if(index===0) sidebar.Window.window.close(); else if(index===1) sidebar.Window.window.showMinimized(); else if(sidebar.Window.window.visibility===Window.Maximized) sidebar.Window.window.showNormal(); else sidebar.Window.window.showMaximized() }
                        Accessible.name:index===0 ? "关闭" : index===1 ? "最小化" : "最大化或还原"
                    }
                }
            }
            RowLayout {
                x:7; y:64; width:parent.width-12; spacing:16
                Rectangle {
                    width:sidebar.effectivelyCollapsed ? 48 : 64; height:width; radius:Theme.secondaryRadius; color:Theme.raised
                    Image { anchors.fill:parent; anchors.margins:6; source:"qrc:/swirl/swirl-256.png"; fillMode:Image.PreserveAspectFit; sourceSize:Qt.size(128,128) }
                }
                Column {
                    visible:!sidebar.effectivelyCollapsed
                    spacing:3
                    Text { text:"Swirl"; font.family:"Segoe UI"; font.pixelSize:24; font.weight:Font.DemiBold; color:Theme.text }
                    Text { text:"专业网络工具"; font.pixelSize:16; color:Theme.muted }
                }
            }
        }
        ScrollView {
            id:scroll; Layout.fillWidth:true; Layout.fillHeight:true; clip:true
            ScrollBar.horizontal.policy:ScrollBar.AlwaysOff
            Column {
                width:scroll.availableWidth; spacing:0
                Repeater {
                    model:AppState.navigationGroups
                    delegate: Column {
                        required property var modelData
                        width:parent.width
                        Item {
                            visible:modelData.title.length>0; width:parent.width; height:visible ? 42 : 0
                            Text { visible:!sidebar.effectivelyCollapsed; x:16; anchors.verticalCenter:parent.verticalCenter; text:modelData.title; font.pixelSize:15; color:Theme.muted; opacity:0.8 }
                            Rectangle { x:sidebar.effectivelyCollapsed ? 15 : 74; width:sidebar.effectivelyCollapsed ? 36 : parent.width-90; height:1; anchors.verticalCenter:parent.verticalCenter; color:Theme.border }
                        }
                        Repeater {
                            model:modelData.pages
                            delegate:SwirlNavigationItem {
                                required property var modelData
                                width:parent.width; pageId:modelData.id; title:modelData.title; iconName:modelData.icon; compact:sidebar.effectivelyCollapsed
                                onActivated:AppState.navigate(pageId)
                            }
                        }
                    }
                }
            }
        }
        Button {
            id:status; Layout.fillWidth:true; Layout.preferredHeight:68; Layout.topMargin:12
            hoverEnabled:true
            background:SwirlPillSurface { hovered:status.hovered; pressed:status.down }
            contentItem: RowLayout {
                spacing:15
                Rectangle {
                    Layout.leftMargin:sidebar.effectivelyCollapsed ? 7 : 10; width:42; height:42; radius:Theme.pillRadius(height); color:Theme.raised
                    Rectangle { anchors.centerIn:parent; width:30; height:30; radius:Theme.pillRadius(height); color:AppState.proxyOn ? Theme.accent : "#CCCFD5" }
                }
                Column {
                    visible:!sidebar.effectivelyCollapsed
                    Layout.fillWidth:true; spacing:1
                    Text { text:AppState.proxyOn ? "演示已连接" : "未连接"; color:Theme.text; font.pixelSize:18; font.weight:Font.DemiBold }
                    Text { text:AppState.proxyOn ? "点击断开演示" : "点击连接"; color:Theme.muted; font.pixelSize:15 }
                }
                SwirlIcon { visible:!sidebar.effectivelyCollapsed; Layout.rightMargin:16; name:"chevron-right"; size:19 }
            }
            onClicked:AppState.setConnection(!AppState.proxyOn)
            Accessible.name:AppState.proxyOn ? "断开演示连接" : "开启演示连接"
        }
    }
}
