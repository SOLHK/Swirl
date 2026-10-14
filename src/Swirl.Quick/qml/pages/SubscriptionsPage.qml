import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import SwirlQuick
import "../components"
import "../controls"
Item {
 id:page
 property string expandedId:""
 property string editingId:""
 function edit(record){editingId=record?record.id:"";displayName.text=record?record.name:"";urlField.text="";interval.currentIndex=record?Math.max(0,[360,720,1440,10080].indexOf(record.intervalMinutes)):0;autoEnabled.checked=record?record.enabled:true;addDialog.open()}
 readonly property var providers:engineController.imports.providers
 readonly property var listed:providers.filter(function(r){return r.name.toLowerCase().indexOf(search.text.toLowerCase())>=0})
 ColumnLayout { anchors.fill:parent;anchors.margins:Theme.dp(24);spacing:Theme.gap
  RowLayout { Layout.fillWidth:true
   Text { text:"订阅管理";color:Theme.text;font.pixelSize:Theme.fontSize(30);font.weight:Font.DemiBold;Layout.fillWidth:true }
   SwirlButton { text:"更新全部";enabled:!engineController.imports.busy;onClicked:engineController.imports.refreshAll() }
   SwirlButton { objectName:"addSubscription";text:"添加订阅";primary:true;enabled:!engineController.imports.busy;onClicked:page.edit(null) }
  }
  Text { text:engineController.imports.message||"地址由 DPAPI 加密；更新失败保留原节点";color:Theme.muted;Layout.fillWidth:true;wrapMode:Text.Wrap;font.pixelSize:Theme.fontSize(12) }
  SwirlSearchField { id:search;Layout.fillWidth:true;placeholderText:"搜索订阅名称" }
  ScrollView { id:scroll;objectName:"subscriptionsSinglePanel";Layout.fillWidth:true;Layout.fillHeight:true;clip:true;ScrollBar.horizontal.policy:ScrollBar.AlwaysOff;ScrollBar.vertical:SwirlScrollBar {}
   ColumnLayout { width:scroll.availableWidth;spacing:Theme.gap
    Repeater { model:page.listed
     SwirlGlassPanel { id:provider;required property var modelData;readonly property var record:modelData
      Layout.fillWidth:true;Layout.preferredHeight:providerContent.implicitHeight+2*Theme.cardPadding
      ColumnLayout { id:providerContent;anchors.fill:parent;anchors.margins:Theme.cardPadding;spacing:Theme.dp(10)
       RowLayout { Layout.fillWidth:true
        Text { text:provider.record.name;textFormat:Text.PlainText;color:Theme.text;font.pixelSize:Theme.fontSize(18);font.weight:Font.DemiBold;Layout.fillWidth:true }
        SwirlStatusBadge { label:provider.record.status;tone:provider.record.status==="已保存真实节点"?"success":provider.record.status==="更新失败"?"warning":"neutral" }
        Text { text:provider.record.nodes+" 个节点";color:Theme.muted }
       }
       RowLayout { Layout.fillWidth:true
        Text { text:"最近更新："+provider.record.update;color:Theme.muted;font.pixelSize:Theme.fontSize(12);Layout.fillWidth:true }
        Text { text:"自动更新";color:Theme.text;font.pixelSize:Theme.fontSize(12) }
        SwirlToggle { checked:provider.record.enabled;enabled:!engineController.imports.busy;onToggled:engineController.imports.saveSubscription(provider.record.id,provider.record.name,"",provider.record.intervalMinutes,checked) }
       }
       Text { text:provider.record.enabled?"每 "+provider.record.intervalMinutes+" 分钟 · 下次预计 "+provider.record.nextUpdate:"自动更新已关闭";color:Theme.muted;font.pixelSize:Theme.fontSize(12);Layout.fillWidth:true;wrapMode:Text.Wrap }
       Text { text:provider.record.error;visible:text.length>0;color:Theme.orange;Layout.fillWidth:true;wrapMode:Text.Wrap;font.pixelSize:Theme.fontSize(12) }
       Text { visible:page.expandedId===provider.record.id;text:"订阅地址已加密隐藏。HTTPS 重定向最多 5 次，禁止降级；仅导入节点，不执行远程全局配置。";color:Theme.muted;Layout.fillWidth:true;wrapMode:Text.Wrap;font.pixelSize:Theme.fontSize(12) }
       RowLayout { Layout.fillWidth:true
        SwirlButton { text:page.expandedId===provider.record.id?"收起详情":"展开详情";onClicked:page.expandedId=page.expandedId===provider.record.id?"":provider.record.id }
        Item { Layout.fillWidth:true }
        SwirlButton { text:"刷新";enabled:!engineController.imports.busy;onClicked:engineController.imports.refreshSubscription(provider.record.id) }
        SwirlButton { text:"编辑";enabled:!engineController.imports.busy;onClicked:page.edit(provider.record) }
        SwirlButton { text:"删除";danger:true;enabled:!engineController.imports.busy;onClicked:{deleteDialog.recordId=provider.record.id;deleteDialog.open()} }
       }
      }
     }
    }
    Text { visible:page.listed.length===0;text:"暂无订阅。添加订阅后，可在原卡片内查看更新状态。";color:Theme.muted;Layout.fillWidth:true;wrapMode:Text.Wrap }
   }
  }
 }
    SwirlDialog {
        id:deleteDialog;title:"删除订阅？";property string recordId:"";guardChanges:false
        ColumnLayout {width:parent.width
            Text {text:"删除此订阅及其导入的节点。";color:Theme.text}
            RowLayout {Layout.alignment:Qt.AlignRight
                SwirlButton {text:"取消";onClicked:deleteDialog.close()}
                SwirlButton {text:"删除";danger:true;onClicked:{engineController.imports.removeSubscription(deleteDialog.recordId);deleteDialog.close()}}
            }
        }
    }
    SwirlDialog {
        id:addDialog;objectName:"subscriptionDialog"; title:"订阅来源";onClosed:urlField.text=""
        ColumnLayout {
            width:parent.width; spacing:Theme.dp(12)
            ScrollView {id:subscriptionForm;Layout.fillWidth:true;Layout.preferredHeight:Math.min(Theme.dp(330),page.height*0.6);clip:true;ScrollBar.horizontal.policy:ScrollBar.AlwaysOff
        ScrollBar.vertical:SwirlScrollBar {}
                ColumnLayout {width:subscriptionForm.availableWidth;spacing:Theme.dp(12)
            Text { text:AppState.zh("Display name"); color:Theme.text }
            SwirlTextField { id:displayName;objectName:"subscriptionName"; Layout.fillWidth:true; placeholderText:AppState.zh("My subscription") }
            Text { text:"HTTPS 订阅地址"; color:Theme.text }
            SwirlTextField { id:urlField;objectName:"subscriptionUrl"; Layout.fillWidth:true;echoMode:TextInput.Password; placeholderText:page.editingId.length?"留空保留已加密地址":"https://…";Accessible.name:"订阅地址" }
            Text { text:"应用运行时按设定间隔更新；只导入节点，不执行远程全局配置。"; color:Theme.muted; font.pixelSize:Theme.fontSize(11); Layout.fillWidth:true; wrapMode:Text.WordWrap }
            SwirlComboBox {id:interval;Layout.fillWidth:true;model:["每 6 小时","每 12 小时","每天","每周"];Accessible.name:"自动更新间隔"}
            RowLayout {Layout.fillWidth:true;Text {text:"自动更新";color:Theme.text;Layout.fillWidth:true}SwirlToggle {id:autoEnabled;checked:true}}
            Text {text:engineController.imports.message;color:Theme.orange;Layout.fillWidth:true;wrapMode:Text.Wrap;font.pixelSize:Theme.fontSize(11)}
                }
            }
            RowLayout {
                Layout.alignment:Qt.AlignRight
                SwirlButton { text:AppState.zh("Cancel"); onClicked:addDialog.close() }
                SwirlButton { enabled:!engineController.imports.busy && displayName.text.trim().length>0 && (page.editingId.length>0 || urlField.text.trim().length>0);
                    objectName:"saveSubscription";text:"保存并更新"; primary:true
                    onClicked:{if(engineController.imports.saveSubscription(page.editingId,displayName.text,urlField.text.trim(),[360,720,1440,10080][interval.currentIndex],autoEnabled.checked)){var id=page.editingId||engineController.imports.providers[engineController.imports.providers.length-1].id;addDialog.close();engineController.imports.refreshSubscription(id)}}
                }
            }
        }
    }
}
