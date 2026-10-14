import QtQuick
import QtQuick.Controls
import QtQuick.Effects
import SwirlQuick
import "../components"
Item {
    id:table
    property var columns:[{key:"name",label:"名称",w:220}]
    property var rows:[]
    property bool incrementalRows:false
    property bool animateRowChanges:true
    property bool animateLatency:false
    property bool minimal:false
    SwirlAnimatedModel{id:stableRows;source:table.incrementalRows?table.rows:[];keyRole:"id"}
    property string selectedId:""
    property Item selectedItem:null
    property int itemHeight:Theme.dp(43)
    property int textPixelSize:12
    property int headerPixelSize:11
    property real headerHeight:Theme.dp(26)
    property real emptyStripeHeight:itemHeight
    property bool fillEmptyRows:false
    property bool gridLines:false
    property real cellPadding:Theme.dp(12)
    property real stripeInset:0
    property real stripeRadius:0
    readonly property real totalWidth:columns.reduce(function(v,c){return v+Theme.dp(c.w)},0)
    function columnWidth(column) { return Math.max(Theme.dp(12),width*Theme.dp(column.w)/totalWidth) }
    signal rowSelected(var record)
    signal rowActivated(var record, Item titleItem)
    signal rowEdited(var record, Item rowItem)
    clip:true
    layer.enabled:Theme.effectsSupported && !minimal
    layer.effect:MultiEffect { maskEnabled:true; maskSource:cornerMask }
    SwirlContinuousSurface { id:cornerMask; anchors.fill:parent; radius:Theme.tableRadius; layer.enabled:true; visible:false; color:"white" }
    SwirlContinuousSurface { anchors.fill:parent; visible:!table.minimal; radius:Theme.tableRadius; color:"transparent"; border.width:Theme.borderWidth; border.color:Theme.border; z:10 }
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
                width:parent.width; height:table.headerHeight
                color:Theme.surface
                radius: 0
                Row {
                    anchors.fill:parent
                    Repeater {
                        model:table.columns
                        delegate:Item {
                            width:table.columnWidth(modelData); height:table.headerHeight
                            Rectangle{visible:index>0 && !table.minimal;x:0;y:Theme.dp(5);width:Theme.dp(1);height:parent.height-Theme.dp(10);color:Theme.border}
                            Text {
                                text:AppState.zh(modelData.label)
                                color:table.minimal?Theme.muted:Theme.text
                                font.pixelSize:Theme.fontSize(table.headerPixelSize)
                                font.family:Theme.fontFamily
                                font.weight:Font.Normal
                                anchors.fill:parent
                                anchors.leftMargin:table.cellPadding
                                verticalAlignment:Text.AlignVCenter
                                elide:Text.ElideRight
                            }
                        }
                    }
                }
            }
            ListView {
                    add: Transition { enabled:table.animateRowChanges && !SwirlMotion.reduced; NumberAnimation {property:"opacity";from:0;to:1;duration:SwirlMotion.duration} }
                    remove: Transition { enabled:table.animateRowChanges && !SwirlMotion.reduced; NumberAnimation {property:"opacity";to:0;duration:SwirlMotion.duration} }
                    move: Transition {enabled:table.animateRowChanges && !SwirlMotion.reduced;SmoothedAnimation {properties:"x,y";velocity:1200*SwirlMotion.speed;duration:SwirlMotion.duration}}
                    displaced: Transition { enabled:table.animateRowChanges && !SwirlMotion.reduced; SmoothedAnimation {properties:"x,y";velocity:1200*SwirlMotion.speed;duration:SwirlMotion.duration} }
                id:list
                Repeater {model:table.fillEmptyRows?Math.max(0,Math.ceil((list.height-table.rows.length*table.itemHeight)/table.emptyStripeHeight)):0
                    Rectangle{required property int index;x:table.stripeInset;y:table.rows.length*table.itemHeight+index*table.emptyStripeHeight;width:list.width-2*table.stripeInset;height:table.emptyStripeHeight;radius:table.stripeRadius;color:(index+table.rows.length)%2?Theme.field:Theme.surface;z:-1}
                }
                width:parent.width
                height:Math.floor(Math.max(0,horizontal.height-table.headerHeight)/table.itemHeight)*table.itemHeight
                clip:true
                model:table.incrementalRows?stableRows:table.rows
                boundsBehavior:Flickable.StopAtBounds
                ScrollBar.vertical:ScrollBar {}
                delegate:Rectangle {
                    id:recordRow
                    z:1
                    width:list.width; height:table.itemHeight
                    property var record:table.incrementalRows?model.entry:modelData
                    property Item titleElement:null
                    radius:table.minimal?Theme.dp(10):0
                    color:table.selectedId===String(record.id||record.name) ? (table.minimal?Theme.withAlpha(Theme.accent,0.12):Theme.selected) :
                          mouse.containsMouse ? (table.minimal?Theme.withAlpha(Theme.accent,0.055):Theme.hover) : table.minimal?"transparent":(index%2?Theme.field:Theme.surface)
                    Behavior on color { ColorAnimation { duration:Theme.motion } }
                    Rectangle { anchors.bottom:parent.bottom; width:parent.width; height:Theme.dp(1); color:Theme.border; opacity:table.fillEmptyRows||table.minimal?0:0.6 }
                    Row {
                        anchors.fill:parent
                        Repeater {
                            model:table.columns
                            delegate:Item {
                                width:table.columnWidth(modelData); height:table.itemHeight
                                Text {
                                    anchors.fill:parent
                                    anchors.leftMargin:table.cellPadding; anchors.rightMargin:Theme.dp(8)
                                    id:cell
                                    Component.onCompleted:if(modelData.key==="name")recordRow.titleElement=cell
                                    readonly property string raw:String(recordRow.record[modelData.key]===undefined?"":recordRow.record[modelData.key])
                                    readonly property real measured:table.animateLatency && modelData.key==="latency" && raw.length && isFinite(Number(raw))?Number(raw):-1
                                    property real displayed:-1
                                    property real previous:-1
                                    onMeasuredChanged:{if(measured>=0 && previous>=0 && !SwirlMotion.reduced)numberSlide.restart();else{numberSlide.stop();displayed=measured}previous=measured}
                                    SmoothedAnimation{id:numberSlide;target:cell;property:"displayed";to:cell.measured;duration:SwirlMotion.duration;velocity:-1}
                                    text:measured>=0?String(Math.round(displayed)):raw
                                    textFormat:Text.PlainText
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
                            table.selectedItem=recordRow
                            if(!table.incrementalRows)table.selectedId=String(recordRow.record.id||recordRow.record.name)
                            table.rowSelected(recordRow.record)
                            if(event.button===Qt.LeftButton)table.rowActivated(recordRow.record,table.minimal?recordRow:recordRow.titleElement)
                            if(event.button===Qt.RightButton) contextMenu.popup()
                        }
                        onDoubleClicked:table.rowEdited(recordRow.record,recordRow)
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
        Item {visible:table.gridLines;y:table.headerHeight;width:horizontal.contentWidth;height:horizontal.height-table.headerHeight;z:3
            Row{anchors.fill:parent;Repeater{model:table.columns;Item{width:table.columnWidth(modelData);height:parent.height;Rectangle{visible:index>0;width:Theme.dp(1);height:parent.height;color:Theme.border}}}}
        }
    }
}
