import QtQuick
import QtQuick.Controls
import QtQuick.Effects
import SwirlQuick
Item {
    id:table
    property var columns:[{key:"name",label:"名称",w:220}]
    property var rows:[]
    property string selectedId:""
    property int itemHeight:Theme.dp(43)
    property int textPixelSize:12
    property int headerPixelSize:11
    readonly property real totalWidth:columns.reduce(function(v,c){return v+Theme.dp(c.w)},0)
    function columnWidth(column) { return Math.max(Theme.dp(48),width*Theme.dp(column.w)/totalWidth) }
    signal rowSelected(var record)
    clip:true
    layer.enabled:Theme.effectsSupported
    layer.effect:MultiEffect { maskEnabled:true; maskSource:cornerMask }
    Rectangle { id:cornerMask; anchors.fill:parent; radius:Theme.containerRadius; layer.enabled:true; visible:false; color:"white" }
    Flickable {
        id:horizontal
        anchors.fill:parent
        contentWidth:table.columns.reduce(function(v,c){return v+table.columnWidth(c)},0)
        contentHeight:height
        flickableDirection:Flickable.HorizontalFlick
        boundsBehavior:Flickable.StopAtBounds
        Column {
            width:horizontal.contentWidth
            spacing:Theme.dp(0)
            Rectangle {
                width:parent.width; height:Theme.dp(39)
                color:Theme.material("secondary")
                radius: Theme.roundedRadius(width,height)
                Row {
                    anchors.fill:parent
                    Repeater {
                        model:table.columns
                        delegate:Item {
                            width:table.columnWidth(modelData); height:Theme.dp(39)
                            Text {
                                text:AppState.zh(modelData.label)
                                color:Theme.muted
                                font.pixelSize:Theme.fontSize(table.headerPixelSize)
                                font.family:Theme.fontFamily
                                font.weight:Font.DemiBold
                                anchors.fill:parent
                                anchors.leftMargin:Theme.dp(12)
                                verticalAlignment:Text.AlignVCenter
                                elide:Text.ElideRight
                            }
                        }
                    }
                }
            }
            ListView {
                id:list
                width:parent.width
                height:Math.floor(Math.max(0,horizontal.height-Theme.dp(39))/table.itemHeight)*table.itemHeight
                clip:true
                model:table.rows
                boundsBehavior:Flickable.StopAtBounds
                ScrollBar.vertical:ScrollBar {}
                delegate:Rectangle {
                    id:recordRow
                    width:list.width; height:table.itemHeight
                    property var record:modelData
                    color:table.selectedId===String(record.id||record.name) ? Theme.selected :
                          mouse.containsMouse ? Theme.hover : (index%2?Theme.material("secondary"):Theme.material("content"))
                    Behavior on color { ColorAnimation { duration:Theme.motion } }
                    Rectangle { anchors.bottom:parent.bottom; width:parent.width; height:Theme.dp(1); color:Theme.border; opacity:0.6 }
                    Row {
                        anchors.fill:parent
                        Repeater {
                            model:table.columns
                            delegate:Item {
                                width:table.columnWidth(modelData); height:table.itemHeight
                                Text {
                                    anchors.fill:parent
                                    anchors.leftMargin:Theme.dp(12); anchors.rightMargin:Theme.dp(8)
                                    text:AppState.zh(String(recordRow.record[modelData.key]===undefined?"":recordRow.record[modelData.key]))
                                    color:Theme.text
                                    font.pixelSize:Theme.fontSize(table.textPixelSize)
                                    font.family:Theme.fontFamily
                                    verticalAlignment:Text.AlignVCenter
                                    elide:Text.ElideRight
                                }
                            }
                        }
                    }
                    MouseArea {
                        id:mouse; anchors.fill:parent; hoverEnabled:true
                        acceptedButtons:Qt.LeftButton|Qt.RightButton
                        onClicked:function(event){
                            table.selectedId=String(recordRow.record.id||recordRow.record.name)
                            table.rowSelected(recordRow.record)
                            if(event.button===Qt.RightButton) contextMenu.popup()
                        }
                        SwirlContextMenu {
                            id:contextMenu
                            payload:table.columns.map(function(c){
                                return c.label + ": " + String(recordRow.record[c.key] === undefined?"":recordRow.record[c.key])
                            }).join("\n")
                        }
                    }
                }
            }
        }
    }
}
