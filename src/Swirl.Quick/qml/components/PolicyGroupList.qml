pragma ComponentBehavior: Bound
import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import SwirlQuick
import "../controls"
import "PolicyHelpers.js" as Policy

ColumnLayout {
    id:groups
    property var records:[]
    property var targetOptions:[]
    property bool editable:true
    property bool running:false
    property string query:""
    readonly property var visibleRecords:records.filter(record=>String(record.name).toLowerCase().indexOf(query.toLowerCase())>=0)
    signal editRequested(var record,Item source)
    signal memberRequested(var record,Item source)
    signal deleteRequested(var record,Item source)
    spacing:Theme.dp(12)
    RowLayout {Layout.fillWidth:true
        SwirlText {text:qsTr("%1 个策略组").arg(groups.records.length);color:Theme.muted;font.pixelSize:Theme.fontSize(12);Layout.fillWidth:true}
        SwirlSearchField {objectName:"policyGroupSearch";Layout.preferredWidth:Theme.dp(260);placeholderText:qsTr("搜索策略组");onTextChanged:groups.query=text;Accessible.name:qsTr("搜索策略组")}
    }
    SwirlText {Layout.fillWidth:true;text:qsTr("自动组按服务选择出口，实际使用的节点请在连接详情中查看。");color:Theme.muted;font.pixelSize:Theme.fontSize(11);wrapMode:Text.Wrap}
    SwirlAnimatedModel {id:groupModel;source:groups.visibleRecords;keyRole:"id"}
    ListView {
        id:list;objectName:"policyGroupList";Layout.fillWidth:true;Layout.fillHeight:true;clip:true;reuseItems:true;pixelAligned:true;model:groupModel
        ScrollBar.vertical:SwirlScrollBar {}
        delegate:Item {
            id:row;required property var entry;readonly property var record:entry;width:Math.floor(ListView.view.width);height:Theme.dp(78)
            ListView.onPooled:moreMenu.close()
            Rectangle {anchors.bottom:parent.bottom;width:parent.width;height:Theme.borderWidth;color:Theme.border}
            RowLayout {anchors.fill:parent;spacing:Theme.dp(8)
                SwirlMotionButton {
                    id:edit;objectName:"policyGroup-"+row.record.id;Layout.fillWidth:true;Layout.fillHeight:true;padding:Theme.dp(4);hoverEnabled:true;enabled:groups.editable
                    background:Rectangle {radius:Theme.controlRadius;color:edit.hovered?Theme.hover:"transparent";border.width:edit.activeFocus?Theme.dp(1):0;border.color:Theme.focusBorder}
                    contentItem:ColumnLayout {spacing:Theme.dp(3)
                        SwirlText {Layout.fillWidth:true;text:row.record.name;color:Theme.text;font.pixelSize:Theme.fontSize(13);elide:Text.ElideRight}
                        SwirlText {Layout.fillWidth:true;text:qsTr("%1，%2 个候选").arg(Policy.strategyName(row.record.strategy)).arg((row.record.members||[]).length);color:Theme.muted;font.pixelSize:Theme.fontSize(11);elide:Text.ElideRight}
                        SwirlText {Layout.fillWidth:true;visible:row.record.strategy==="manual";text:qsTr("已配置：%1").arg(Policy.targetName(row.record.selected,groups.targetOptions));color:Theme.muted;font.pixelSize:Theme.fontSize(11);elide:Text.ElideRight}
                    }
                    Accessible.name:qsTr("编辑策略组 %1").arg(row.record.name)
                    onClicked:groups.editRequested(row.record,edit)
                }
                SwirlButton {id:member;objectName:"policyGroupChoose-"+row.record.id;visible:row.record.strategy==="manual";text:qsTr("选择成员");quiet:true;enabled:groups.editable;onClicked:groups.memberRequested(row.record,member)}
                SwirlButton {id:more;objectName:"policyGroupMore-"+row.record.id;text:qsTr("更多");quiet:true;Layout.preferredWidth:Theme.dp(56);enabled:groups.editable;onClicked:{SwirlMotion.noteTrigger(more);moreMenu.open()}}
            }
            SwirlContextMenu {id:moreMenu;popupType:Popup.Item;parent:more;x:more.width-width;y:more.height;transformOrigin:Item.TopRight;items:[qsTr("编辑策略组"),qsTr("删除策略组")];handleItemsInternally:false;onItemTriggered:index=>{if(index===0)groups.editRequested(row.record,more);else groups.deleteRequested(row.record,more)}}
        }
        SwirlEmptyState {anchors.centerIn:parent;width:parent.width;visible:list.count===0;headline:groups.records.length?qsTr("没有匹配的策略组"):qsTr("尚无策略组");detail:groups.records.length?qsTr("尝试其他名称。"):qsTr("添加手动、自动测速、故障转移或负载均衡组。")}
    }
}
