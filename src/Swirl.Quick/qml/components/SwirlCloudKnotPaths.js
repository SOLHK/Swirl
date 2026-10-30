.pragma library

// Original cloud loops, with short tucked ends extended through the crossings.
// Each passage keeps one card identity from the lead to the finished knot.
var passages = [
    {
        "key": "warm",
        "tangent": [
            18,
            -10
        ],
        "guide": "M254 558 C272 548 288 561 283 581 C280 613 249 633 219 633 C173 637 144 604 145 560 C144 511 189 470 242 462 C291 454 315 476 355 500 C399 531 440 545 478 513 C514 487 533 447 516 416 C504 393 475 388 456 404 C439 415 436 430 445 432",
        "start": [
            254,
            558
        ],
        "card": "connections",
        "ink": "#E9A54E"
    },
    {
        "key": "return",
        "tangent": [
            -30,
            7
        ],
        "guide": "M490 558 C460 565 430 580 415 587 C370 606 335 644 338 693 C334 752 390 800 453 801 C515 805 566 764 575 713 C579 697 577 685 575 678 C575 655 568 637 559 620",
        "start": [
            490,
            558
        ],
        "card": "traffic",
        "ink": "#DD6A78"
    },
    {
        "key": "crown",
        "tangent": [
            -14,
            -21
        ],
        "guide": "M390 529 C376 508 363 474 352 447 C336 416 343 376 362 349 C391 308 430 287 475 288 C557 278 624 340 625 430 C630 486 600 533 550 568 C532 580 518 594 503 609",
        "start": [
            390,
            529
        ],
        "card": "connection",
        "ink": "#459AB3"
    },
    {
        "key": "forward",
        "tangent": [
            58,
            20
        ],
        "guide": "M450 557 C508 577 558 624 611 651 C661 677 715 679 755 662 C801 644 827 607 828 565 C835 516 793 478 749 479 C708 475 675 499 676 535 C673 554 688 568 701 569 C711 569 711 562 710 559",
        "start": [
            450,
            557
        ],
        "card": "sources",
        "ink": "#8874C2"
    },
    {
        "key": "heart",
        "tangent": [
            -13,
            -1
        ],
        "guide": "M455 664 C442 663 434 677 443 690 C461 719 505 689 530 647 C548 620 563 594 577 574",
        "start": [
            455,
            664
        ],
        "card": "diagnostics",
        "ink": "#59A990"
    }
];

// Four local overpasses alternate depth; no global strand z-order can express this.
// Positions are arc-length fractions on the centre lines above.
var crossings = [
    { passage: 0, start: 0.595, end: 0.677 }, // orange over cyan
    { passage: 1, start: 0.000, end: 0.091 }, // green over purple
    { passage: 2, start: 0.918, end: 1.000 }, // cyan over purple
    { passage: 3, start: 0.112, end: 0.193 }  // purple over coral
];

// Cue values are time fractions of a 3.7-second tour, with overlapping arrivals.
var timing = { connection: [0, 0.70, 0.92], traffic: [0.09, 0.73, 0.93],
    sources: [0.16, 0.75, 0.94], diagnostics: [0.25, 0.78, 0.95], connections: [0.13, 0.80, 0.95] };
function point(x, y) { return { x: x, y: y } }
function distance(a, b) { return Math.hypot(a.x - b.x, a.y - b.y) }
function mix(a, b, t) { return point(a.x + (b.x - a.x) * t, a.y + (b.y - a.y) * t) }
function command(p) { return p.x.toFixed(3) + " " + p.y.toFixed(3) }
function cubicPoint(a, b, c, d, t) {
    const ab = mix(a, b, t), bc = mix(b, c, t), cd = mix(c, d, t);
    return mix(mix(ab, bc, t), mix(bc, cd, t), t);
}

