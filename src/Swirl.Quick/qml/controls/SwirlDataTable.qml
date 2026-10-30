import QtQuick
import QtQuick.Controls
import SwirlQuick
import "../components"
Item {
    id:table
    property var columns:[{key:"name",label:"名称",w:220}]
    property var rows:[]
    property var externalModel:null
    property bool incrementalRows:false
    property bool sectioned:false
    property real sectionHeight:Theme.dp(32)
    property Component sectionDelegate:null
    property Component rowActions:null
    property real rowActionsWidth:0
    property bool activateOnSingleClick:true
    property bool followTail:false
    property string anchorKey:""
    property real anchorOffset:0
    property bool wasAtEnd:true
    property var visiblePositions:({})
    property int projectionGeneration:0
    function recordAt(index) {
        if(index<0||index>=list.count)return null
        if(externalModel!==null)return typeof externalModel.get==="function"?externalModel.get(index):null
        return incrementalRows?stableRows.get(index).entry:rows[index]
    }
    function displayKey(record,index) {
        if(!record)return ""
        if(sectioned)return String(record.displayKey||record.id||"")
        return incrementalRows&&index>=0&&index<stableRows.count?String(stableRows.get(index).motionKey):String(record.id||record.name||"")
    }
    function rowForKey(key) {
        if(externalModel!==null&&typeof externalModel.rowForDisplayKey==="function")return externalModel.rowForDisplayKey(key)
        for(let i=0;i<list.count;++i)if(displayKey(recordAt(i),i)===key)return i
        return -1
    }
    function saveViewport() {
        wasAtEnd=list.atYEnd
        const index=list.indexAt(1,list.contentY+1)
        const item=index>=0?list.itemAtIndex(index):null
        anchorKey=item?displayKey(item.record,index):""
        anchorOffset=item?item.y-list.contentY:0
    }
    function animateVisibleRows() {
        if(!sectioned||!animateRowChanges||SwirlMotion.reduced||list.moving)return
        for(const item of list.contentItem.children) {
            if(!item.presentationKey||item.pooled||item.y+item.height<list.contentY||item.y>list.contentY+list.height)continue
            const before=visiblePositions[item.presentationKey]
            if(before!==undefined)item.presentFrom(before-(item.y-list.contentY))
        }
        visiblePositions={}
    }
    function restoreViewport() {
        const generation=projectionGeneration
        if(followTail&&wasAtEnd){list.positionViewAtEnd();animateVisibleRows();return}
        const index=anchorKey.length?rowForKey(anchorKey):-1
        if(index<0){animateVisibleRows();return}
        list.positionViewAtIndex(index,ListView.Beginning)
        Qt.callLater(function(){
            if(generation!==table.projectionGeneration)return
            const item=list.itemAtIndex(index)
            if(item)list.contentY=Math.max(list.originY,Math.min(item.y-table.anchorOffset,list.originY+Math.max(0,list.contentHeight-list.height)))
            table.animateVisibleRows()
        })
    }
    function beginProjection() {
        ++projectionGeneration
        saveViewport()
        const positions={}
        if(sectioned&&animateRowChanges&&!SwirlMotion.reduced&&!list.moving)
            for(const item of list.contentItem.children)
                if(item.presentationKey&&!item.pooled&&item.y+item.height>=list.contentY&&item.y<=list.contentY+list.height)
                    positions[item.presentationKey]=item.y+item.visualOffsetY-list.contentY
        visiblePositions=positions
    }
    function endProjection() {
        const generation=projectionGeneration
        Qt.callLater(function(){if(generation===table.projectionGeneration){list.forceLayout();table.restoreViewport()}})
    }
    Connections {target:stableRows;function onAboutToSync(){table.beginProjection()}function onSynced(){table.endProjection()}}
    Connections {target:table.sectioned?table.externalModel:null;ignoreUnknownSignals:true;function onAboutToSync(){table.beginProjection()}function onSynced(){table.endProjection()}}
    property bool managedSelection:false
    property bool animateRowChanges:false
    property bool animateLatency:false
    property bool minimal:false
    property alias scrollPosition:list.contentY
    function scrollToBeginning(){anchorKey="";list.positionViewAtBeginning()}
    function positionRow(key) {
        Qt.callLater(function() {
            list.forceLayout()
            const index = table.rowForKey(key)
            if (index >= 0) list.positionViewAtIndex(index, ListView.Contain)
        })
    }
    function focusRowAt(index){const row=list.itemAtIndex(index);if(row){list.currentIndex=index;chooseRow(row,false)}}
    readonly property int renderedRows:list.contentItem.children.length
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
    readonly property real minimumColumnWidth:columns.reduce(function(v,c){return v+Theme.dp(c.min||12)},0)
    readonly property real actionWidth:rowActions!==null?rowActionsWidth:0
    readonly property real minimumGridWidth:minimumColumnWidth+actionWidth
    readonly property real gridWidth:Math.max(Math.floor(width),minimumGridWidth)
    // Rounded cumulative edges keep header/body columns aligned at all scales.
    function columnWidth(column) {
        let before=0
        for(const item of columns){if(item.key===column.key)break;before+=item.w}
        const flexible=Math.max(0,gridWidth-actionWidth-minimumColumnWidth)
        return Theme.dp(column.min||12)+Math.round(flexible*(before+column.w)/totalWidth)-Math.round(flexible*before/totalWidth)
    }
    function chooseRow(row,activate) {
        if(!row)return
        if(row.sectionRow){if(activate)sectionActivated(String(row.record.sectionKey));return}
        selectedItem=row
        if(!incrementalRows&&!managedSelection)selectedId=String(row.record.id||row.record.name)
        rowSelected(row.record)
        if(activate)rowActivated(row.record,minimal?row:row.titleElement)
    }
    signal rowSelected(var record)
    signal rowActivated(var record, Item titleItem)
    signal rowEdited(var record, Item rowItem)
    signal sectionActivated(string sectionKey)
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
                                textRole:"smallLabel"
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
                    add: Transition { enabled:table.animateRowChanges && !SwirlMotion.reduced; ParallelAnimation { NumberAnimation {property:"opacity";from:0;to:1;duration:SwirlMotion.duration} NumberAnimation {property:"scale";from:table.sectioned?0.985:1;to:1;duration:SwirlMotion.duration;easing.type:Easing.OutCubic} } }
                    remove: Transition { enabled:table.animateRowChanges && !SwirlMotion.reduced; ParallelAnimation { NumberAnimation {property:"opacity";to:0;duration:table.sectioned?SwirlMotion.exitDuration:SwirlMotion.duration} NumberAnimation {property:"scale";to:table.sectioned?0.985:1;duration:table.sectioned?SwirlMotion.exitDuration:SwirlMotion.duration;easing.type:Easing.InCubic} } }
                    move: Transition {enabled:table.animateRowChanges && !table.sectioned && !SwirlMotion.reduced;SmoothedAnimation {properties:"x,y";velocity:1200*SwirlMotion.speed;duration:SwirlMotion.duration}}
                    displaced: Transition { enabled:table.animateRowChanges && !table.sectioned && !SwirlMotion.reduced; SmoothedAnimation {properties:"x,y";velocity:1200*SwirlMotion.speed;duration:SwirlMotion.duration} }
                id:list
                objectName:"tableRowsViewport"
                Repeater {model:table.fillEmptyRows?Math.max(0,Math.ceil((list.height-table.rows.length*table.itemHeight)/table.emptyStripeHeight)):0
                    Rectangle{required property int index;x:table.stripeInset;y:table.rows.length*table.itemHeight+index*table.emptyStripeHeight;width:list.width-2*table.stripeInset;height:table.emptyStripeHeight;radius:table.stripeRadius;color:(index+table.rows.length)%2?Theme.field:Theme.surface;z:-1}
                }
                y:table.headerHeight
                width:horizontal.contentWidth
                height:Math.max(0,horizontal.height-table.headerHeight-(horizontal.contentWidth>horizontal.width?Theme.dp(10):0))
                clip:true
                model:table.externalModel!==null?table.externalModel:table.incrementalRows?stableRows:table.rows
                reuseItems:table.externalModel!==null
                boundsBehavior:Flickable.StopAtBounds
                pixelAligned:false
                activeFocusOnTab:true
                keyNavigationEnabled:true
                highlightMoveDuration:0
                Keys.onReturnPressed:table.chooseRow(currentItem,true)
                Keys.onEnterPressed:table.chooseRow(currentItem,true)
                Keys.onSpacePressed:table.chooseRow(currentItem,true)
                Keys.onPressed:function(event){
                    if(table.sectioned&&[Qt.Key_Up,Qt.Key_Down,Qt.Key_Home,Qt.Key_End,Qt.Key_PageUp,Qt.Key_PageDown].indexOf(event.key)>=0)
                        Qt.callLater(function(){if(list.currentItem)table.chooseRow(list.currentItem,false)})
                    event.accepted=false
                }
                ScrollBar.vertical:SwirlScrollBar {parent:table;z:11;anchors.right:parent.right;y:table.headerHeight;height:list.height}
                delegate:Item {
                    id:recordRow
                    z:1
                    width:list.width; height:sectionRow?table.sectionHeight:table.itemHeight
                    property var record:table.externalModel!==null||table.incrementalRows?model.entry:modelData
                    readonly property bool sectionRow:table.sectioned&&record&&record.rowKind==="section"
                    readonly property string presentationKey:table.displayKey(record,index)
                    property bool pooled:false
                    SwirlInteractionMotion {
                        id:rowFeedback
                        hovered:!recordRow.pooled && mouse.containsMouse
                        pressed:!recordRow.pooled && mouse.pressed
                        focused:!recordRow.pooled && list.activeFocus && list.currentIndex===index
                        controlEnabled:recordRow.enabled && !recordRow.pooled
                    }
                    property real visualOffsetY:0
                    function clearPresentation(){if(positionShift)positionShift.stop();if(rowFeedback)rowFeedback.finish();visualOffsetY=0;scale=1;opacity=1;if(contextMenu)contextMenu.close();if(actionsLoader.item&&actionsLoader.item.closeMenu)actionsLoader.item.closeMenu()}
                    function presentFrom(offset){positionShift.stop();visualOffsetY=offset;if(Math.abs(offset)>0.25){positionShift.to=0;positionShift.start()}else visualOffsetY=0}
                    SmoothedAnimation {id:positionShift;target:recordRow;property:"visualOffsetY";to:0;duration:SwirlMotion.duration;velocity:-1}
                    onPresentationKeyChanged:{clearPresentation();if(table.selectedItem===recordRow)table.selectedItem=null}
                    onVisibleChanged:if(!visible)clearPresentation()
                    ListView.onPooled:{pooled=true;clearPresentation();if(table.selectedItem===recordRow)table.selectedItem=null}
                    ListView.onReused:{pooled=false;clearPresentation()}
                    Connections {target:SwirlMotion;function onReducedChanged(){if(SwirlMotion.reduced)recordRow.clearPresentation()}}
                    property Item titleElement:null
                    Accessible.role:sectionRow?Accessible.Button:Accessible.ListItem
                    Accessible.selected:!sectionRow&&table.selectedId===String(record.id||record.name)
                    Accessible.name:sectionRow?String(record.sectionName)+"，"+String(record.matchedCount)+"，"+(record.expanded?qsTr("已展开"):qsTr("已收起")):table.columns.map(c=>c.label+"："+String(recordRow.record[c.key]===undefined?"":recordRow.record[c.key])).join("，")
                    Accessible.onPressAction:table.chooseRow(recordRow,true)
                    Rectangle {
                    anchors.fill:parent
                    transform:[Translate {y:recordRow.visualOffsetY},Scale {origin.x:recordRow.width/2;origin.y:recordRow.height/2;xScale:1-0.008*rowFeedback.contact;yScale:1-(1-SwirlMotion.pressScale)*rowFeedback.contact}]
                    radius:table.minimal?Theme.dp(10):0
                    border.width:Theme.increaseContrast && table.sectioned?Theme.dp(1):0
                    border.color:Theme.text
                    color:!recordRow.sectionRow&&table.selectedId===String(recordRow.record.id||recordRow.record.name) ? (table.minimal?(table.rowActions!==null?Theme.navigationSelected:Theme.withAlpha(Theme.accent,0.12)):Theme.selected) :
                          mouse.containsMouse ? (table.minimal?(table.rowActions!==null?Theme.hover:Theme.withAlpha(Theme.accent,0.055)):Theme.hover) : table.minimal?"transparent":(index%2?Theme.field:Theme.surface)
                    Behavior on color { enabled:!SwirlMotion.reduced;ColorAnimation { duration:SwirlMotion.hoverDuration } }
                    Rectangle { anchors.bottom:parent.bottom; width:parent.width; height:Theme.dp(1); color:Theme.border; opacity:table.fillEmptyRows||table.minimal?0:0.6 }
                    Rectangle {anchors.fill:parent;radius:parent.radius;color:Theme.withAlpha(Theme.text,0.05);opacity:rowFeedback.focusAmount;visible:opacity>0;Accessible.ignored:true}
                    Row {
                        anchors.fill:parent
                        visible:!recordRow.sectionRow
                        Repeater {
                            model:recordRow.sectionRow?[]:table.columns
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
                                    readonly property string rowIdentity:String(recordRow.record.id||recordRow.record.name||"")
                                    property string measuredIdentity:""
                                    function settleMeasurement(){numberSlide.stop();displayed=measured;previous=measured;measuredIdentity=rowIdentity}
                                    onRowIdentityChanged:settleMeasurement()
                                    onMeasuredChanged:{
                                        if(rowIdentity===measuredIdentity && measured>=0 && previous>=0 && !recordRow.pooled && recordRow.visible && !SwirlMotion.reduced){numberSlide.to=measured;numberSlide.restart()}
                                        else{numberSlide.stop();displayed=measured}
                                        previous=measured;measuredIdentity=rowIdentity
                                    }
                                    Connections {target:recordRow;function onPooledChanged(){cell.settleMeasurement()}function onVisibleChanged(){if(!recordRow.visible)cell.settleMeasurement()}}
                                    SmoothedAnimation{id:numberSlide;target:cell;property:"displayed";to:cell.measured;duration:SwirlMotion.duration;velocity:-1}
                                    text:measured>=0?String(Math.round(displayed)):raw
                                    textFormat:Text.PlainText
                                    color:Theme.text
                                    textRole:"list"
                                    font.pixelSize:Theme.fontSize(table.textPixelSize)
                                    font.family:Theme.fontFamily
                                    verticalAlignment:Text.AlignVCenter
                                    elide:Text.ElideRight
                                }
                                HoverHandler {id:cellHover}
                                SwirlToolTip {parent:cell.parent;visible:cellHover.hovered&&cell.truncated;text:cell.raw;delay:600}
                            }
                        }
                    }
                    Loader {
                        id:sectionLoader
                        anchors.fill:parent
                        active:recordRow.sectionRow&&table.sectionDelegate!==null
                        sourceComponent:table.sectionDelegate
                        readonly property var record:recordRow.record
                    }
                    MouseArea {
                        id:mouse; anchors.fill:parent; hoverEnabled:true
                        cursorShape:Qt.PointingHandCursor
                        acceptedButtons:Qt.LeftButton|Qt.RightButton
                        onClicked:function(event){
                            list.forceActiveFocus();list.currentIndex=index
                            table.chooseRow(recordRow,event.button===Qt.LeftButton&&(recordRow.sectionRow||table.activateOnSingleClick))
                            if(event.button===Qt.RightButton&&!recordRow.sectionRow){if(actionsLoader.item&&actionsLoader.item.openMenu)actionsLoader.item.openMenu();else contextMenu.showAt()}
                        }
                        onDoubleClicked:if(!recordRow.sectionRow){if(table.activateOnSingleClick)table.rowEdited(recordRow.record,recordRow);else table.chooseRow(recordRow,true)}
                        SwirlContextMenu {
                            id:contextMenu
                            parent:mouse
                            payload:table.columns.map(function(c){
                                return c.label + ": " + String(recordRow.record[c.key] === undefined?"":recordRow.record[c.key])
                            }).join("\n")
                        }
                    }
                    Loader {
                        id:actionsLoader
                        z:2; anchors.right:parent.right; width:table.actionWidth; height:parent.height
                        active:!recordRow.sectionRow&&!recordRow.pooled&&table.rowActions!==null
                        sourceComponent:table.rowActions
                        readonly property var record:recordRow.record
                    }
                    }
                }
            }
        Item {visible:table.gridLines;y:table.headerHeight;width:horizontal.contentWidth;height:horizontal.height-table.headerHeight;z:3
            Row{anchors.fill:parent;Repeater{model:table.columns;Item{width:table.columnWidth(modelData);height:parent.height;Rectangle{visible:index>0;width:Theme.dp(1);height:parent.height;color:Theme.border}}}}
        }
    }
}
