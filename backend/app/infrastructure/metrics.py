"""Small, per-process Prometheus exposition for the internal network."""
from collections import Counter
import json
from threading import Lock

lock = Lock()
requests = Counter()
elapsed = Counter()
histogram = Counter()
events = Counter()
BUCKETS = (0.05, 0.1, 0.2, 0.3, 0.5, 0.8, 1, 2, 5)


def request_observed(route, status, duration):
    with lock:
        requests[(route, status)] += 1
        elapsed[route] += duration
        for bucket in BUCKETS:
            if duration <= bucket:
                histogram[(route, bucket)] += 1


def event(name):
    with lock:
        events[name] += 1


def exposition():
    with lock:
        lines = [f'gduf_http_requests_total{{route={json.dumps(route)},status="{status}"}} {count}'
                 for (route, status), count in sorted(requests.items())]
        lines += [f'gduf_events_total{{event="{name}"}} {count}' for name, count in sorted(events.items())]
        lines.append('# TYPE gduf_http_request_duration_seconds histogram')
        for route, duration in sorted(elapsed.items()):
            label = json.dumps(route)
            count = sum(n for (r, _), n in requests.items() if r == route)
            lines.extend(f'gduf_http_request_duration_seconds_bucket{{route={label},le="{b}"}} {histogram[(route, b)]}'
                         for b in BUCKETS)
            lines.extend([f'gduf_http_request_duration_seconds_bucket{{route={label},le="+Inf"}} {count}',
                          f'gduf_http_request_duration_seconds_sum{{route={label}}} {duration}',
                          f'gduf_http_request_duration_seconds_count{{route={label}}} {count}'])
        return lines
