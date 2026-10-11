import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { createRequire } from 'node:module';
import { resolve } from 'node:path';
import { pathToFileURL } from 'node:url';

const rootValue = process.env.VO_SE_VOCAL_ROOT;
assert.ok(rootValue, 'VO_SE_VOCAL_ROOT must point to the checked-out VO-SE_vocal repository');
const root = resolve(rootValue);
const requireFromVoiceRepo = createRequire(resolve(root, 'package.json'));
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

// Shared deterministic case: A4, 100 ms, pitch offsets 0 -> +2 semitones.
// The Web UST representation uses tenths of a semitone; 3 endpoint-inclusive
// samples should yield the same Hz values as the Desktop linear sampler.
const curve = bridge.buildPitchCurveHz({
  noteNum: 69,
  pbs: '0;0',
  pbw: '50,50',
  pby: '10,20',
}, 3, 100);
process.stdout.write(JSON.stringify(curve));
