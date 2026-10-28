pragma ComponentBehavior: Bound
import QtQuick
import QtQuick.Shapes
import SwirlQuick

Item {
    id: wing
    property real progress: 0
    property bool largeWing: false
    readonly property int featherCount: paths.length
    readonly property real artWidth: largeWing ? 1600 : 96
    readonly property real artHeight: largeWing ? 1000 : 48
    readonly property real fit: Math.min(width / artWidth, height / artHeight)
    readonly property var paths: largeWing ? [
        "M -70 830 C 35 957 205 955 415 868 C 798 709 1202 359 1570 20 C 1246 388 825 745 433 915 C 206 1000 10 1002 -70 830 Z",
        "M 280 925 C 653 771 1093 505 1460 205 C 1125 544 684 827 300 960 Z",
        "M 408 942 C 692 835 1061 656 1365 425 C 1118 698 736 904 439 970 Z",
        "M 510 954 C 751 871 1007 751 1235 650 C 1038 795 782 942 520 980 Z",
        "M 600 980 C 800 918 1004 844 1140 795 C 1020 895 842 965 610 1000 Z"
    ] : [
        "M5 39C21 37 26 22 42 14C57 6 76 5 92 4C83 12 72 17 58 20C39 24 26 39 5 39Z",
        "M10 42C30 39 40 27 57 24C67 22 77 20 85 16C79 25 67 30 55 31C36 33 25 43 10 42Z",
        "M18 44C34 41 43 35 56 34C65 33 71 31 77 28C70 36 62 39 52 39C38 39 30 45 18 44Z",
        "M30 45C40 42 47 42 54 42C59 42 63 41 67 39C62 44 56 46 50 45C42 44 37 46 30 45Z"
    ]
    implicitWidth: Theme.dp(40)
    implicitHeight: Theme.dp(20)
    visible: progress > 0
    Accessible.ignored: true

    function featherProgress(index) {
        const stagger = 0.6 / (featherCount - 1)
        const value = Math.max(0, Math.min(1, (progress - index * stagger) / 0.4))
        return value * value * (3 - 2 * value)
    }

    Item {
        x: (wing.width - wing.artWidth * wing.fit) / 2
        y: (wing.height - wing.artHeight * wing.fit) / 2
        width: wing.artWidth
        height: wing.artHeight
        scale: wing.fit
        transformOrigin: Item.TopLeft
        Repeater {
            model: wing.featherCount
            Item {
                id: feather
                required property int index
                objectName: "wingFeather" + index
                readonly property real reveal: wing.featherProgress(index)
                // Reveal each original contour from its root, then release its fold.
                width: wing.artWidth * reveal
                height: wing.artHeight
                clip: reveal < 1
                visible: reveal > 0
                opacity: Math.min(1, reveal * 5) * (wing.largeWing ? 1 : 1 - index * 0.18)
                transform: [
                    Scale { origin.y: wing.artHeight; yScale: 0.6 + 0.4 * feather.reveal },
                    Rotation { origin.y: wing.artHeight; angle: (1 - feather.reveal) * 5 }
                ]
                Shape {
                    objectName: wing.largeWing && feather.index === 0 ? "apecFlatWingPaths" : "wingFeatherPath" + feather.index
                    width: wing.artWidth
                    height: wing.artHeight
                    preferredRendererType: Shape.CurveRenderer
                    ShapePath {
                        strokeWidth: 0
                        strokeColor: "transparent"
                        fillRule: ShapePath.WindingFill
                        fillGradient: LinearGradient {
                            x1: wing.largeWing ? 160 : 8
                            y1: wing.largeWing ? 960 : 42
                            x2: wing.largeWing ? 1560 : 83
                            y2: wing.largeWing ? 30 : 5
                            GradientStop { position: 0; color: wing.largeWing ? Theme.withAlpha(Theme.wingGold, 0.42) : Theme.wingSmallStart }
                            GradientStop { position: 0.16; color: wing.largeWing ? Theme.withAlpha(Theme.wingCoral, 0.65) : Theme.wingSmallStart }
                            GradientStop { position: 0.33; color: wing.largeWing ? Theme.wingRose : Theme.wingSmallMid }
                            GradientStop { position: 0.55; color: wing.largeWing ? Theme.wingCyan : Theme.wingSmallMid }
                            GradientStop { position: 0.79; color: wing.largeWing ? Theme.withAlpha(Theme.wingTeal, 0.74) : Theme.wingSmallEnd }
                            GradientStop { position: 1; color: wing.largeWing ? Theme.withAlpha(Theme.wingGreen, 0.48) : Theme.wingSmallEnd }
                        }
                        PathSvg { path: wing.paths[feather.index] }
                    }
                }
            }
        }
    }
}