// World coordinates: the same flight is hidden naturally by opaque cards and
// controls. Only its birth edge and emblem get a small foreground aperture.
function route(passage, cards, emblem, origin, scale, wide, gap, scene) {
    const card = passage.card, source = cards[card], status = cards.connection;
    const proxy = scene.proxy, sidebar = scene.sidebar, wing = scene.wing;
    const entry = point(origin.x + passage.start[0] * scale, origin.y + passage.start[1] * scale);
    const approach = point(entry.x - passage.tangent[0] * scale, entry.y - passage.tangent[1] * scale);
    const sidebarRight = sidebar.x + sidebar.width;
    const gutter = sidebarRight + gap * 0.5;
    const top = Math.max(gap * 0.35, proxy.y - gap * 0.35);
    const rowGap = status.y + status.height + gap * 0.5;
    const returnGate = point(status.x + status.width + gap * 0.5, emblem.y + emblem.height * 0.65);
    let start, points, aperture;
    if (card === "connection") {
        const r = proxy.height * 0.5;
        start = point(source.x + source.width * 0.82, source.y + gap * 0.2);
        points = [start, point(start.x + gap, source.y - gap * 0.35),
            point(proxy.x + proxy.width - r, proxy.y + proxy.height + gap * 0.25),
            point(proxy.x + proxy.width + gap * 0.25, proxy.y + r),
            point(proxy.x + proxy.width - r, top),
            point(sidebarRight - Math.min(sidebar.width * 0.2, gap * 1.8), top),
            point(gutter, sidebar.y + gap * 1.8), point(gutter, wing[0].y - gap),
            wing[0], wing[1], wing[2], wing[3],
            point(gutter + gap, rowGap), point(returnGate.x, rowGap), returnGate];
        aperture = {x:start.x-gap, y:source.y-gap, width:gap*2.5, height:gap*1.4};
    } else if (card === "traffic") {
        start = point(source.x + gap * 2.2, source.y + gap * 0.2);
        points = [start, point(source.x + gap * 0.5, source.y - gap * 0.35),
            point(source.x - gap * 0.4, source.y + gap), point(source.x - gap * 0.5, rowGap),
            point(gutter + gap, rowGap), wing[2], point(gutter + gap, rowGap + gap),
            point(returnGate.x + gap * 0.25, rowGap), returnGate];
        aperture = {x:start.x-gap, y:source.y-gap, width:gap*2, height:gap*1.4};
    } else if (card === "sources") {
        start = point(source.x + gap * 0.2, source.y + gap * 2.5);
        points = [start, point(source.x-gap*0.4, start.y-gap), point(gutter, start.y-gap*2),
            wing[0], wing[1], wing[2], point(gutter + gap, rowGap), point(returnGate.x, rowGap), returnGate];
        aperture = {x:source.x-gap, y:start.y-gap, width:gap*1.4, height:gap*2};
    } else if (card === "diagnostics") {
        start = point(source.x+gap*0.2, source.y+source.height*0.5);
        points = [start, point(source.x-gap*0.6,start.y-gap*0.5),point(source.x-gap*0.5,rowGap),
            point(returnGate.x,rowGap),point(returnGate.x+gap*0.4,emblem.y+emblem.height),returnGate];
        aperture = {x:source.x-gap,y:start.y-gap,width:gap*1.4,height:gap*2};
    } else {
        start = point(source.x+gap*2.2,source.y+gap*0.2);
        points = [start,point(source.x+gap*0.4,source.y-gap*0.5),point(source.x-gap*0.5,source.y+gap),
            point(source.x-gap*0.5,rowGap),point(returnGate.x+gap*0.25,rowGap),returnGate];
        aperture = {x:start.x-gap,y:source.y-gap,width:gap*2,height:gap*1.4};
    }
    if (!wide && card !== "connection" && card !== "sources") {
        const outside = status.x + status.width + gap * 0.5;
        points = [start, points[1], point(outside,source.y-gap*0.5),point(outside,emblem.y+emblem.height),returnGate];
    }
    points.push(approach, entry);
    let guide = "M" + command(points[0]), leadLength = 0;
    const wayLengths = [0];
    for (let i = 0; i < points.length - 1; ++i) {
        const a = points[i], d = points[i + 1], before = points[Math.max(0, i - 1)], after = points[Math.min(points.length - 1, i + 2)];
        const handle = Math.min(distance(a, d), i ? distance(before, a) : distance(a, d), distance(d, after) || distance(a, d)) * 0.26;
        const tangentA = distance(before, d) || 1, tangentD = distance(a, after) || 1;
        const b = point(a.x + (d.x - before.x) / tangentA * handle, a.y + (d.y - before.y) / tangentA * handle);
        const c = i === points.length - 2 ? approach : point(d.x - (after.x - a.x) / tangentD * handle, d.y - (after.y - a.y) / tangentD * handle);
        guide += " C" + command(b) + " " + command(c) + " " + command(d);
        let previous = a;
        for (let n = 1; n <= 40; ++n) { const p = cubicPoint(a, b, c, d, n / 40); leadLength += distance(previous, p); previous = p; }
        wayLengths.push(leadLength);
    }
    const tokens = passage.guide.match(/[MC]|[-+]?\d*\.?\d+/g);
    let i = 3, previous = entry, knotLength = 0;
    while (i < tokens.length) {
        ++i;
        const b = point(origin.x + Number(tokens[i++]) * scale, origin.y + Number(tokens[i++]) * scale);
        const c = point(origin.x + Number(tokens[i++]) * scale, origin.y + Number(tokens[i++]) * scale);
        const d = point(origin.x + Number(tokens[i++]) * scale, origin.y + Number(tokens[i++]) * scale);
        guide += " C" + command(b) + " " + command(c) + " " + command(d);
        const a = previous;
        for (let n = 1; n <= 40; ++n) { const p = cubicPoint(a, b, c, d, n / 40); knotLength += distance(previous, p); previous = p; }
    }
    const total = leadLength + knotLength;
    const times = timing[card];
    const cues = card === "connection" ? [
        [0,0], [0.18,wayLengths[4]/total], [0.37,wayLengths[7]/total],
        [0.59,wayLengths[11]/total], [times[1],leadLength/total], [times[2],1]
    ] : [[times[0],0], [times[1],leadLength/total], [times[2],1]];
    return {guide:guide, join:leadLength/total, span:(card === "connection" ? 150 : 100)*gap/16/total, aperture:aperture, cues:cues};
}
function hermite(t, a, b, startSlope, endSlope, duration) {
    return (2*t*t*t-3*t*t+1)*a + (t*t*t-2*t*t+t)*startSlope*duration
        + (-2*t*t*t+3*t*t)*b + (t*t*t-t*t)*endSlope*duration;
}
function head(progress, card, route) {
    const cues = route.cues;
    if (progress <= cues[0][0]) return 0;
    if (progress >= cues[cues.length-1][0]) return 1;
    function slope(index) {
        if (index === 0 || index === cues.length-1) return 0;
        const left = (cues[index][1]-cues[index-1][1])/(cues[index][0]-cues[index-1][0]);
        const right = (cues[index+1][1]-cues[index][1])/(cues[index+1][0]-cues[index][0]);
        return Math.min(left,right);
    }
    for (let i=0; i<cues.length-1; ++i) {
        if (progress <= cues[i+1][0]) {
            const duration = cues[i+1][0]-cues[i][0];
            return hermite((progress-cues[i][0])/duration,cues[i][1],cues[i+1][1],slope(i),slope(i+1),duration);
        }
    }
    return 1;
}
function tail(progress, card, route, headPosition) {
    const times = timing[card];
    const t = Math.max(0, Math.min(1, (progress - times[1]) / (times[2] - times[1])));
    const tucked = route.join * t * t * (3 - 2 * t);
    return Math.min(headPosition, route.join, Math.max(0, headPosition - route.span, tucked));
}
