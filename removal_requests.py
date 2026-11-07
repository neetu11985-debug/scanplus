"""Per-listing permission boundary for the local synthetic removal adapter.

No network transport, provider URLs, personal-data input or live enable switch.
Do not wire a live adapter into the surrounding SQLite request transaction: a
production integration needs a durable outbox and provider reconciliation first.
"""
from copy import deepcopy
from hashlib import sha256
import json
import re
import secrets
import time

from providers import FixtureRemoval

CONSENT_VERSION = 'removal-consent-v1'
CONSENT_TTL = 300
FIXTURE_PHONES = ('+12025550147', '+12025550148')


class RemovalError(ValueError):
    def __init__(self, message, status=400):
        super().__init__(message)
        self.status = status


def fixture_listing(session):
    """Only a server-owned report can select this reserved fixture."""
    report_id = session['report_id']
    return {'provider': 'fixture', 'report_id': report_id,
            'listing_id': sha256(('fixture\n' + report_id).encode()).hexdigest()[:24],
            'label': 'Fictional example listing', 'synthetic': True}


def _checked_listing(session, data):
    if data.get('provider') != 'fixture':
        raise RemovalError('No supported, permitted live removal API is configured. Use the official guide.', 409)
    listing = fixture_listing(session)
    if any(data.get(key) != listing[key] for key in ('report_id', 'listing_id')):
        raise RemovalError('This listing is not in the current report. Reload the report.', 409)
    if not any(sha256(phone.encode()).hexdigest() == session.get('phone_ref') for phone in FIXTURE_PHONES):
        raise RemovalError('Only reserved synthetic identities are supported.', 409)
    return listing


def _keys(data, allowed):
    if set(data) - set(allowed):
        raise RemovalError('Unexpected removal fields. Personal data and provider destinations are not accepted.')


def _disclosure(session):
    listing = fixture_listing(session)
    phone = next(phone for phone in FIXTURE_PHONES
                 if sha256(phone.encode()).hexdigest() == session['phone_ref'])
    return {**listing, 'consent_version': CONSENT_VERSION,
            'recipient': 'ScanPlus local synthetic adapter (no external recipient)',
            'purpose': 'Simulate a request to remove this one fictional listing.',
            'data': [{'label': 'Reserved example phone', 'value': phone},
                     {'label': 'Fictional listing ID', 'value': listing['listing_id']}],
            'scope': 'This listing only. No other listings or future requests are authorized.',
            'consequences': 'No broker is contacted and nothing is removed. A real submission would share the displayed data with the named recipient and might require its verification. Submission is not proof of removal.',
            'retention': 'Synthetic permission and request records expire with this demo session. Clearing the session deletes them. This is not a production audit trail.',
            'cost': 'No charge; no subscription.',
            'cancellation': 'Cancel before submitting to discard this permission screen. A submitted request cannot be unsent.'}


def _fingerprint(disclosure):
    return sha256(json.dumps(disclosure, sort_keys=True, separators=(',', ':')).encode()).hexdigest()


def public_request(session):
    record = session.get('removal_request')
    if not record:
        return None
    return {key: deepcopy(record[key]) for key in
            ('request_id', 'listing_id', 'status', 'submitted_at', 'demo',
             'receipt', 'removal_verified', 'message')}


def prepare(session, data, now=None):
    _keys(data, ('provider', 'report_id', 'listing_id'))
    _checked_listing(session, data)
    if session.get('removal_request'):
        return {'demo': True, 'request': public_request(session)}
    now = time.time() if now is None else now
    disclosure = _disclosure(session)
    # Opening another review invalidates the previous review (including old tabs).
    preview = {'consent_id': secrets.token_urlsafe(32),
               'expires_at': min(now + CONSENT_TTL, session['expires']),
               'disclosure_hash': _fingerprint(disclosure), 'disclosure': disclosure}
    session['removal_preview'] = preview
    return {'demo': True, **deepcopy(preview)}


def cancel(session, data):
    _keys(data, ('consent_id',))
    if session.get('removal_request'):
        raise RemovalError('A request was already recorded and cannot be unsent. Reload to check its status.', 409)
    preview = session.get('removal_preview')
    if preview and data.get('consent_id') == preview['consent_id']:
        session.pop('removal_preview', None)
    return {'demo': True, 'cancelled': True}


def submit(session, data, now=None):
    _keys(data, ('provider', 'report_id', 'listing_id', 'consent_id',
                 'consent_version', 'authorize', 'confirm_listing'))
    _checked_listing(session, data)
    if data.get('authorize') is not True or data.get('confirm_listing') is not True:
        raise RemovalError('Confirm the exact listing and explicitly authorize the displayed data and recipient.')
    if data.get('consent_version') != CONSENT_VERSION:
        raise RemovalError('Review the current permission screen before submitting.', 409)
    token = data.get('consent_id')
    if not isinstance(token, str) or not re.fullmatch(r'[A-Za-z0-9_-]{20,128}', token):
        raise RemovalError('Review the permission screen before submitting.', 409)
    existing = session.get('removal_request')
    if existing:
        if not secrets.compare_digest(sha256(token.encode()).hexdigest(), existing['consent_hash']):
            raise RemovalError('A request already exists. Reload to check its status.', 409)
        # A network retry returns the original receipt, never invokes the adapter.
        return public_request(session)
    now = time.time() if now is None else now
    preview = session.get('removal_preview')
    if (not preview or preview['expires_at'] <= now or
            not secrets.compare_digest(token, preview['consent_id']) or
            preview['disclosure_hash'] != _fingerprint(_disclosure(session))):
        raise RemovalError('Permission expired or changed. Review this listing again.', 409)
    request_id = 'fixture-' + sha256((session['report_id'] + '\n' + data['listing_id']).encode()).hexdigest()[:32]
    record = {'request_id': request_id, 'listing_id': data['listing_id'],
              'consent_hash': sha256(token.encode()).hexdigest(),
              'consent_version': CONSENT_VERSION, 'consented_at': now,
              'disclosure': deepcopy(preview['disclosure']), 'submitted_at': None,
              'status': 'outcome_unknown', 'demo': True, 'receipt': None,
              'removal_verified': False,
              'message': 'Simulation outcome is uncertain. Do not resubmit; check this request first.'}
    session['removal_request'] = record
    session.pop('removal_preview', None)
    try:
        result = FixtureRemoval().submit('fixture', True, request_id=request_id,
                                         listing_id=data['listing_id'],
                                         payload={'phone':preview['disclosure']['data'][0]['value'],
                                                  'listing_id':data['listing_id']})
        # Never trust a submitted receipt as evidence that the listing is gone.
        if (result.get('demo') is not True or result.get('status') != 'request_submitted' or
                result.get('receipt') != request_id):
            raise ValueError('Unrecognized synthetic receipt.')
        record.update(status='request_submitted', submitted_at=now, receipt=result['receipt'],
                      message='Synthetic request recorded locally. No broker was contacted; no removal was verified.')
    except Exception:
        # No exception details, personal data or credentials reach the caller.
        # Unknown outcomes are not automatically retried.
        pass
    session['removal'] = record['status']
    return public_request(session)


def status(session, data):
    _keys(data, ('request_id',))
    record = session.get('removal_request')
    if not record or data.get('request_id') != record['request_id']:
        raise RemovalError('Removal request not found in this session.', 404)
    # Read-only status. Polling, elapsed time and missing index results are not
    # removal evidence. There is deliberately no browser-set completion route.
    return public_request(session)
