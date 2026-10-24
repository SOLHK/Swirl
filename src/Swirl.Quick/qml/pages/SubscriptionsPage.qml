import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import SwirlQuick
import "../components"
import "../controls"
Item {
 id:page
    readonly property Item motionTitle:routeTitle

 property string expandedId:""
 property string editingId:""
  function edit(record){editingId=record?record.id:"";displayName.text=record?record.name:"";urlField.text="";formatPreference.currentIndex=record?Math.max(0,["auto","clash","loon","shadowrocket","surge","quantumult-x","sing-box"].indexOf(record.formatHint)):0;importScope.currentIndex=record&&record.importScope==="nodes-only"?1:0;interval.currentIndex=record?Math.max(0,[360,720,1440,10080].indexOf(record.intervalMinutes)):0;autoEnabled.checked=record?record.enabled:true;addDialog.open();Qt.callLater(function(){subscriptionForm.contentItem.contentY=0;displayName.forceActiveFocus()})}
 function revealField(field){
  if(!addDialog.visible)return
  const flick=subscriptionForm.contentItem,top=field.mapToItem(subscriptionBody,0,0).y,bottom=top+field.height
  if(top<flick.contentY)flick.contentY=top
  else if(bottom>flick.contentY+flick.height)flick.contentY=Math.max(0,bottom-flick.height)
 }
 readonly property var providers:engineController.imports.providers
 SwirlAnimatedModel{id:subscriptionModel;source:page.listed;keyRole:"id"}
 readonly property string searchQuery:search.text.trim().toLowerCase()
 readonly property var listed:providers.filter(function(r){return r.name.toLowerCase().indexOf(page.searchQuery)>=0})
 ColumnLayout { anchors.fill:parent;anchors.margins:Theme.dp(24);spacing:Theme.gap
  RowLayout { Layout.fillWidth:true
   SwirlText {textRole:"pageTitle";id:routeTitle; text:"订阅管理";color:Theme.text;font.pixelSize:Theme.fontSize(26);font.weight:Font.DemiBold;Layout.fillWidth:true }
   SwirlButton { text:"更新全部";enabled:!engineController.imports.busy;onClicked:engineController.imports.refreshAll() }
   SwirlButton { objectName:"addSubscription";text:"添加订阅";primary:true;enabled:!engineController.imports.busy;onClicked:page.edit(null) }
  }
  SwirlText { text:engineController.imports.message||"管理订阅、节点更新和自动更新周期";color:Theme.muted;Layout.fillWidth:true;wrapMode:Text.Wrap;font.pixelSize:Theme.fontSize(12) }
  SwirlSearchField { id:search;Layout.fillWidth:true;placeholderText:"搜索订阅名称" }
  RowLayout {
   visible:engineController.imports.legacyNodeCount>0;Layout.fillWidth:true;spacing:Theme.dp(12)
   SwirlText {text:qsTr("有 %1 个历史节点无法确认订阅归属，已保留。可在节点来源中单独查看。").arg(engineController.imports.legacyNodeCount);Layout.fillWidth:true;wrapMode:Text.Wrap;color:Theme.muted;font.pixelSize:Theme.fontSize(12)}
   SwirlButton {objectName:"reviewLegacyNodes";text:qsTr("查看历史节点");onClicked:{AppState.navigate("proxies");Qt.callLater(function(){AppState.notice(qsTr("在节点来源中选择「历史未归属」查看；确认后可返回此处清理。"))})}}
   SwirlButton {objectName:"cleanLegacyNodes";text:qsTr("清理");danger:true;enabled:!engineController.imports.busy;onClicked:legacyDialog.open()}
  }
  ColumnLayout {
   objectName:"subscriptionsEmptyState";visible:page.listed.length===0;Layout.fillWidth:true;spacing:Theme.dp(8)
   SwirlText {text:page.providers.length?qsTr("没有匹配的订阅"):qsTr("暂无订阅");color:Theme.text;font.pixelSize:Theme.fontSize(16);font.weight:Font.DemiBold}
   SwirlText {text:page.providers.length?qsTr("调整搜索内容以查看其他订阅。"):qsTr("添加 HTTPS 订阅后，可查看节点来源、上次成功更新时间与更新结果。");color:Theme.muted;Layout.fillWidth:true;wrapMode:Text.Wrap}
  }
  Item {visible:page.listed.length===0;Layout.fillWidth:true;Layout.fillHeight:true}
  ScrollView { id:scroll;objectName:"subscriptionsSinglePanel";visible:page.listed.length>0;Layout.fillWidth:true;Layout.fillHeight:true;Layout.minimumHeight:0;clip:true;ScrollBar.horizontal.policy:ScrollBar.AlwaysOff;ScrollBar.vertical:SwirlScrollBar {}
   ListView { pixelAligned: true; id:subscriptionList;objectName:"subscriptionList";model:subscriptionModel;spacing:Theme.gap;clip:true
    add:Transition{enabled:!SwirlMotion.reduced;NumberAnimation{property:"opacity";from:0;to:1;duration:SwirlMotion.duration}}
    remove:Transition{enabled:!SwirlMotion.reduced;NumberAnimation{property:"opacity";to:0;duration:SwirlMotion.exitDuration}}
    displaced:Transition{enabled:!SwirlMotion.reduced;NumberAnimation{property:"y";duration:SwirlMotion.expandDuration;easing.type:SwirlMotion.standardEasing}}
    delegate:SwirlHeroCard {
      id:provider;objectName:'subscriptionCard-'+record.id
      required property var entry;readonly property var record:entry
      expanded:page.expandedId===record.id
      width:Math.floor(subscriptionList.width)
      collapsedHeight:header.implicitHeight+actions.implicitHeight+2*Theme.cardPadding+Theme.dp(14)
      expandedHeight:collapsedHeight+detailBody.implicitHeight+Theme.dp(18)
      ColumnLayout {
        id:header;x:Theme.cardPadding;y:Theme.cardPadding;width:parent.width-2*Theme.cardPadding;spacing:Theme.dp(9)
        RowLayout {Layout.fillWidth:true
          SwirlText {objectName:'subscriptionTitle-'+provider.record.id;text:provider.record.name;textFormat:Text.PlainText;color:Theme.text;font.pixelSize:Theme.fontSize(18+4*provider.reveal);font.weight:Font.DemiBold;Layout.fillWidth:true;elide:Text.ElideRight}
          SwirlStatusBadge {objectName:'subscriptionStatus-'+provider.record.id;busy:provider.record.status==='正在更新';label:provider.record.status==='已保存真实节点'?'已更新':provider.record.status;tone:provider.record.status==='已保存真实节点'?'success':provider.record.status==='更新失败'?'warning':'neutral'}
          SwirlText {text:provider.record.nodes+' 个节点';color:Theme.muted}
        }
        SwirlText {text:qsTr('上次成功更新：%1').arg(provider.record.update);color:Theme.muted;font.pixelSize:Theme.fontSize(12);Layout.fillWidth:true;wrapMode:Text.Wrap}
        SwirlText {text:provider.record.error;textFormat:Text.PlainText;visible:text.length>0;color:Theme.orange;Layout.fillWidth:true;wrapMode:Text.WrapAnywhere;font.pixelSize:Theme.fontSize(12)}
        SwirlButton {
          text:'仅导入节点并重试';visible:provider.record.importScope==='full-profile'&&provider.record.error.indexOf('尚未映射')>=0
          enabled:!engineController.imports.busy
          onClicked:{if(engineController.imports.saveSubscription(provider.record.id,provider.record.name,'',provider.record.intervalMinutes,provider.record.enabled,provider.record.formatHint,'nodes-only'))engineController.imports.refreshSubscription(provider.record.id)}
        }
      }
      Item {
        x:Theme.cardPadding;y:header.y+header.implicitHeight+Theme.dp(14);width:parent.width-2*Theme.cardPadding
        height:detailBody.implicitHeight*provider.reveal;clip:true
        enabled:provider.expanded
        ColumnLayout {id:detailBody;width:parent.width;spacing:Theme.dp(12)
          Rectangle {Layout.fillWidth:true;Layout.preferredHeight:Theme.dp(1);color:Theme.border}
          RowLayout {Layout.fillWidth:true
            ColumnLayout {Layout.fillWidth:true;spacing:Theme.dp(5)
              SwirlText {text:'自动更新';color:Theme.text;font.pixelSize:Theme.fontSize(14);font.weight:Font.DemiBold}
              SwirlText {text:provider.record.enabled?'每 '+provider.record.intervalMinutes+' 分钟':'自动更新已关闭';color:Theme.muted;font.pixelSize:Theme.fontSize(12)}
            }
            SwirlToggle {checked:provider.record.enabled;enabled:!engineController.imports.busy;onToggled:engineController.imports.saveSubscription(provider.record.id,provider.record.name,'',provider.record.intervalMinutes,checked)}
          }
          SwirlText {text:provider.record.enabled?'下次预计：'+provider.record.nextUpdate:'可在编辑中调整更新周期';color:Theme.muted;font.pixelSize:Theme.fontSize(12);Layout.fillWidth:true;wrapMode:Text.Wrap}
          SwirlText {text:provider.record.importScope==='nodes-only'?'导入范围：仅节点':'导入范围：完整配置（严格校验）';color:Theme.muted;font.pixelSize:Theme.fontSize(12);Layout.fillWidth:true}
          SwirlText {text:'订阅地址已加密隐藏。更新失败时保留现有节点。';color:Theme.muted;font.pixelSize:Theme.fontSize(12);Layout.fillWidth:true;wrapMode:Text.Wrap}
        }
      }
      RowLayout {
        id:actions;x:Theme.cardPadding;y:provider.height-Theme.cardPadding-implicitHeight;width:parent.width-2*Theme.cardPadding;spacing:Theme.dp(8)
        SwirlButton {objectName:'expandSubscription-'+provider.record.id;text:provider.expanded?'收起详情':'展开详情';onClicked:page.expandedId=provider.expanded?'':provider.record.id;Accessible.name:text+' '+provider.record.name}
        Item {Layout.fillWidth:true}
        SwirlButton {objectName:'refreshSubscription-'+provider.record.id;text:provider.record.canCancel?(provider.record.queued?'取消排队':'取消更新'):'刷新';enabled:provider.record.canCancel||(!engineController.imports.busy&&!engineController.imports.hasPreview);onClicked:{if(provider.record.canCancel)engineController.imports.cancelRefresh(provider.record.id);else engineController.imports.refreshSubscription(provider.record.id)}}
        SwirlButton {objectName:'editSubscription-'+provider.record.id;text:'编辑';enabled:!engineController.imports.busy;onClicked:page.edit(provider.record)}
        SwirlButton {objectName:'deleteSubscription-'+provider.record.id;text:'删除';danger:true;enabled:!engineController.imports.busy;onClicked:{deleteDialog.recordId=provider.record.id;deleteDialog.open()}}
      }
    }
   }
  }
 }
    SwirlDialog {
        ownerItem:page
        id:deleteDialog;title:"删除订阅？";property string recordId:"";guardChanges:false
        ColumnLayout {width:parent.width
            SwirlText {text:qsTr("删除此订阅及其所属节点。手动节点和无法确认归属的历史节点会保留；正在使用的所属节点将断开。");color:Theme.text;wrapMode:Text.Wrap;Layout.fillWidth:true}
            RowLayout {Layout.alignment:Qt.AlignRight
                SwirlButton {text:"取消";onClicked:deleteDialog.close()}
                SwirlButton {objectName:"confirmSubscriptionDelete";text:"删除";danger:true;onClicked:{engineController.imports.removeSubscription(deleteDialog.recordId);deleteDialog.close()}}
            }
        }
    }
    SwirlDialog {
        ownerItem:page
        id:legacyDialog;objectName:"legacyNodesDialog";title:qsTr("清理历史未归属节点？");guardChanges:false
        ColumnLayout {width:parent.width;spacing:Theme.dp(12)
            SwirlText {text:qsTr("仅清理已标记为历史未归属的 %1 个节点。已确认的手动节点与现有订阅节点会保留。建议先在节点来源中查看；此操作不能撤销。").arg(engineController.imports.legacyNodeCount);Layout.fillWidth:true;wrapMode:Text.Wrap;color:Theme.text}
            RowLayout {Layout.alignment:Qt.AlignRight
                SwirlButton {text:qsTr("取消");onClicked:legacyDialog.close()}
                SwirlButton {objectName:"confirmLegacyNodesDelete";text:qsTr("确认清理");danger:true;onClicked:{if(engineController.imports.cleanLegacyNodes())legacyDialog.close()}}
            }
        }
    }
    SwirlDialog {
        ownerItem:page
        id:addDialog;objectName:"subscriptionDialog"; title:"订阅来源";onClosed:urlField.text=""
        height:Math.min(implicitHeight,parent?parent.height-Theme.dp(30):implicitHeight)
        contentItem:ColumnLayout {
            spacing:Theme.dp(12)
            ScrollView {id:subscriptionForm;objectName:"subscriptionFormViewport";Layout.fillWidth:true;Layout.fillHeight:true;Layout.minimumHeight:0;Layout.preferredHeight:Theme.dp(330);clip:true;ScrollBar.horizontal.policy:ScrollBar.AlwaysOff
        contentWidth:availableWidth;contentHeight:subscriptionBody.implicitHeight
        ScrollBar.vertical:SwirlScrollBar {}
                ColumnLayout {id:subscriptionBody;objectName:"subscriptionFormBody";width:subscriptionForm.availableWidth;spacing:Theme.dp(12)
            SwirlText { text:AppState.zh("Display name"); color:Theme.text }
            SwirlTextField { id:displayName;objectName:"subscriptionName"; Layout.fillWidth:true; placeholderText:AppState.zh("My subscription");onActiveFocusChanged:if(activeFocus)page.revealField(displayName) }
            SwirlText { text:"HTTPS 订阅地址"; color:Theme.text }
            SwirlTextField { id:urlField;objectName:"subscriptionUrl"; Layout.fillWidth:true;echoMode:TextInput.Password; placeholderText:page.editingId.length?"留空保留已加密地址":"https://…";Accessible.name:"订阅地址";onActiveFocusChanged:if(activeFocus)page.revealField(urlField) }
            SwirlText {text:"导入范围";color:Theme.text}
            SwirlComboBox {id:importScope;objectName:"subscriptionImportScope";Layout.fillWidth:true;model:[qsTr("完整配置（严格校验）"),qsTr("仅导入节点")];Accessible.name:"订阅导入范围";onActiveFocusChanged:if(activeFocus)page.revealField(importScope)}
            SwirlText {text:importScope.currentIndex===1?"仅更新节点，不应用本次订阅的全局配置；已保存的规则与 DNS 保持不变，引用失效时更新失败。":"完整配置需要受支持的规则、DNS、代理组及全局字段；不支持时保留旧节点与网络配置。";color:Theme.muted;font.pixelSize:Theme.fontSize(11);Layout.fillWidth:true;wrapMode:Text.WordWrap}
            SwirlText {text:qsTr("订阅格式");color:Theme.text}
            SwirlComboBox{id:formatPreference;objectName:"subscriptionFormat";Layout.fillWidth:true;model:[qsTr("自动"),"Clash","Loon",qsTr("Shadowrocket / 通用"),"Surge / Surfboard","Quantumult X","sing-box"];Accessible.name:qsTr("订阅格式");onActiveFocusChanged:if(activeFocus)page.revealField(formatPreference)}
            SwirlText {text:"向服务端请求此客户端格式；下载后仍检测实际内容，不把客户端格式当成协议。";color:Theme.muted;font.pixelSize:Theme.fontSize(11);Layout.fillWidth:true;wrapMode:Text.Wrap}
            SwirlComboBox {id:interval;Layout.fillWidth:true;model:["每 6 小时","每 12 小时","每天","每周"];Accessible.name:"自动更新间隔";onActiveFocusChanged:if(activeFocus)page.revealField(interval)}
            RowLayout {Layout.fillWidth:true;SwirlText {text:"自动更新";color:Theme.text;Layout.fillWidth:true}SwirlToggle {id:autoEnabled;checked:true}}
            SwirlText {text:engineController.imports.message;color:Theme.orange;Layout.fillWidth:true;wrapMode:Text.Wrap;font.pixelSize:Theme.fontSize(11)}
                }
            }
            RowLayout {
                Layout.alignment:Qt.AlignRight
                SwirlButton { text:AppState.zh("Cancel"); onClicked:addDialog.requestDismiss() }
                SwirlButton { enabled:!engineController.imports.busy && displayName.text.trim().length>0 && (page.editingId.length>0 || urlField.text.trim().length>0);
                    objectName:"saveSubscription";text:"保存并更新"; primary:true
                    onClicked:{if(engineController.imports.saveSubscription(page.editingId,displayName.text,urlField.text.trim(),[360,720,1440,10080][interval.currentIndex],autoEnabled.checked,["auto","clash","loon","shadowrocket","surge","quantumult-x","sing-box"][formatPreference.currentIndex],importScope.currentIndex===1?"nodes-only":"full-profile")){var id=page.editingId||engineController.imports.providers[engineController.imports.providers.length-1].id;addDialog.close();engineController.imports.refreshSubscription(id)}}
                }
            }
        }
    }
}
