import QtQuick
import QtQuick.Controls
import SwirlQuick
import "../components"
Item {
    id:table
    property var columns:[{key:"name",label:"名称",w:220}]
    property var rows:[]
    property bool incrementalRows:false
    property bool followTail:false
    property string anchorKey:""
    property real anchorOffset:0
    property bool wasAtEnd:true
    function saveViewport(){if(!list)return;wasAtEnd=list.atYEnd;const index=list.indexAt(1,list.contentY+1);anchorKey=index>=0&&index<stableRows.count?stableRows.get(index).motionKey:"";anchorOffset=index*itemHeight-list.contentY}
    function restoreViewport(){if(!list)return;if(followTail&&wasAtEnd){list.positionViewAtEnd();return}if(!anchorKey.length)return;for(let i=0;i<stableRows.count;i++)if(stableRows.get(i).motionKey===anchorKey){list.contentY=Math.max(0,Math.min(i*itemHeight-anchorOffset,Math.max(0,list.contentHeight-list.height)));return}}
    Connections {target:stableRows;function onAboutToSync(){table.saveViewport()}function onSynced(){Qt.callLater(table.restoreViewport)}}
    property bool managedSelection:false
    property bool animateRowChanges:false
    property bool animateLatency:false
    property bool minimal:false
    SwirlAnimatedModel{id:stableRows;source:table.incrementalRows?table.rows:[];keyRole:"id"}
    property string selectedId:""
    property Item selectedItem:null
    property int itemHeight:Theme.tableRowHeight
    property int textPixelSize:12
    property int headerPixelSize:11
    property real headerHeight:Theme.tableHeaderHeight
    property real emptyStripeHeight:itemHeight
    property bool fillEmptyRows:false
    property bool gridLines:false
    property real cellPadding:Theme.dp(12)
    property real stripeInset:0
    property real stripeRadius:0
    readonly property real totalWidth:columns.reduce(function(v,c){return v+c.w},0)
    readonly property real minimumGridWidth:columns.reduce(function(v,c){return v+Theme.dp(c.min||12)},0)
    readonly property real gridWidth:Math.max(Math.floor(width),minimumGridWidth)
    // Rounded cumulative edges keep header/body columns aligned at all scales.
    function columnWidth(column) {
        let before=0
        for(const item of columns){if(item.key===column.key)break;before+=item.w}
        const flexible=Math.max(0,gridWidth-minimumGridWidth)
        return Theme.dp(column.min||12)+Math.round(flexible*(before+column.w)/totalWidth)-Math.round(flexible*before/totalWidth)
    }
    function chooseRow(row,activate) {
        if(!row)return
        selectedItem=row
        if(!incrementalRows&&!managedSelection)selectedId=String(row.record.id||row.record.name)
        rowSelected(row.record)
        if(activate)rowActivated(row.record,minimal?row:row.titleElement)
    }
    signal rowSelected(var record)
    signal rowActivated(var record, Item titleItem)
    signal rowEdited(var record, Item rowItem)
    clip:true
    // Rectangular viewport clipping keeps glyphs on the native render path.
    SwirlContinuousSurface { anchors.fill:parent; visible:!table.minimal; radius:Theme.tableRadius; color:"transparent"; border.width:Theme.borderWidth; border.color:Theme.border; z:10 }
    Flickable {
        id:horizontal
        anchors.fill:parent
        contentWidth:table.gridWidth
        contentHeight:height
        flickableDirection:Flickable.HorizontalFlick
        boundsBehavior:Flickable.StopAtBounds
        pixelAligned:false
        ScrollBar.horizontal:SwirlScrollBar {policy:horizontal.contentWidth>horizontal.width?ScrollBar.AlwaysOn:ScrollBar.AlwaysOff}
            Rectangle {
                z:1;width:horizontal.contentWidth;height:table.headerHeight
                color:Theme.field
                radius: Theme.tableRadius
                Row {
                    anchors.fill:parent
                    Repeater {
                        model:table.columns
                        delegate:Item {
                            width:table.columnWidth(modelData); height:table.headerHeight
                            Rectangle{visible:index>0 && !table.minimal;x:0;y:Theme.dp(5);width:Theme.dp(1);height:parent.height-Theme.dp(10);color:Theme.border}
                            SwirlText {renderType:Text.NativeRendering;
                                text:AppState.zh(modelData.label)
                                color:table.minimal?Theme.muted:Theme.text
                                font.pixelSize:Theme.fontSize(table.headerPixelSize)
                                font.family:Theme.fontFamily
                                font.weight:Theme.bodyFontWeight
                                anchors.fill:parent
                                anchors.leftMargin:table.cellPadding
                                anchors.rightMargin:Theme.dp(8)
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
                objectName:"tableRowsViewport"
                Repeater {model:table.fillEmptyRows?Math.max(0,Math.ceil((list.height-table.rows.length*table.itemHeight)/table.emptyStripeHeight)):0
                    Rectangle{required property int index;x:table.stripeInset;y:table.rows.length*table.itemHeight+index*table.emptyStripeHeight;width:list.width-2*table.stripeInset;height:table.emptyStripeHeight;radius:table.stripeRadius;color:(index+table.rows.length)%2?Theme.field:Theme.surface;z:-1}
                }
                y:table.headerHeight
                width:horizontal.contentWidth
                height:Math.max(0,horizontal.height-table.headerHeight-(horizontal.contentWidth>horizontal.width?Theme.dp(10):0))
                clip:true
                model:table.incrementalRows?stableRows:table.rows
                boundsBehavior:Flickable.StopAtBounds
                pixelAligned:false
                activeFocusOnTab:true
                keyNavigationEnabled:true
                highlightMoveDuration:0
                Keys.onReturnPressed:table.chooseRow(currentItem,true)
                Keys.onEnterPressed:table.chooseRow(currentItem,true)
                Keys.onSpacePressed:table.chooseRow(currentItem,true)
                ScrollBar.vertical:SwirlScrollBar {parent:table;z:11;anchors.right:parent.right;y:table.headerHeight;height:list.height}
                delegate:Rectangle {
                    id:recordRow
                    z:1
                    width:list.width; height:table.itemHeight
                    property var record:table.incrementalRows?model.entry:modelData
                    property Item titleElement:null
                    Accessible.role:Accessible.ListItem
                    Accessible.selected:table.selectedId===String(record.id||record.name)
                    Accessible.name:table.columns.map(c=>c.label+"："+String(recordRow.record[c.key]===undefined?"":recordRow.record[c.key])).join("，")
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
                                SwirlText {renderType:Text.NativeRendering;
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
                                HoverHandler {id:cellHover}
                                ToolTip.visible:cellHover.hovered&&cell.truncated
                                ToolTip.text:cell.raw;ToolTip.delay:600
                            }
                        }
                    }
                    MouseArea {
                        id:mouse; anchors.fill:parent; hoverEnabled:true
                        cursorShape:Qt.PointingHandCursor
                        acceptedButtons:Qt.LeftButton|Qt.RightButton
                        onClicked:function(event){
                            list.forceActiveFocus();list.currentIndex=index
                            table.chooseRow(recordRow,event.button===Qt.LeftButton)
                            if(event.button===Qt.RightButton) contextMenu.popup()
                        }
                        onDoubleClicked:table.rowEdited(recordRow.record,recordRow)
                        SwirlContextMenu {
                            id:contextMenu
                            parent:mouse
                            payload:table.columns.map(function(c){
                                return c.label + ": " + String(recordRow.record[c.key] === undefined?"":recordRow.record[c.key])
                            }).join("\n")
                        }
                    }
                }
            }
        Item {visible:table.gridLines;y:table.headerHeight;width:horizontal.contentWidth;height:horizontal.height-table.headerHeight;z:3
            Row{anchors.fill:parent;Repeater{model:table.columns;Item{width:table.columnWidth(modelData);height:parent.height;Rectangle{visible:index>0;width:Theme.dp(1);height:parent.height;color:Theme.border}}}}
        }
    }
}
