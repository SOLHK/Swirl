pragma ComponentBehavior: Bound
import QtQuick
import QtQuick.Controls.Basic
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

    component TargetAction: SubscriptionAction {
        id:control
        implicitWidth:Theme.dp(174)
        tooltip:text
        contentItem:RowLayout {
            spacing:Theme.dp(8)
            SwirlText {Layout.fillWidth:true;Layout.minimumWidth:0;text:control.text;textFormat:Text.PlainText;color:control.enabled?Theme.text:Theme.muted;font.pixelSize:Theme.fontSize(13);elide:Text.ElideRight}
            SwirlIcon {name:"chevron-right";size:Theme.dp(12);color:Theme.muted;Accessible.ignored:true}
        }
    }
    component PolicyMenuItem: MenuItem {
        id:action
        property string glyph:""
        property real glyphRotation:0
        property bool danger:false
        implicitHeight:Theme.dp(38)
        leftPadding:Theme.dp(10);rightPadding:Theme.dp(12)
        contentItem:RowLayout {
            spacing:Theme.dp(10)
            SwirlIcon {name:action.glyph;rotation:action.glyphRotation;size:Theme.dp(16);color:action.danger?Theme.red:Theme.muted;Accessible.ignored:true}
            SwirlText {Layout.fillWidth:true;text:action.text;color:action.danger?Theme.red:Theme.text;font.pixelSize:Theme.fontSize(12)}
        }
        background:Rectangle {radius:Theme.dp(8);color:action.highlighted?Theme.hover:"transparent";border.width:action.visualFocus?Theme.borderWidth:0;border.color:Theme.text}
    }

    ColumnLayout {
        Layout.fillWidth:true;spacing:Theme.dp(6)
        RowLayout {
            Layout.fillWidth:true;spacing:Theme.dp(12)
            SwirlText {Layout.fillWidth:true;Layout.minimumWidth:0;text:qsTr("默认策略");color:Theme.text;font.pixelSize:Theme.fontSize(14);font.weight:Font.DemiBold}
            TargetAction {id:defaultTarget;objectName:"defaultPolicyTarget";Layout.preferredWidth:Theme.dp(214);text:Policy.targetName(assignments.defaultPolicy.target,assignments.targetOptions);enabled:assignments.editable;onClicked:assignments.defaultTargetRequested(defaultTarget);Accessible.name:qsTr("默认策略出口：%1").arg(text)}
        }
        SwirlText {Layout.fillWidth:true;text:qsTr("未命中其他规则的流量使用此出口；国内规则仍直连。");color:Theme.muted;font.pixelSize:Theme.fontSize(12);wrapMode:Text.Wrap}
        SwirlText {Layout.fillWidth:true;visible:["node","group"].indexOf((assignments.defaultPolicy.target||{}).kind)>=0&&!Policy.targetAvailable(assignments.defaultPolicy.target,assignments.targetOptions);text:qsTr("出口不可用，请选择其他出口。");color:Theme.orange;font.pixelSize:Theme.fontSize(12);wrapMode:Text.Wrap}
    }
    Rectangle {Layout.fillWidth:true;implicitHeight:Theme.borderWidth;color:Theme.border}
    RowLayout {Layout.fillWidth:true;spacing:Theme.dp(10)
        SwirlText {text:qsTr("专属策略");color:Theme.text;font.pixelSize:Theme.fontSize(14);font.weight:Font.DemiBold}
        SwirlText {text:qsTr("%1 项").arg(assignments.records.length);color:Theme.muted;font.pixelSize:Theme.fontSize(12)}
        Item {Layout.fillWidth:true}
        TextField {
            id:search;objectName:"servicePolicySearch"
            Layout.preferredWidth:Theme.dp(240);Layout.minimumWidth:Theme.dp(140)
            implicitHeight:Theme.dp(34);placeholderText:qsTr("搜索策略或域名")
            color:Theme.text;placeholderTextColor:Theme.muted;font.family:Theme.fontFamily;font.pixelSize:Theme.fontSize(12)
            leftPadding:Theme.dp(32);rightPadding:Theme.dp(10);selectByMouse:true
            onTextChanged:assignments.query=text;Accessible.name:qsTr("搜索服务策略")
            background:Rectangle {radius:Theme.dp(9);color:Theme.buttonBase;border.width:search.activeFocus?Theme.borderWidth:0;border.color:Theme.text}
            SwirlIcon {anchors.left:parent.left;anchors.leftMargin:Theme.dp(10);anchors.verticalCenter:parent.verticalCenter;name:"search";size:Theme.dp(14);color:Theme.muted;Accessible.ignored:true}
        }
    }
    RowLayout {
        Layout.fillWidth:true;spacing:Theme.dp(8)
        SwirlText {Layout.fillWidth:true;Layout.minimumWidth:0;leftPadding:Theme.dp(8);text:qsTr("服务与匹配域名");color:Theme.muted;font.pixelSize:Theme.fontSize(12)}
        SwirlText {Layout.preferredWidth:Theme.dp(174);leftPadding:Theme.dp(8);text:qsTr("配置的出口");color:Theme.muted;font.pixelSize:Theme.fontSize(12)}
        SwirlText {Layout.preferredWidth:Theme.dp(36);text:qsTr("启用");color:Theme.muted;font.pixelSize:Theme.fontSize(12);horizontalAlignment:Text.AlignHCenter}
        Item {Layout.preferredWidth:Theme.dp(44)}
    }
    SwirlAnimatedModel {id:services;source:assignments.visibleRecords;keyRole:"id"}
    ListView {
        id:list;objectName:"servicePolicyList";Layout.fillWidth:true;Layout.fillHeight:true;clip:true;reuseItems:true;pixelAligned:true;model:services
        ScrollBar.vertical:SwirlScrollBar {}
        delegate:Item {
            id:row;required property var entry;readonly property var record:entry;width:Math.floor(ListView.view.width);height:Theme.dp(72)
            ListView.onPooled:moreMenu.close()
            Rectangle {anchors.bottom:parent.bottom;width:parent.width;height:Theme.borderWidth;color:Theme.border}
            RowLayout {anchors.fill:parent;spacing:Theme.dp(8)
                SwirlMotionButton {
                    id:edit;objectName:"servicePolicy-"+row.record.id;Layout.fillWidth:true;Layout.minimumWidth:0;Layout.fillHeight:true;padding:Theme.dp(8);enabled:assignments.editable;hoverEnabled:true
                    background:Rectangle {radius:Theme.controlRadius;color:edit.down?Theme.pressed:edit.hovered?Theme.navigationSelected:"transparent";border.width:edit.visualFocus?Theme.borderWidth:0;border.color:Theme.text}
                    contentItem:ColumnLayout {spacing:Theme.dp(4)
                        SwirlText {Layout.fillWidth:true;Layout.minimumWidth:0;text:row.record.name;textFormat:Text.PlainText;color:Theme.text;font.pixelSize:Theme.fontSize(14);font.weight:Font.DemiBold;elide:Text.ElideRight}
                        SwirlText {Layout.fillWidth:true;Layout.minimumWidth:0;text:Policy.domainSummary(row.record.domains);textFormat:Text.PlainText;color:Theme.muted;font.pixelSize:Theme.fontSize(12);elide:Text.ElideRight}
                    }
                    Accessible.name:qsTr("编辑策略 %1").arg(row.record.name)
                    onClicked:assignments.editRequested(row.record,edit)
                }
                TargetAction {id:target;objectName:"servicePolicyTarget-"+row.record.id;Layout.preferredWidth:Theme.dp(174);text:Policy.targetName(row.record.target,assignments.targetOptions);enabled:assignments.editable;onClicked:assignments.targetRequested(row.record,target);Accessible.name:qsTr("%1 的出口：%2").arg(row.record.name).arg(text)}
                CheckBox {
                    id:enabledControl;objectName:"servicePolicyEnabled-"+row.record.id
                    Layout.preferredWidth:Theme.dp(36);Layout.preferredHeight:Theme.dp(44);padding:0
                    checked:Boolean(row.record.enabled);enabled:assignments.editable
                    Accessible.name:qsTr("启用策略 %1").arg(row.record.name)
                    onToggled:{const requested=checked;checked=Qt.binding(function(){return Boolean(row.record.enabled)});assignments.enabledRequested(row.record.id,requested)}
                    background:Rectangle {anchors.centerIn:parent;width:Theme.dp(30);height:Theme.dp(30);radius:Theme.dp(8);color:"transparent";border.width:enabledControl.visualFocus?Theme.borderWidth:0;border.color:Theme.text}
                    indicator:Rectangle {
                        anchors.centerIn:parent;width:Theme.dp(16);height:width;radius:Theme.dp(4)
                        color:enabledControl.checked?Theme.text:Theme.buttonBase
                        border.color:Theme.controlBorder;border.width:enabledControl.checked?0:Theme.borderWidth
                        opacity:enabledControl.enabled?1:0.45
                        Behavior on color {enabled:!SwirlMotion.reduced;ColorAnimation {duration:SwirlMotion.statusDuration}}
                        SwirlIcon {anchors.centerIn:parent;name:"checkmark";size:Theme.dp(12);color:Theme.surface;visible:enabledControl.checked;Accessible.ignored:true}
                    }
                    contentItem:Item {}
                }
                SubscriptionAction {id:more;objectName:"servicePolicyMore-"+row.record.id;iconName:"ellipsis";Layout.preferredWidth:Theme.dp(44);Layout.preferredHeight:Theme.dp(44);enabled:assignments.editable;Accessible.name:qsTr("%1 的更多操作").arg(row.record.name);tooltip:Accessible.name;tooltipEnabled:!moreMenu.visible;onClicked:moreMenu.open()}
            }
            SwirlContextMenu {
                id:moreMenu;popupType:Popup.Item;parent:more;x:more.width-width;y:more.height;transformOrigin:Item.TopRight
                items:[];implicitWidth:Theme.dp(204)
                PolicyMenuItem {objectName:"swirlContextOption-0";text:qsTr("编辑策略");glyph:"edit";enabled:assignments.editable;onTriggered:assignments.editRequested(row.record,more)}
                PolicyMenuItem {objectName:"swirlContextOption-1";text:qsTr("上移优先级");glyph:"chevron-right";glyphRotation:-90;enabled:assignments.editable;onTriggered:assignments.moveRequested(row.record.id,-1)}
                PolicyMenuItem {objectName:"swirlContextOption-2";text:qsTr("下移优先级");glyph:"chevron-right";glyphRotation:90;enabled:assignments.editable;onTriggered:assignments.moveRequested(row.record.id,1)}
                MenuSeparator {contentItem:Rectangle {implicitHeight:Theme.borderWidth;color:Theme.border}topPadding:Theme.dp(5);bottomPadding:Theme.dp(5)}
                PolicyMenuItem {objectName:"swirlContextOption-3";text:qsTr("删除策略");glyph:"trash";danger:true;enabled:assignments.editable;onTriggered:assignments.deleteRequested(row.record,more)}
            }
        }
        SwirlEmptyState {anchors.centerIn:parent;width:parent.width;visible:list.count===0;headline:assignments.records.length?qsTr("没有匹配的策略"):qsTr("尚无专属策略");detail:assignments.records.length?qsTr("尝试其他名称或域名。"):qsTr("添加需要单独指定出口的网站服务。")}
    }
}
