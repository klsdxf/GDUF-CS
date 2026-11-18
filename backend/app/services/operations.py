"""Store successful command results within the transaction that applies the command."""
import hashlib
import json

from fastapi.encoders import jsonable_encoder

from ..db import OperationReceipt
from ..security import fail


def digest(value):
    return hashlib.sha256(json.dumps(jsonable_encoder(value), sort_keys=True,
                                     separators=(',', ':'), ensure_ascii=False).encode()).hexdigest()


def receipt(db, action, target, token, payload):
    if not token or not token.strip() or len(token) > 128:
        fail('IDEMPOTENCY', '操作键必须为 1 至 128 字符')
    identity = (1, action, target, digest(token))
    request_hash = digest(payload)
    existing = db.get(OperationReceipt, identity)
    if existing and existing.request_hash != request_hash:
        fail('IDEMPOTENCY_CONFLICT', '该操作键已用于其他请求', 409)
    return identity, request_hash, existing


def record(db, identity, request_hash, response):
    actor_id, action, target, key_hash = identity
    db.add(OperationReceipt(actor_id=actor_id, action=action, resource_id=target, key_hash=key_hash,
                            request_hash=request_hash, response_body=jsonable_encoder(response)))
    return response


def command(db, action, target, token, payload, apply):
    identity, request_hash, existing = receipt(db, action, target, token, payload)
    if existing:
        return existing.response_body
    return record(db, identity, request_hash, apply())
