pragma ComponentBehavior: Bound
import QtQuick
import QtQuick.Shapes
import SwirlQuick

Item {
    id: wing
    property real progress: 0
    property bool largeWing: false
    readonly property int featherCount: paths.length
    readonly property real artWidth: largeWing ? 1000 : 96
    readonly property real artHeight: largeWing ? 760 : 48
    readonly property real fit: Math.min(width / artWidth, height / artHeight)
    readonly property var roots: largeWing ? [Qt.point(80, 740), Qt.point(118, 754), Qt.point(164, 760), Qt.point(208, 768), Qt.point(252, 770)]
                                                : [Qt.point(5, 39), Qt.point(10, 42), Qt.point(18, 44), Qt.point(30, 45)]
    readonly property var paths: largeWing ? [
        "M80 740 C160 655 186 479 290 343 C391 211 519 154 642 168 C670 172 680 187 656 208 C549 298 433 314 365 407 C266 538 247 689 80 740 Z",
        "M118 754 C248 676 310 518 429 425 C537 341 648 306 757 327 C781 332 783 346 762 363 C659 431 563 436 488 490 C351 591 301 711 118 754 Z",
        "M164 760 C314 701 387 591 507 536 C599 492 683 481 762 504 C780 509 779 521 762 533 C683 581 604 572 534 608 C397 674 329 735 164 760 Z",
        "M208 768 C359 734 436 666 532 643 C609 624 675 625 727 646 C742 653 737 665 719 671 C650 697 597 680 538 699 C408 742 352 765 208 768 Z",
        "M252 770 C386 751 455 726 526 725 C581 724 622 733 656 748 C666 755 660 763 646 766 C596 776 551 755 503 760 C412 775 351 783 252 770 Z"
    ] : [
        "M5 39C21 37 26 22 42 14C57 6 76 5 92 4C83 12 72 17 58 20C39 24 26 39 5 39Z",
        "M10 42C30 39 40 27 57 24C67 22 77 20 85 16C79 25 67 30 55 31C36 33 25 43 10 42Z",
        "M18 44C34 41 43 35 56 34C65 33 65 37 60 39C48 40 30 45 18 44Z",
        "M30 45C40 42 47 42 54 42C59 42 63 41 67 39C62 44 56 46 50 45C42 44 37 46 30 45Z"
    ]
    readonly property var featherColors: Theme.dark
        ? ["#7CAFBF", "#9BA5C6", "#87B4A6", "#C6A0AA", "#90B8BE"]
        : ["#91BFCA", "#B3ACCE", "#A1C4B6", "#D4B4BA", "#A5C5CA"]
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
                readonly property point rootPoint: wing.roots[index]
                readonly property color featherColor: wing.featherColors[index]
                // Rounded swept feather lobes share a root direction, without shafts or veins.
                width: wing.artWidth
                height: wing.artHeight
                visible: reveal > 0
                opacity: Math.min(1, reveal * 8) * (wing.largeWing ? 1 : 1 - index * 0.18)
                transform: [
                    Scale {
                        origin.x: feather.rootPoint.x; origin.y: feather.rootPoint.y
                        xScale: 0.12 + 0.88 * feather.reveal
                        yScale: 0.18 + 0.82 * feather.reveal
                    },
                    Rotation {
                        origin.x: feather.rootPoint.x; origin.y: feather.rootPoint.y
                        angle: (1 - feather.reveal) * (12 + feather.index * 2)
                    }
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
                            x1: wing.largeWing ? 0 : 8
                            y1: wing.largeWing ? 760 : 42
                            x2: wing.largeWing ? 920 : 83
                            y2: wing.largeWing ? 80 : 5
                            GradientStop { position: 0; color: wing.largeWing ? Theme.withAlpha(feather.featherColor, 0.16) : Theme.wingSmallStart }
                            GradientStop { position: 0.16; color: wing.largeWing ? Theme.withAlpha(feather.featherColor, 0.26) : Theme.wingSmallStart }
                            GradientStop { position: 0.33; color: wing.largeWing ? Theme.withAlpha(feather.featherColor, 0.32) : Theme.wingSmallMid }
                            GradientStop { position: 0.55; color: wing.largeWing ? Theme.withAlpha(feather.featherColor, 0.48) : Theme.wingSmallMid }
                            GradientStop { position: 0.79; color: wing.largeWing ? Theme.withAlpha(feather.featherColor, 0.34) : Theme.wingSmallEnd }
                            GradientStop { position: 1; color: wing.largeWing ? Theme.withAlpha(feather.featherColor, 0.34) : Theme.wingSmallEnd }
                        }
                        PathSvg { path: wing.paths[feather.index] }
                    }

                }
            }
        }
    }
}
