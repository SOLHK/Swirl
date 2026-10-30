.pragma library

// Original cloud loops, with short tucked ends extended through the crossings.
// Each continuous guide ends in the permanent cloud geometry.
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
    { passage: 1, start: 0.000, end: 0.091 }, // coral over purple
    { passage: 2, start: 0.918, end: 1.000 }, // cyan over purple
    { passage: 3, start: 0.112, end: 0.193 }  // purple over coral
];

// One 4.8s handoff: warm wing to cloud, crown answer, lower loop, right curl, heart.
// Most of the interval belongs to the weave, with overlapping arrivals.
var timing = { connections: [0.02, 0.34, 0.74], connection: [0.10, 0.43, 0.84],
    traffic: [0.16, 0.49, 0.89], sources: [0.22, 0.55, 0.95], diagnostics: [0.32, 0.67, 0.99] };
function point(x, y) { return { x: x, y: y } }
function distance(a, b) { return Math.hypot(a.x - b.x, a.y - b.y) }
function mix(a, b, t) { return point(a.x + (b.x - a.x) * t, a.y + (b.y - a.y) * t) }
function command(p) { return p.x.toFixed(3) + " " + p.y.toFixed(3) }
function cubicPoint(a, b, c, d, t) {
    const ab = mix(a, b, t), bc = mix(b, c, t), cd = mix(c, d, t);
    return mix(mix(ab, bc, t), mix(bc, cd, t), t);
}

// The wing hands off into the sidebar gutter. One broad arc follows the
// space below the connection card, disappears behind its round corner, then
// emerges inside the reserved emblem area. All five guides share that flow.
function route(passage, cards, emblem, origin, scale, wide, gap, scene) {
    const card = passage.card, status = cards.connection, wing = scene.wing;
    const entry = point(origin.x + passage.start[0] * scale, origin.y + passage.start[1] * scale);
    const tangent = point(passage.tangent[0], passage.tangent[1]);
    const tangentLength = Math.hypot(tangent.x, tangent.y);
    const approach = point(entry.x - tangent.x / tangentLength * gap,
                           entry.y - tangent.y / tangentLength * gap);
    const lane = {connections: 0, connection: 1, traffic: 2, sources: 3, diagnostics: 4}[card];
    const drift = lane * gap * 0.10;
    const start = mix(wing[0], wing[1], 0.44 + lane * 0.09);
    const shoulder = point(wing[1].x + drift, wing[1].y - drift);
    const gutter = scene.sidebar.x + scene.sidebar.width + gap * 0.5;
    const rowY = status.y + status.height + gap * 0.5;
    const lift = point(gutter, wing[2].y - gap * 1.2);
    const sweep = point(gutter + gap, rowY);
    const corner = point(status.x + status.width - gap * 0.75, rowY);
    const gate = point(emblem.x + emblem.width * 0.72, emblem.y + emblem.height - gap * 0.25);
    // Explicit cubic handles keep the two open-space turns broad, instead of
    // interpolating a list of rectangular card corners.
    const curves = [
        [start, shoulder, point(wing[2].x, wing[2].y + gap), point(wing[2].x, wing[2].y)],
        [point(wing[2].x, wing[2].y), point(wing[2].x, wing[2].y - gap),
            point(lift.x, lift.y + gap), lift],
        [lift, point(gutter, lift.y - Math.max(gap, (lift.y-rowY)*0.5)),
            point(gutter - gap * 2, rowY), sweep],
        [sweep, point(sweep.x + (corner.x-sweep.x)*0.36, rowY),
            point(corner.x-gap*1.7, rowY), corner],
        [corner, point(corner.x+gap*1.7, rowY),
            point(gate.x+gap*1.8, gate.y+gap*0.9), gate],
        [gate, point(gate.x-gap*1.8, gate.y-gap*0.9), approach, entry]
    ];
    let guide = "M" + command(start), leadLength = 0;
    for (let j=0; j<curves.length; ++j) {
        const curve = curves[j];
        guide += " C" + command(curve[1]) + " " + command(curve[2]) + " " + command(curve[3]);
        let previous = curve[0];
        for (let n=1; n<=40; ++n) {
            const p=cubicPoint(curve[0],curve[1],curve[2],curve[3],n/40);
            leadLength+=distance(previous,p); previous=p;
        }
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
    const cues = [[times[0],0], [times[1],leadLength/total], [times[2],1]];
    return {guide:guide, join:leadLength/total, span:(card === "connections" ? 140 : 105)*gap/16/total, cues:cues};
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
