import QtQuick
import QtQuick.Controls
import SwirlQuick
Item {
    id:table
    property var columns:[{key:"name",label:"名称",w:220}]
    property var rows:[]
    property string selectedId:""
    property int itemHeight:43
    readonly property int totalWidth:columns.reduce(function(v,c){return v+c.w},0)
    signal rowSelected(var record)
    clip:true
    Flickable {
        id:horizontal
        anchors.fill:parent
        contentWidth:Math.max(width,table.totalWidth)
        contentHeight:height
        flickableDirection:Flickable.HorizontalFlick
        boundsBehavior:Flickable.StopAtBounds
        Column {
            width:horizontal.contentWidth
            spacing:0
            Rectangle {
                width:parent.width; height:39
                color:Theme.material("secondary")
                radius:10
                Row {
                    anchors.fill:parent
                    Repeater {
                        model:table.columns
                        delegate:Item {
                            width:modelData.w; height:39
                            Text {
                                text:modelData.label
                                color:Theme.muted
                                font.pixelSize:11
                                font.weight:Font.DemiBold
                                anchors.fill:parent
                                anchors.leftMargin:12
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
                height:Math.max(0,horizontal.height-39)
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
                    Rectangle { anchors.bottom:parent.bottom; width:parent.width; height:1; color:Theme.border; opacity:0.6 }
                    Row {
                        anchors.fill:parent
                        Repeater {
                            model:table.columns
                            delegate:Item {
                                width:modelData.w; height:table.itemHeight
                                Text {
                                    anchors.fill:parent
                                    anchors.leftMargin:12; anchors.rightMargin:8
                                    text:String(recordRow.record[modelData.key]===undefined?"":recordRow.record[modelData.key])
                                    color:Theme.text
                                    font.pixelSize:12
                                    font.family:"Segoe UI"
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