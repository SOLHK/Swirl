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

// All five ribbons launch together. Different tours arrive independently,
// leaving the latter half of the 4.8s clock for the permanent cloud strokes.
var timing = { connections: [0.02, 0.36, 0.82], connection: [0.02, 0.47, 0.88],
    traffic: [0.02, 0.62, 0.97], sources: [0.02, 0.50, 0.94], diagnostics: [0.02, 0.58, 0.99] };
function point(x, y) { return { x: x, y: y } }
function distance(a, b) { return Math.hypot(a.x - b.x, a.y - b.y) }
function mix(a, b, t) { return point(a.x + (b.x - a.x) * t, a.y + (b.y - a.y) * t) }
function command(p) { return p.x.toFixed(3) + " " + p.y.toFixed(3) }
function cubicPoint(a, b, c, d, t) {
    const ab = mix(a, b, t), bc = mix(b, c, t), cd = mix(c, d, t);
    return mix(mix(ab, bc, t), mix(bc, cd, t), t);
}

// Each colour has its own continuous tour. Only the title's small padded
// aperture is brought in front of a card; all other detours use real occlusion.
function route(passage, cards, emblem, origin, scale, wide, gap, scene) {
    const card = passage.card, status = cards.connection;
    const fromRight = card === "connection" || card === "diagnostics";
    const wing = fromRight ? scene.rightWing : scene.leftWing;
    const entry = point(origin.x + passage.start[0] * scale, origin.y + passage.start[1] * scale);
    const tangent = point(passage.tangent[0], passage.tangent[1]);
    const tangentLength = Math.hypot(tangent.x, tangent.y);
    const approach = point(entry.x - tangent.x / tangentLength * gap,
                           entry.y - tangent.y / tangentLength * gap);
    const rightLimit = scene.viewport.x + scene.viewport.width - gap * 0.35;
    const gutter = scene.sidebar.x + scene.sidebar.width + gap * 0.5;
    const rowY = status.y + status.height + gap * 0.5;
    const column = Math.min(rightLimit, status.x + status.width + gap * 0.5);
    const gate = point(emblem.x + emblem.width * 0.76, emblem.y + emblem.height - gap * 0.4);
    const starts = {connections: 0.34, traffic: 0.04, sources: 0.70, connection: 0, diagnostics: 1};
    const start = mix(wing[0], wing[1], starts[card]);
    const curves = [];
    let cursor = start;
    let aperture = {x:0, y:0, width:0, height:0};
    function bend(b, c, d) { curves.push([cursor,b,c,d]); cursor=d; }
    function enterBelow(b) {
        bend(b, point(gate.x+gap,gate.y+gap),gate);
        bend(point(gate.x-gap,gate.y-gap),approach,entry);
    }
    if (card === "connections") {
        // Gold: wing shoulder, rising gutter, a relaxed sweep under the card.
        const tip = point(wing[2].x,wing[2].y);
        const lift = point(gutter-gap*0.2,tip.y-gap*1.2);
        const sweep = point(gutter+gap,rowY-gap*0.22);
        bend(wing[1],point(tip.x,tip.y+gap),tip);
        bend(point(tip.x,tip.y-gap),point(lift.x,lift.y+gap),lift);
        bend(point(lift.x,lift.y-Math.max(gap,(lift.y-rowY)*0.5)),point(sweep.x-gap*2,sweep.y),sweep);
        enterBelow(point(sweep.x+(gate.x-sweep.x)*0.5,sweep.y));
    } else if (card === "traffic") {
        // Coral: one complete rounded lap around the connection card.
        const l=status.x-gap*0.5, r=column, t=status.y-gap*0.5, b=rowY;
        const radius=Math.min(gap*1.25,status.width*0.12,status.height*0.12), k=0.55228475;
        const begin=point(l+radius,b);
        bend(point(start.x+gap*2,start.y-gap),point(begin.x-gap*2,begin.y),begin);
        bend(point(l+radius+gap,b),point(r-radius-gap,b),point(r-radius,b));
        bend(point(r-radius+k*radius,b),point(r,b-radius+k*radius),point(r,b-radius));
        bend(point(r,b-radius-gap),point(r,t+radius+gap),point(r,t+radius));
        bend(point(r,t+radius-k*radius),point(r-radius+k*radius,t),point(r-radius,t));
        bend(point(r-radius-gap,t),point(l+radius+gap,t),point(l+radius,t));
        bend(point(l+radius-k*radius,t),point(l,t+radius-k*radius),point(l,t+radius));
        bend(point(l,t+radius+gap),point(l,b-radius-gap),point(l,b-radius));
        bend(point(l,b-radius+k*radius),point(l+radius-k*radius,b),begin);
        enterBelow(point(begin.x+(gate.x-begin.x)*0.5,b));
    } else if (card === "sources") {
        // Purple: a compact vertical loop beside the lower card's shoulder.
        const cx=gutter+gap*0.15;
        const cy=Math.min(cards.sources.y+gap*2.4,scene.viewport.y+scene.viewport.height-gap*3);
        const rx=gap*0.58, ry=gap*1.55, k=0.55228475;
        const bottom=point(cx,cy+ry);
        bend(point(start.x+gap*2,start.y-gap),point(cx-gap,cy+ry),bottom);
        bend(point(cx+k*rx,cy+ry),point(cx+rx,cy+k*ry),point(cx+rx,cy));
        bend(point(cx+rx,cy-k*ry),point(cx+k*rx,cy-ry),point(cx,cy-ry));
        bend(point(cx-k*rx,cy-ry),point(cx-rx,cy-k*ry),point(cx-rx,cy));
        bend(point(cx-rx,cy+k*ry),point(cx-k*rx,cy+ry),bottom);
        const sweep=point(gutter+gap*2,rowY+gap*0.22);
        bend(point(cx+gap,cy+ry),point(sweep.x-gap,sweep.y),sweep);
        enterBelow(point(sweep.x+(gate.x-sweep.x)*0.45,sweep.y));
    } else if (card === "connection") {
        // Cyan: leave the right wing to the left, circle the real title once,
        // then descend the column gutter. The centreline never enters the text.
        const exit=point(wing[2].x,wing[2].y);
        bend(wing[1],point(exit.x+gap,exit.y),exit);
        if (wide) {
            // Keep the bottom pass in the title-to-rate gap, not in the
            // upload value's row; the wider sides still give the ribbon room.
            const text=scene.trafficTitle, pad=gap*0.6, bottomPad=gap*0.15, radius=bottomPad, k=0.55228475;
            const l=text.x-pad, r=text.x+text.width+pad, t=text.y-pad, b=text.y+text.height+bottomPad;
            const orbit=point(r-radius,t);
            const fringe=25*scale*0.65+gap*0.12;
            aperture={x:l-fringe,y:t-fringe,width:r-l+fringe*2,height:b-t+fringe*2};
            bend(point(exit.x-gap*2,exit.y),point(orbit.x+gap*2,orbit.y),orbit);
            bend(point(r-radius-gap,t),point(l+radius+gap,t),point(l+radius,t));
            bend(point(l+radius-k*radius,t),point(l,t+radius-k*radius),point(l,t+radius));
            bend(point(l,t+radius+gap*0.3),point(l,b-radius-gap*0.3),point(l,b-radius));
            bend(point(l,b-radius+k*radius),point(l+radius-k*radius,b),point(l+radius,b));
            bend(point(l+radius+gap,b),point(r-radius-gap,b),point(r-radius,b));
            bend(point(r-radius+k*radius,b),point(r,b-radius+k*radius),point(r,b-radius));
            bend(point(r,b-radius-gap*0.3),point(r,t+radius+gap*0.3),point(r,t+radius));
            bend(point(r,t+radius-k*radius),point(r-radius+k*radius,t),orbit);
            bend(point(orbit.x-gap,orbit.y),point(column,orbit.y),point(column,orbit.y+gap*2));
        } else {
            // The traffic title is below the visible row in a narrow window.
            // Turn in the top margin rather than following it off screen.
            const top=status.y-gap*0.55;
            bend(point(exit.x-gap,exit.y),point(column,top),point(column,status.y+gap*1.8));
        }
        const side=point(emblem.x+emblem.width-gap*0.25,emblem.y+emblem.height*0.53);
        bend(point(column,cursor.y+gap*2),point(side.x+gap*0.2,side.y),side);
        bend(point(side.x-gap,side.y),approach,entry);
    } else {
        // Green travels the other way off the echo, around the traffic card's
        // outer flank, and curls back under it. Narrow layouts use the status card.
        const tour=wide?cards.traffic:status;
        const outer=Math.min(rightLimit,tour.x+tour.width+gap*0.5);
        const bottom=tour.y+tour.height+gap*0.5, radius=gap*1.2, k=0.55228475;
        bend(wing[0],point(outer,status.y-gap*0.5),point(outer,status.y+gap*1.6));
        bend(point(outer,status.y+gap*4),point(outer,bottom-radius-gap),point(outer,bottom-radius));
        bend(point(outer,bottom-radius+k*radius),point(outer-radius+k*radius,bottom),point(outer-radius,bottom));
        if (wide) {
            const turn=point(column-gap*0.35,bottom);
            bend(point(cursor.x-gap*2,bottom),point(turn.x+gap*2,bottom),turn);
        }
        enterBelow(point(cursor.x-gap,bottom));
    }
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
    return {guide:guide, join:leadLength/total, span:(card === "traffic" ? 170 : 125)*gap/16/total, aperture:aperture, cues:cues};
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
