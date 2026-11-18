// npm audit reports published versions and cannot see a local source guard.
// CI runs a separate unfiltered audit of the production dependency graph.
import { readFileSync } from 'node:fs'
import assert from 'node:assert/strict'

const audit = JSON.parse(readFileSync(process.argv[2], 'utf8'))
assert.equal(audit.auditReportVersion, 2)
assert.ok(!audit.error && audit.vulnerabilities && audit.metadata?.vulnerabilities)
const lock = JSON.parse(readFileSync('package-lock.json', 'utf8')).packages
const advisory = 'https://github.com/advisories/GHSA-fc5q-39xc-vjpf'
const reviewBy = Date.parse('2026-12-18T00:00:00Z')

function guardedOnly(name, ancestors = new Set()) {
  const item = audit.vulnerabilities[name]
  if (!item || ancestors.has(name) || !item.nodes.length || !item.via.length) return false
  if (!item.nodes.every(path => lock[path]?.dev === true)) return false
  const visited = new Set([...ancestors, name])
  return item.via.every(cause => typeof cause === 'string'
    ? guardedOnly(cause, visited)
    : name === 'picomatch' && cause.url === advisory && cause.severity === 'high')
}

for (const [name, item] of Object.entries(audit.vulnerabilities)) {
  if (['info', 'low'].includes(item.severity)) continue
  assert.ok(Date.now() < reviewBy && guardedOnly(name), 'Unmitigated or expired advisory: ' + name)
  console.warn(name + ': covered by the verified build-only picomatch patch until 2026-12-18')
}
