"""Allowlisted search diagnostics only. Never retain or format exception text."""
import http.client
import json
import socket
import ssl

SEARCH_DIAGNOSTICS = {
    'timeout': 'The provider request timed out.',
    'dns_error': 'The provider hostname could not be resolved.',
    'tls_certificate_error': 'TLS certificate verification failed.',
    'tls_error': 'A secure TLS connection could not be completed.',
    'network_permission_denied': 'A permission restriction denied the network operation.',
    'connection_refused': 'The connection was refused.',
    'connection_closed': 'The connection closed before a usable response arrived.',
    'network_error': 'A network operation failed.',
    'http_protocol_error': 'The HTTP response could not be read correctly.',
    'response_incomplete': 'The provider response was incomplete.',
    'response_too_large': 'The provider response exceeded the size limit.',
    'invalid_json': 'The provider response was not valid JSON.',
    'invalid_response': 'The provider response did not have the expected structure.',
    'http_error': 'The provider returned an unusable HTTP status.',
    'not_dispatched': 'The query was not sent because an allowance or safety gate blocked it.',
    'not_attempted_after_provider_error': 'The query was not attempted after an earlier provider failure.',
    'transport_error': 'The request failed for an unclassified transport reason.',
}
NOT_DISPATCHED = frozenset(('not_dispatched', 'not_attempted_after_provider_error'))


def search_diagnostic(category, http_status=None):
    category = category if isinstance(category, str) and category in SEARCH_DIAGNOSTICS else 'transport_error'
    status = http_status if type(http_status) is int and 100 <= http_status <= 599 else None
    return {'category': category, 'http_status': status}


class SearchTransportFailure(Exception):
    def __init__(self, category, http_status=None):
        diagnostic = search_diagnostic(category, http_status)
        self.category = diagnostic['category']
        self.http_status = diagnostic['http_status']
        super().__init__('A provider request failed. See the safe diagnostic category.')


def diagnose_search_exception(error, http_status=None):
    if isinstance(error, SearchTransportFailure):
        return search_diagnostic(error.category, error.http_status if http_status is None else http_status)
    categories = ((ssl.SSLCertVerificationError, 'tls_certificate_error'),
                  (ssl.SSLError, 'tls_error'), (socket.gaierror, 'dns_error'),
                  (TimeoutError, 'timeout'), (PermissionError, 'network_permission_denied'),
                  (ConnectionRefusedError, 'connection_refused'),
                  ((ConnectionResetError, ConnectionAbortedError, BrokenPipeError), 'connection_closed'),
                  (http.client.IncompleteRead, 'response_incomplete'),
                  (http.client.HTTPException, 'http_protocol_error'),
                  ((json.JSONDecodeError, UnicodeDecodeError), 'invalid_json'),
                  (OSError, 'network_error'))
    category = next((category for kind, category in categories if isinstance(error, kind)), 'transport_error')
    return search_diagnostic(category, http_status)


def search_diagnostic_text(diagnostic):
    if not isinstance(diagnostic, dict):
        return ''
    safe = search_diagnostic(diagnostic.get('category'), diagnostic.get('http_status'))
    status = str(safe['http_status']) if safe['http_status'] is not None else 'status unavailable'
    return 'Search diagnostic: ' + SEARCH_DIAGNOSTICS[safe['category']] + ' HTTP ' + status + '. No automatic retry occurred.'
