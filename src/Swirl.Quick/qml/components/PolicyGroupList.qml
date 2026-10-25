pragma ComponentBehavior: Bound
import QtQuick
import QtQuick.Controls.Basic
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
    component PolicyMenuItem: MenuItem {
        id:action
        property string glyph:""
        property bool danger:false
        implicitHeight:Theme.dp(38)
        leftPadding:Theme.dp(10);rightPadding:Theme.dp(12)
        contentItem:RowLayout {
            spacing:Theme.dp(10)
            SwirlIcon {name:action.glyph;size:Theme.dp(16);color:action.danger?Theme.red:Theme.muted;Accessible.ignored:true}
            SwirlText {Layout.fillWidth:true;text:action.text;color:action.danger?Theme.red:Theme.text;font.pixelSize:Theme.fontSize(12)}
        }
        background:Rectangle {radius:Theme.dp(8);color:action.highlighted?Theme.hover:"transparent";border.width:action.visualFocus?Theme.borderWidth:0;border.color:Theme.text}
    }
    RowLayout {Layout.fillWidth:true
        SwirlText {text:qsTr("%1 个策略组").arg(groups.records.length);color:Theme.muted;font.pixelSize:Theme.fontSize(12);Layout.fillWidth:true}
        TextField {
            id:search;objectName:"policyGroupSearch"
            Layout.preferredWidth:Theme.dp(260);Layout.minimumWidth:Theme.dp(140)
            implicitHeight:Theme.dp(34);placeholderText:qsTr("搜索策略组")
            color:Theme.text;placeholderTextColor:Theme.muted;font.family:Theme.fontFamily;font.pixelSize:Theme.fontSize(12)
            leftPadding:Theme.dp(32);rightPadding:Theme.dp(10);selectByMouse:true
            onTextChanged:groups.query=text;Accessible.name:qsTr("搜索策略组")
            background:Rectangle {radius:Theme.dp(9);color:Theme.buttonBase;border.width:search.activeFocus?Theme.borderWidth:0;border.color:Theme.text}
            SwirlIcon {anchors.left:parent.left;anchors.leftMargin:Theme.dp(10);anchors.verticalCenter:parent.verticalCenter;name:"search";size:Theme.dp(14);color:Theme.muted;Accessible.ignored:true}
        }
    }
    SwirlText {Layout.fillWidth:true;text:qsTr("自动组按服务选择出口，实际使用的节点请在连接详情中查看。");color:Theme.muted;font.pixelSize:Theme.fontSize(12);wrapMode:Text.Wrap}
    RowLayout {
        Layout.fillWidth:true;spacing:Theme.dp(8)
        SwirlText {Layout.fillWidth:true;Layout.minimumWidth:0;leftPadding:Theme.dp(8);text:qsTr("策略组与选择方式");color:Theme.muted;font.pixelSize:Theme.fontSize(12)}
        SwirlText {Layout.preferredWidth:Theme.dp(194);leftPadding:Theme.dp(8);text:qsTr("配置的出口");color:Theme.muted;font.pixelSize:Theme.fontSize(12)}
        Item {Layout.preferredWidth:Theme.dp(44)}
    }
    SwirlAnimatedModel {id:groupModel;source:groups.visibleRecords;keyRole:"id"}
    ListView {
        id:list;objectName:"policyGroupList";Layout.fillWidth:true;Layout.fillHeight:true;clip:true;reuseItems:true;pixelAligned:true;model:groupModel
        ScrollBar.vertical:SwirlScrollBar {}
        delegate:Item {
            id:row;required property var entry;readonly property var record:entry;width:Math.floor(ListView.view.width);height:Theme.dp(72)
            ListView.onPooled:moreMenu.close()
            Rectangle {anchors.bottom:parent.bottom;width:parent.width;height:Theme.borderWidth;color:Theme.border}
            RowLayout {anchors.fill:parent;spacing:Theme.dp(8)
                SwirlMotionButton {
                    id:edit;objectName:"policyGroup-"+row.record.id;Layout.fillWidth:true;Layout.minimumWidth:0;Layout.fillHeight:true;padding:Theme.dp(8);hoverEnabled:true;enabled:groups.editable
                    background:Rectangle {radius:Theme.controlRadius;color:edit.down?Theme.pressed:edit.hovered?Theme.navigationSelected:"transparent";border.width:edit.visualFocus?Theme.borderWidth:0;border.color:Theme.text}
                    contentItem:ColumnLayout {spacing:Theme.dp(4)
                        SwirlText {Layout.fillWidth:true;Layout.minimumWidth:0;text:row.record.name;textFormat:Text.PlainText;color:Theme.text;font.pixelSize:Theme.fontSize(14);font.weight:Font.DemiBold;elide:Text.ElideRight}
                        SwirlText {Layout.fillWidth:true;Layout.minimumWidth:0;text:qsTr("%1，%2 个候选").arg(Policy.strategyName(row.record.strategy)).arg((row.record.members||[]).length);color:Theme.muted;font.pixelSize:Theme.fontSize(12);elide:Text.ElideRight}
                    }
                    Accessible.name:qsTr("编辑策略组 %1").arg(row.record.name)
                    onClicked:groups.editRequested(row.record,edit)
                }
                Item {
                    Layout.preferredWidth:Theme.dp(194);Layout.fillHeight:true
                    SubscriptionAction {
                        id:member;objectName:"policyGroupChoose-"+row.record.id
                        anchors.left:parent.left;anchors.right:parent.right;anchors.verticalCenter:parent.verticalCenter
                        implicitWidth:Theme.dp(194);visible:row.record.strategy==="manual"
                        text:Policy.targetName(row.record.selected,groups.targetOptions);enabled:groups.editable
                        Accessible.name:qsTr("%1 的配置出口：%2，选择成员").arg(row.record.name).arg(text);tooltip:Accessible.name
                        contentItem:RowLayout {
                            spacing:Theme.dp(8)
                            SwirlText {Layout.fillWidth:true;Layout.minimumWidth:0;text:member.text;textFormat:Text.PlainText;color:member.enabled?Theme.text:Theme.muted;font.pixelSize:Theme.fontSize(13);elide:Text.ElideRight}
                            SwirlIcon {name:"chevron-right";size:Theme.dp(12);color:Theme.muted;Accessible.ignored:true}
                        }
                        onClicked:groups.memberRequested(row.record,member)
                    }
                    SwirlText {anchors.left:parent.left;anchors.right:parent.right;anchors.leftMargin:Theme.dp(8);anchors.verticalCenter:parent.verticalCenter;visible:row.record.strategy!=="manual";text:qsTr("按服务自动选择");color:Theme.muted;font.pixelSize:Theme.fontSize(12);elide:Text.ElideRight}
                }
                SubscriptionAction {id:more;objectName:"policyGroupMore-"+row.record.id;iconName:"ellipsis";Layout.preferredWidth:Theme.dp(44);Layout.preferredHeight:Theme.dp(44);enabled:groups.editable;Accessible.name:qsTr("%1 的更多操作").arg(row.record.name);tooltip:Accessible.name;tooltipEnabled:!moreMenu.visible;onClicked:moreMenu.open()}
            }
            SwirlContextMenu {
                id:moreMenu;popupType:Popup.Item;parent:more;x:more.width-width;y:more.height;transformOrigin:Item.TopRight
                items:[];implicitWidth:Theme.dp(204)
                PolicyMenuItem {objectName:"swirlContextOption-0";text:qsTr("编辑策略组");glyph:"edit";enabled:groups.editable;onTriggered:groups.editRequested(row.record,more)}
                MenuSeparator {contentItem:Rectangle {implicitHeight:Theme.borderWidth;color:Theme.border}topPadding:Theme.dp(5);bottomPadding:Theme.dp(5)}
                PolicyMenuItem {objectName:"swirlContextOption-1";text:qsTr("删除策略组");glyph:"trash";danger:true;enabled:groups.editable;onTriggered:groups.deleteRequested(row.record,more)}
            }
        }
        SwirlEmptyState {anchors.centerIn:parent;width:parent.width;visible:list.count===0;headline:groups.records.length?qsTr("没有匹配的策略组"):qsTr("尚无策略组");detail:groups.records.length?qsTr("尝试其他名称。"):qsTr("添加手动、自动测速、故障转移或负载均衡组。")}
    }
}
