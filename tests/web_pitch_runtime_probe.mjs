import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { createRequire } from 'node:module';
import { resolve } from 'node:path';

const rootValue = process.env.VO_SE_VOCAL_ROOT;
assert.ok(rootValue, 'VO_SE_VOCAL_ROOT must point to the checked-out VO-SE_vocal repository');
const root = resolve(rootValue);
const moduleRoot = process.env.AXRAL_NODE_MODULES_ROOT || root;
const requireFromVoiceRepo = createRequire(resolve(moduleRoot, 'package.json'));
const ts = requireFromVoiceRepo('typescript');

const utilitySource = readFileSync(resolve(root, 'assets/src/utils/pitchCurve.ts'), 'utf8');
const compiledUtility = ts.transpileModule(utilitySource, {
  compilerOptions: { module: ts.ModuleKind.ESNext, target: ts.ScriptTarget.ES2022 },
}).outputText;
const utilityUrl = 'data:text/javascript;base64,' + Buffer.from(compiledUtility, 'utf8').toString('base64');

const clientSource = readFileSync(resolve(root, 'assets/src/voseCoreClient.ts'), 'utf8');
const framePeriodMatch = clientSource.match(/const PITCH_FRAME_PERIOD_MS = (\d+);/);
assert.ok(framePeriodMatch, 'production pitch frame period was not found');
const framePeriod = Number(framePeriodMatch[1]);
assert.ok(Number.isFinite(framePeriod) && framePeriod > 0, 'production pitch frame period is invalid');

const normalizeMatch = clientSource.match(/function normalizeTrailingControlPoint\([\s\S]*?\n}\n\n/);
assert.ok(normalizeMatch, 'production normalizeTrailingControlPoint helper was not found');
const helperMatch = clientSource.match(
  /function buildPitchAndPortamento\([\s\S]*?\n}\n\nfunction silentFrames/
);
assert.ok(helperMatch, 'production buildPitchAndPortamento helper was not found');

const normalizeSource = normalizeMatch[0];
const helperSource = helperMatch[0].replace(/\n\nfunction silentFrames$/, '');
const bridgeSource =
  'import { parsePitchBend, softClampSemitone, sampleSemitoneAt, ' +
  'hasExplicitUstPortamento, generateUtauPortamentoPoints } from ' +
  JSON.stringify(utilityUrl) + ';\n' +
  'const PITCH_FRAME_PERIOD_MS = ' + framePeriod + ';\n' +
  normalizeSource + helperSource + '\nexport { buildPitchAndPortamento };';
const compiledBridge = ts.transpileModule(bridgeSource, {
  compilerOptions: { module: ts.ModuleKind.ESNext, target: ts.ScriptTarget.ES2022 },
}).outputText;
const bridgeUrl = 'data:text/javascript;base64,' + Buffer.from(compiledBridge, 'utf8').toString('base64');
const bridge = await import(bridgeUrl);

// The current production bridge passes base F0 in Hz and pitch offsets in cents
// to the worker. The native engine applies cents as baseHz * 2 ** (cents / 1200).
// Sample the actual 5 ms production curve at 0, 50 and 100 ms.
const frameCount = Math.round(100 / framePeriod) + 1;
const sampleIndices = [0, Math.round(50 / framePeriod), Math.round(100 / framePeriod)];

function sampleProductionCurve(note) {
  const result = bridge.buildPitchAndPortamento(
    note, frameCount, 100, undefined, undefined, 0, 0
  );
  assert.ok(Array.isArray(result.pitchCurveHz), 'production helper did not return pitchCurveHz');
  assert.ok(Array.isArray(result.portamentoOffsets), 'production helper did not return cent-domain portamentoOffsets');
  assert.equal(result.pitchCurveHz.length, frameCount);
  assert.equal(result.portamentoOffsets.length, frameCount);

  const baseHz = result.pitchCurveHz[0];
  return sampleIndices.map((index) => {
    const cents = result.portamentoOffsets[index];
    assert.ok(Number.isFinite(cents), 'production helper returned a non-finite pitch offset');
    return baseHz * Math.pow(2, cents / 1200);
  });
}

const curves = {
  positive: sampleProductionCurve({
    noteNum: 69, pbs: '0;0', pbw: '100', pby: '20',
  }),
  negative: sampleProductionCurve({
    noteNum: 69, pbs: '0;0', pbw: '100', pby: '-20',
  }),
  steep: sampleProductionCurve({
    noteNum: 69, pbs: '0;0', pbw: '100', pby: '100',
  }),
};
process.stdout.write(JSON.stringify(curves));
