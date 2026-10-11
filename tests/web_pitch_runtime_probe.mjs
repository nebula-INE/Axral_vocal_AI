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

const utilitySource = readFileSync(resolve(root, 'src/utils/pitchCurve.ts'), 'utf8');
const compiledUtility = ts.transpileModule(utilitySource, {
  compilerOptions: { module: ts.ModuleKind.ESNext, target: ts.ScriptTarget.ES2022 },
}).outputText;
const utilityUrl = 'data:text/javascript;base64,' + Buffer.from(compiledUtility, 'utf8').toString('base64');

const clientSource = readFileSync(resolve(root, 'src/voseCoreClient.ts'), 'utf8');
const helperMatch = clientSource.match(
  /function buildPitchCurveHz\\(note: any, frameCount: number, durationMs: number\\): number\\[\\] \\{[\\s\\S]*?\\r?\\n\\}\\r?\\n\\r?\\nfunction silentFrames/
);
assert.ok(helperMatch, 'production buildPitchCurveHz helper was not found');
const helperSource = helperMatch[0].replace(/\\r?\\n\\r?\\nfunction silentFrames$/, '\\nexport { buildPitchCurveHz };');
const bridgeSource = 'import { parsePitchBend, smoothPitchBendPoints } from ' +
  JSON.stringify(utilityUrl) + ';\\n' + helperSource;
const compiledBridge = ts.transpileModule(bridgeSource, {
  compilerOptions: { module: ts.ModuleKind.ESNext, target: ts.ScriptTarget.ES2022 },
}).outputText;
const bridgeUrl = 'data:text/javascript;base64,' + Buffer.from(compiledBridge, 'utf8').toString('base64');
const bridge = await import(bridgeUrl);

// Exercise the actual production Web helper with positive, negative, and steep
// UST bends. UST PBY values are tenths of a semitone.
const cases = {
  positive: {
    note: { noteNum: 69, pbs: '0;0', pbw: '50,50', pby: '10,20' },
    frameCount: 3,
    durationMs: 100,
  },
  negative: {
    note: { noteNum: 69, pbs: '0;0', pbw: '100', pby: '-20' },
    frameCount: 3,
    durationMs: 100,
  },
  steep: {
    note: { noteNum: 69, pbs: '0;0', pbw: '100', pby: '100' },
    frameCount: 3,
    durationMs: 100,
  },
};
const curves = Object.fromEntries(
  Object.entries(cases).map(([name, fixture]) => [
    name,
    bridge.buildPitchCurveHz(fixture.note, fixture.frameCount, fixture.durationMs),
  ]),
);
process.stdout.write(JSON.stringify(curves));
