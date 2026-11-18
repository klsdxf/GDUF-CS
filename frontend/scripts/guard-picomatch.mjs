// Temporary build-tool mitigation for GHSA-fc5q-39xc-vjpf. Remove when both
// upstream lines are fixed. npm's tarball integrity and these source hashes
// ensure a changed parser requires review before this patch can be applied.
import { createHash } from 'node:crypto'
import { existsSync, readFileSync, writeFileSync } from 'node:fs'

const parsers = new Map([
  ['node_modules/picomatch', '4e1e05447668aa1e94366c5516a2bcd8f5fff800cc92b1d0cd7d77703b8618c4'],
  ['node_modules/micromatch/node_modules/picomatch', '3a91656f440069aa8f8e15c9d695b9f6b2209df1eab2be8127c72cbcca45ff5f'],
])
const original = 'const analysis = analyzeRepeatedExtglob(body, opts);'
// Our build only needs literal bodies in repeating extglobs. Delegate other
// repeating bodies to the parser's existing literal fallback.
const guarded = `const complexRepeat = (token.type === 'plus' || token.type === 'star') && !/^[a-zA-Z0-9_-]+$/.test(body);
    const analysis = complexRepeat ? { risky: true } : analyzeRepeatedExtglob(body, opts);`
const lock = JSON.parse(readFileSync('package-lock.json', 'utf8'))
for (const [path, pkg] of Object.entries(lock.packages)) {
  if (path.endsWith('/picomatch') && (!parsers.has(path) || !pkg.dev)) {
    throw new Error('Review new picomatch dependency: ' + path)
  }
}
for (const [path, hash] of parsers) {
  const file = path + '/lib/parse.js'
  const productionOnly = process.env.NODE_ENV === 'production' || process.env.npm_config_omit?.split(/\s+/).includes('dev')
  if (!existsSync(file) && productionOnly && !process.argv.includes('--check')) continue
  const current = readFileSync(file, 'utf8')
  const source = current.replace(guarded, original)
  if (createHash('sha256').update(source).digest('hex') !== hash || !source.includes(original)) {
    throw new Error('Unexpected picomatch parser: ' + path)
  }
  const patched = source.replace(original, guarded)
  if (patched !== current) {
    if (process.argv.includes('--check')) throw new Error('Missing picomatch guard: ' + path)
    writeFileSync(file, patched)
  }
}
