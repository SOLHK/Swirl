import QtQuick
import SwirlQuick
Item {
    id:expander
    default property alias contents:body.data
    property bool expanded:false
    property real reveal:expanded?1:0
    implicitHeight:body.implicitHeight*reveal
    opacity:reveal;clip:true;enabled:expanded
    Behavior on reveal{enabled:!SwirlMotion.reduced;NumberAnimation{duration:SwirlMotion.expandDuration;easing.type:Easing.OutCubic}}
    Column{id:body;width:expander.width}
}
