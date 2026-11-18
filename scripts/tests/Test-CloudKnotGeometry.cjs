#!/usr/bin/env node
'use strict';

// Executes the shipped QML JavaScript, rather than a second implementation of
// its paths or animation mathematics. No Qt window or proxy state is touched.
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const root = path.resolve(__dirname, '../..');

function library(relativePath) {
    const context = vm.createContext({});
    const source = fs.readFileSync(path.join(root, relativePath), 'utf8');
    vm.runInContext(source.replace(/^\.pragma library\r?\n/, ''), context, { filename: relativePath });
    return context;
}

const knot = library('src/Swirl.Quick/qml/components/SwirlCloudKnotPaths.js');
const wing = library('src/Swirl.Quick/qml/controls/SwirlWingMaster.js');
const materials = knot.materials(wing.feathers, wing.echoFeathers);
assert.equal(materials.length, 5, 'all five physical feathers must participate');
assert.equal(new Set(materials.map(material => material.key)).size, 5);
assert.equal(knot.materials(wing.feathers, wing.echoFeathers), materials,
    'immutable feather outlines must be cached across evaluations');

const poseFields = ['a', 'b', 'c', 'd', 'tx', 'ty', 'morph', 'opacity'];
let samples = 0;
let maximumJoinDelta = 0;

function close(actual, expected, tolerance, message) {
    assert.ok(Number.isFinite(actual) && Number.isFinite(expected)
        && Math.abs(actual - expected) <= tolerance,
    `${message}: actual=${actual}, expected=${expected}, tolerance=${tolerance}`);
}

function checkPose(pose, name) {
    for (const field of poseFields) assert.ok(Number.isFinite(pose[field]), `${name}: finite ${field}`);
    assert.ok(pose.morph >= 0 && pose.morph <= 1, `${name}: bounded morph`);
    assert.ok(pose.opacity >= 0 && pose.opacity <= 1, `${name}: bounded opacity`);
    assert.ok(pose.a * pose.d - pose.b * pose.c > 0, `${name}: no reflection or collapsed feather`);
    ++samples;
}

// These are arithmetic fixtures at different logical sizes/scales. They do not
// claim Windows display scaling, real card layout, or native GPU acceptance.
for (const uiScale of [1, 1.25, 1.5, 1.75, 2]) {
    for (const viewportWidth of [440, 736, 1000, 1400]) {
        const box = (x, y, width, height) => ({
            x: x * uiScale, y: y * uiScale,
            width: width * uiScale, height: height * uiScale
        });
        const scene = {
            sidebar: box(8, 8, 180, 700), viewport: box(200, 100, viewportWidth, 600),
            traffic: box(650, 120, 400, 238), sources: box(220, 374, 450, 326),
            connections: box(686, 550, 350, 150),
            toolbar: [box(500, 45, 100, 36), box(620, 45, 100, 36), box(740, 45, 88, 36)]
        };
        const gap = 16 * uiScale;
        const scale = 0.16 * uiScale;
        const origin = { x: 300 * uiScale, y: 120 * uiScale };
        const angle = 0.075;
        const source = {
            a: Math.cos(angle) * 0.4 * uiScale, b: Math.sin(angle) * 0.4 * uiScale,
            c: -Math.sin(angle) * 0.37 * uiScale, d: Math.cos(angle) * 0.37 * uiScale,
            tx: 12 * uiScale, ty: 300 * uiScale
        };

        for (const material of materials) {
            const name = `${material.key}/${viewportWidth}/${uiScale}`;
            const records = material.side === 'right' ? wing.echoFeathers : wing.feathers;
            assert.equal(material.record, records[material.sourceIndex], `${name}: actual background feather`);
            assert.ok(material.targetPath.endsWith(' Z'), `${name}: closed permanent outline`);
            const destination = {
                x: origin.x + material.targetCenter.x * scale,
                y: origin.y + material.targetCenter.y * scale
            };
            const route = knot.flight(material, source, scene, destination, gap);
            assert.ok(route.points.length > 1, `${name}: usable route`);
            const last = route.points[route.points.length - 1];
            close(last.x, destination.x, 1e-8, `${name}: route ends at knot x`);
            close(last.y, destination.y, 1e-8, `${name}: route ends at knot y`);

            // The whole initial feather must occupy the original background
            // transform, including its non-uniform scale and slight rotation.
            const start = knot.pose(material, route, 0, 0, origin, scale, gap);
            for (const field of ['a', 'b', 'c', 'd', 'tx', 'ty']) {
                close(start[field], source[field], 1e-8, `${name}: source handoff ${field}`);
            }
            for (const release of [0, 0.15, 0.6, 1]) {
                for (let frame = 0; frame <= 240; ++frame) {
                    checkPose(knot.pose(material, route, frame / 240, release, origin, scale, gap), name);
                }
            }

            // Sample both sides of each independently timed stage boundary.
            // This catches jumps that an ordinary uniform frame sweep can miss.
            for (const boundary of [0.055, material.arrival, 0.98]) {
                const before = knot.pose(material, route, boundary - 1e-8, 0, origin, scale, gap);
                const after = knot.pose(material, route, boundary + 1e-8, 0, origin, scale, gap);
                for (const field of poseFields) {
                    const delta = Math.abs(before[field] - after[field]);
                    maximumJoinDelta = Math.max(maximumJoinDelta, delta);
                    close(before[field], after[field], 1e-3, `${name}: continuous stage ${boundary}/${field}`);
                }
            }

            const formed = knot.pose(material, route, 0.98, 0, origin, scale, gap);
            const settled = knot.pose(material, route, 1, 0, origin, scale, gap);
            close(settled.morph, 1, 1e-12, `${name}: complete permanent shape`);
            close(settled.a, scale, 1e-12, `${name}: final width scale`);
            close(settled.d, scale, 1e-12, `${name}: final height scale`);
            for (const field of poseFields) {
                close(formed[field], settled[field], 1e-10, `${name}: no final shrink or replacement ${field}`);
            }

            // Switching from the global flight layer to the local knot host
            // must retain exactly the same scene geometry at the endpoint.
            const hostOffset = { x: 225 * uiScale, y: 85 * uiScale };
            const localOrigin = { x: origin.x - hostOffset.x, y: origin.y - hostOffset.y };
            const local = knot.pose(material, route, 1, 0, localOrigin, scale, gap);
            close(local.tx + hostOffset.x, settled.tx, 1e-8, `${name}: reparented x`);
            close(local.ty + hostOffset.y, settled.ty, 1e-8, `${name}: reparented y`);
        }
    }
}

console.log(JSON.stringify({
    passed: true, materials: materials.length, layoutFixtures: 4, scaleFixtures: 5,
    poseSamples: samples, maximumJoinDelta,
    scope: 'Shipped JavaScript geometry only; Qt, Windows DPI, GPU and visual interaction require their own gates.'
}));
