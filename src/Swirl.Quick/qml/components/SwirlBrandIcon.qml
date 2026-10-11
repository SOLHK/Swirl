import QtQuick
import QtQuick.Effects
import SwirlQuick
Rectangle {
    radius:width*0.29; antialiasing:true
    gradient:Gradient { GradientStop {position:0;color:Theme.dark ? "#405570" : "#FFFFFF"} GradientStop {position:1;color:Theme.dark ? "#2D425E" : "#F2F8FF"} }
    layer.enabled:true
    layer.effect:MultiEffect {shadowEnabled:true;shadowColor:"#5378A3";shadowOpacity:0.14;shadowBlur:0.35;shadowVerticalOffset:3}
    Image {anchors.fill:parent;anchors.margins:6;source:"qrc:/swirl/swirl-mark.svg";sourceSize:Qt.size(256,256);fillMode:Image.PreserveAspectFit}
}
