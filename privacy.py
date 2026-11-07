"""Allowlisted diagnostics. Never render exception/request payloads into logs."""
EVENTS=frozenset({'request_rejected','provider_unavailable','storage_unavailable'})
def safe_event(event,**fields):
    result={'event':event if event in EVENTS else 'request_rejected'}
    if type(fields.get('status')) is int and 100<=fields['status']<=599: result['status']=fields['status']
    if fields.get('reason') in ('timeout','throttled','invalid_request','unavailable'):
        result['reason']=fields['reason']
    return result
