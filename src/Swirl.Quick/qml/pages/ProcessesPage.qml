import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import SwirlQuick
import "../components"
import "../controls"
Item {
 ColumnLayout { anchors.fill:parent; spacing:Theme.gap
  Text { text:"进程"; font.pixelSize:Theme.fontSize(30);font.weight:Font.DemiBold;color:Theme.text }
  Text { text:"仅统计实际经过 Swirl 的连接；无法识别的来源显示未知进程";color:Theme.muted;Layout.fillWidth:true;wrapMode:Text.Wrap }
  SwirlGlassPanel { Layout.fillWidth:true;Layout.fillHeight:true
   SwirlDataTable { anchors.fill:parent; rows:(engineController.telemetry.revision,engineController.telemetry.ranking("apps",0,100)); columns:[{key:"name",label:"进程",w:280},{key:"connections",label:"连接次数",w:140},{key:"upload",label:"上传",w:140},{key:"download",label:"下载",w:140}] }
  }
 }
}
