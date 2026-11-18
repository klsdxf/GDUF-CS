// k6 run --out json=... scripts/quality-load.js
import http from 'k6/http'
import { check } from 'k6'
import { Counter } from 'k6/metrics'

const base = __ENV.QUALITY_BASE_URL
const mode = __ENV.QUALITY_MODE || 'hot'
const quick = __ENV.QUALITY_QUICK === '1'
const hot = __ENV.QUALITY_EDITION || 'quality-hot'
const bad = new Counter('unexpected_responses')

if (!base || __ENV.GDUF_PERF_ONLY !== '1' || !['hot', 'uncached', 'mixed', 'steady'].includes(mode)) {
  throw new Error('Set GDUF_PERF_ONLY=1, QUALITY_BASE_URL, and a valid QUALITY_MODE on an isolated deployment')
}

const target = {
  hot: [100, '15m', 300],
  uncached: [20, '10m', 800],
  mixed: [50, '15m', 500],
  steady: [50, '30m', 500],
}[mode]
const duration = quick ? '30s' : target[1]
const scenarios = {
  read: {
    executor: 'constant-arrival-rate', exec: 'read', rate: target[0], timeUnit: '1s',
    duration, preAllocatedVUs: 40, maxVUs: 150,
  },
}
if (mode === 'mixed') {
  scenarios.write = {
    executor: 'constant-arrival-rate', exec: 'write', rate: 1, timeUnit: '5s',
    duration, preAllocatedVUs: 1, maxVUs: 2,
  }
}

export const options = {
  scenarios,
  thresholds: {
    'http_req_duration{kind:read}': ['p(95)<' + target[2], ...(mode === 'hot' ? ['p(99)<1000'] : [])],
    http_req_failed: ['rate<0.001'],
    dropped_iterations: ['count==0'],
    unexpected_responses: ['count==0'],
  },
}

const paths = ['/competitions', ...['home', 'teams', 'matches', 'announcements'].map(p => '/competitions/' + hot + '/' + p)]

export function setup() {
  if (mode !== 'mixed') return {}
  const response = http.post(base + '/api/v1/admin/auth/login', JSON.stringify({
    username: __ENV.QUALITY_ADMIN,
    password: __ENV.QUALITY_PASSWORD,
  }), { headers: { Origin: base, 'Content-Type': 'application/json' } })
  if (response.status !== 200 || !__ENV.QUALITY_ANNOUNCEMENT) {
    throw new Error('A synthetic administrator and a synthetic announcement are required for the mixed profile')
  }
  return { csrf: response.json('data.csrf'), session: response.cookies.session[0].value }
}

function observe(response) {
  bad.add(response.status === 200 ? 0 : 1)
  check(response, { 'HTTP 200': r => r.status === 200 })
}

export function read() {
  const path = paths[(__VU + __ITER) % paths.length]
  observe(http.get(base + '/api/v1' + path, { tags: { kind: 'read', name: path }, timeout: '5s' }))
}

export function write(auth) {
  const endpoint = '/admin/announcements/' + __ENV.QUALITY_ANNOUNCEMENT
  const params = {
    headers: { Origin: base, Cookie: 'session=' + auth.session, 'X-CSRF-Token': auth.csrf, 'Content-Type': 'application/json' },
    tags: { kind: 'write', name: 'admin-announcement' },
    timeout: '5s',
  }
  const response = http.get(base + '/api/v1/admin/competitions/' + hot + '/announcements', params)
  observe(response)
  if (response.status !== 200) return
  const row = response.json('data').find(item => item.id === __ENV.QUALITY_ANNOUNCEMENT)
  if (!row) {
    bad.add(1)
    return
  }
  observe(http.patch(base + '/api/v1' + endpoint,
    JSON.stringify({ expected_version: row.version, body: 'Synthetic run ' + Date.now() }), params))
}
