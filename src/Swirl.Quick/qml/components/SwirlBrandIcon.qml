import QtQuick
import QtQuick.Effects
import SwirlQuick
Rectangle {
    radius:width*0.29; antialiasing:true
    gradient:Gradient { GradientStop {position:0;color:Theme.dark ? "#3A3A3A" : "#FFFFFF"} GradientStop {position:1;color:Theme.dark ? "#303030" : "#F7F7F7"} }
    layer.enabled:true
    layer.effect:MultiEffect {shadowEnabled:true;shadowColor:"#000000";shadowOpacity:0.06;shadowBlur:0.35;shadowVerticalOffset:3}
    Image {anchors.fill:parent;anchors.margins:6;source:"qrc:/swirl/icons/swirl_wave_mark.svg";sourceSize:Qt.size(256,256);fillMode:Image.PreserveAspectFit}
}
