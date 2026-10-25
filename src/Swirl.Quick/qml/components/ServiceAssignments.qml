pragma ComponentBehavior: Bound
import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import SwirlQuick
import "../controls"
import "PolicyHelpers.js" as Policy

ColumnLayout {
    id:assignments
    property var defaultPolicy:({target:{kind:"unconfigured"}})
    property var records:[]
    property var targetOptions:[]
    property bool editable:true
    property string query:""
    readonly property var visibleRecords:records.filter(record=>(record.name+" "+Policy.domainSummary(record.domains)).toLowerCase().indexOf(query.toLowerCase())>=0).slice().sort((a,b)=>a.priority-b.priority)
    signal defaultTargetRequested(Item source)
    signal targetRequested(var record,Item source)
    signal editRequested(var record,Item source)
    signal enabledRequested(string id,bool enabled)
    signal moveRequested(string id,int direction)
    signal deleteRequested(var record,Item source)
    spacing:Theme.dp(12)
    Rectangle {
        Layout.fillWidth:true;Layout.preferredHeight:defaultContent.implicitHeight+Theme.dp(24);radius:Theme.controlRadius;color:Theme.field
        ColumnLayout {id:defaultContent;anchors.fill:parent;anchors.margins:Theme.dp(12);spacing:Theme.dp(6)
            RowLayout {Layout.fillWidth:true
                SwirlText {Layout.fillWidth:true;text:qsTr("默认策略");color:Theme.text;font.pixelSize:Theme.fontSize(15);font.weight:Font.DemiBold}
                SwirlButton {id:defaultTarget;objectName:"defaultPolicyTarget";Layout.preferredWidth:Theme.dp(240);text:Policy.targetName(assignments.defaultPolicy.target,assignments.targetOptions);outlined:true;enabled:assignments.editable;onClicked:assignments.defaultTargetRequested(defaultTarget);Accessible.name:qsTr("默认策略出口：%1").arg(text)}
            }
            SwirlText {Layout.fillWidth:true;text:qsTr("未命中其他规则的流量使用此出口；国内规则仍直连。");color:Theme.muted;font.pixelSize:Theme.fontSize(11);wrapMode:Text.Wrap}
            SwirlText {Layout.fillWidth:true;visible:["node","group"].indexOf((assignments.defaultPolicy.target||{}).kind)>=0&&!Policy.targetAvailable(assignments.defaultPolicy.target,assignments.targetOptions);text:qsTr("出口不可用，请选择其他出口。");color:Theme.orange;font.pixelSize:Theme.fontSize(11);wrapMode:Text.Wrap}
        }
    }
    RowLayout {Layout.fillWidth:true
        SwirlText {text:qsTr("专属策略");color:Theme.text;font.pixelSize:Theme.fontSize(14);font.weight:Font.DemiBold}
        SwirlText {text:qsTr("%1 项").arg(assignments.records.length);color:Theme.muted;font.pixelSize:Theme.fontSize(11)}
        Item {Layout.fillWidth:true}
        SwirlSearchField {objectName:"servicePolicySearch";Layout.preferredWidth:Theme.dp(240);placeholderText:qsTr("搜索策略或域名");onTextChanged:assignments.query=text;Accessible.name:qsTr("搜索服务策略")}
    }
    SwirlAnimatedModel {id:services;source:assignments.visibleRecords;keyRole:"id"}
    ListView {
        id:list;objectName:"servicePolicyList";Layout.fillWidth:true;Layout.fillHeight:true;clip:true;reuseItems:true;pixelAligned:true;model:services
        ScrollBar.vertical:SwirlScrollBar {}
        delegate:Item {
            id:row;required property var entry;readonly property var record:entry;width:Math.floor(ListView.view.width);height:Theme.dp(66)
            ListView.onPooled:moreMenu.close()
            Rectangle {anchors.bottom:parent.bottom;width:parent.width;height:Theme.borderWidth;color:Theme.border}
            RowLayout {anchors.fill:parent;spacing:Theme.dp(8)
                SwirlMotionButton {
                    id:edit;objectName:"servicePolicy-"+row.record.id;Layout.fillWidth:true;Layout.fillHeight:true;padding:Theme.dp(4);enabled:assignments.editable;hoverEnabled:true
                    background:Rectangle {radius:Theme.controlRadius;color:edit.hovered?Theme.hover:"transparent";border.width:edit.activeFocus?Theme.dp(1):0;border.color:Theme.focusBorder}
                    contentItem:ColumnLayout {spacing:Theme.dp(4)
                        SwirlText {Layout.fillWidth:true;text:row.record.name;color:Theme.text;font.pixelSize:Theme.fontSize(13);elide:Text.ElideRight}
                        SwirlText {Layout.fillWidth:true;text:Policy.domainSummary(row.record.domains);color:Theme.muted;font.pixelSize:Theme.fontSize(11);elide:Text.ElideRight}
                    }
                    Accessible.name:qsTr("编辑策略 %1").arg(row.record.name)
                    onClicked:assignments.editRequested(row.record,edit)
                }
                SwirlButton {id:target;objectName:"servicePolicyTarget-"+row.record.id;Layout.preferredWidth:Theme.dp(174);text:Policy.targetName(row.record.target,assignments.targetOptions);quiet:true;enabled:assignments.editable;onClicked:assignments.targetRequested(row.record,target);Accessible.name:qsTr("%1 的出口：%2").arg(row.record.name).arg(text)}
                ReferenceCheckBox {id:enabledControl;objectName:"servicePolicyEnabled-"+row.record.id;checked:Boolean(row.record.enabled);enabled:assignments.editable;Accessible.name:qsTr("启用策略 %1").arg(row.record.name);onToggled:{const requested=checked;checked=Qt.binding(function(){return Boolean(row.record.enabled)});assignments.enabledRequested(row.record.id,requested)}}
                SwirlButton {id:more;objectName:"servicePolicyMore-"+row.record.id;text:qsTr("更多");quiet:true;Layout.preferredWidth:Theme.dp(56);enabled:assignments.editable;onClicked:{SwirlMotion.noteTrigger(more);moreMenu.open()}}
            }
            SwirlContextMenu {id:moreMenu;popupType:Popup.Item;parent:more;x:more.width-width;y:more.height;transformOrigin:Item.TopRight;items:[qsTr("编辑策略"),qsTr("上移优先级"),qsTr("下移优先级"),qsTr("删除策略")];handleItemsInternally:false;onItemTriggered:index=>{if(index===0)assignments.editRequested(row.record,more);else if(index===1)assignments.moveRequested(row.record.id,-1);else if(index===2)assignments.moveRequested(row.record.id,1);else assignments.deleteRequested(row.record,more)}}
        }
        SwirlEmptyState {anchors.centerIn:parent;width:parent.width;visible:list.count===0;headline:assignments.records.length?qsTr("没有匹配的策略"):qsTr("尚无专属策略");detail:assignments.records.length?qsTr("尝试其他名称或域名。"):qsTr("添加需要单独指定出口的网站服务。")}
    }
}
