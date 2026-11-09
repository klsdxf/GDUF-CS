#!/usr/bin/env bash
# Read-only deployment verification; no credentials, no insecure TLS fallback.
set -euo pipefail
origin="${1:-https://www.gdufcs.fun}"
redirect="${2:-https://gdufcs.fun}"
tmp="$(mktemp -d)"
trap 'rm -rf "$tmp"' EXIT
curl_args=(--silent --show-error --max-time 15 --connect-timeout 5)
headers() {
  local url="$1" expected="$2"
  local code
  code="$(curl "${curl_args[@]}" -D "$tmp/headers" -o "$tmp/body" -w '%{http_code}' "$url")"
  [[ "$code" == "$expected" ]] || { echo "$url: expected $expected, got $code"; exit 1; }
  for header in x-content-type-options referrer-policy x-frame-options content-security-policy; do
    grep -qi "^$header:" "$tmp/headers" || { echo "Missing $header: $url"; exit 1; }
  done
}
headers "$origin/" 200
cp "$tmp/body" "$tmp/index"
for path in /audit-unknown-path /matches/audit-missing-id /competitions/audit-missing/schedule /missing-audit.css; do
  headers "$origin$path" 404
  [[ "$(curl "${curl_args[@]}" -I -o /dev/null -w '%{http_code}' "$origin$path")" == 404 ]]
done
for spec in 'robots.txt text/plain' 'sitemap.xml xml' 'favicon.svg image/svg+xml'; do
  read -r path mime <<< "$spec"
  headers "$origin/$path" 200
  grep -qi "^content-type:.*$mime" "$tmp/headers"
done
# Discover current build assets, including split stylesheet URLs from the entry JS.
grep -oE '(src|href)="/assets/[^"]+\.(js|css)"' "$tmp/index" | cut -d '"' -f 2 > "$tmp/assets"
entry="$(grep '\.js$' "$tmp/assets" | head -1)"
curl "${curl_args[@]}" "$origin$entry" > "$tmp/entry"
grep -oE 'assets/[^" ]+\.css' "$tmp/entry" | sed 's|^|/|' >> "$tmp/assets" || true
while read -r path; do
  headers "$origin$path" 200
  curl "${curl_args[@]}" -H 'Accept-Encoding: gzip' -D "$tmp/encoding" -o /dev/null -w "$path transfer=%{size_download}\n" "$origin$path"
  grep -qi '^content-encoding: gzip' "$tmp/encoding"
done < "$tmp/assets"
headers "$redirect/competitions/autumn/schedule?date=2026-11-14" 301
tr -d '\r' < "$tmp/headers" | grep -qiFx "Location: $origin/competitions/autumn/schedule?date=2026-11-14"
if curl -V | grep -q HTTP2; then
  [[ "$(curl "${curl_args[@]}" --http2 -o /dev/null -w '%{http_version}' "$origin/")" == 2 ]]
else
  echo 'HTTP/2 未验证：当前 curl 不支持 HTTP2' >&2
  exit 2
fi
echo 'Deployment audit smoke passed'
