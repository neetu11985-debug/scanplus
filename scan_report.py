"""Memory-only report and manual action guidance. Never contacts a broker.

Official destinations are confirmed in broker filings in the California registry;
current form workflows have not been independently verified. No adapter in this report grants permission to submit removals.
"""
from copy import deepcopy
from datetime import datetime, timezone
from hashlib import sha256
from uuid import uuid4
from providers import CATALOG
from search_diagnostics import search_diagnostic_text

SITE_IDS = {'spokeo.com': 'spokeo', 'whitepages.com': 'whitepages', 'truepeoplesearch.com': 'truepeople'}
GUIDE_NOTICE = ('Current page workflow has not been independently verified. Follow the site’s current '
                'official instructions. Self-service requests are normally free; do not buy a paid lookup to follow this guide.')
AUTOMATION_NOTICE = ('No supported, permitted automatic removal integration is configured for this site. '
                     'ScanPlus will not submit a removal or claim it was completed.')
SAFETY_NOTICE = ('Current phone control does not prove a listing belongs to you. Confirm the record first; '
                 'do not request deletion of someone else’s data. Complete CAPTCHA, email, phone and identity checks yourself.')


def removal_guide(site):
    provider = next((p for p in CATALOG if p.id == SITE_IDS.get(site)), None)
    if provider is None:
        raise ValueError('Unsupported report source.')
    return {'name': provider.name, 'url': provider.url, 'steps': list(provider.steps),
            'destination_verification': 'primary_registry_confirmed',
            'source_url': 'https://cppa.ca.gov/data_broker_registry/registry.csv',
            'registry_updated': '2026-10-30', 'reviewed_at': '2026-11-06',
            'registry_broker_id': {'spokeo.com': '1361', 'whitepages.com': '1170', 'truepeoplesearch.com': '1346'}[site],
            'workflow_verification': 'not_verified', 'verification_notice': GUIDE_NOTICE,
            'automation_supported': False, 'automation_notice': AUTOMATION_NOTICE,
            'safety_notice': SAFETY_NOTICE,
            'follow_up': 'Save any site confirmation privately. After the processing period stated by the site, revisit the exact listing yourself. A request receipt or missing search result is not proof of removal.'}


def build_report(sources, provider, last_four):
    report_id = str(uuid4())
    sources = deepcopy(sources)
    for source in sources:
        source['guide'] = removal_guide(source['site'])
        for candidate in source['candidates']:
            candidate['id'] = sha256((report_id + '\n' + source['site'] + '\n' + candidate['source_url']).encode()).hexdigest()[:24]
            candidate['match_review'] = 'needs_confirmation'
            candidate['manual_action'] = 'not_started'
            candidate['removal_eligible'] = False
            candidate['removal_verified'] = False
    return {'schema_version': 1, 'report_id': report_id, 'live': True,
            'created_at': datetime.now(timezone.utc).isoformat(), 'last_four': last_four,
            'search_provider': provider, 'sources': sources,
            'sources_checked': sum(s['status'] != 'source_unavailable' for s in sources),
            'coverage': ('At most three bounded ' + ('Serper Google Search' if provider == 'serper' else 'Brave') +
                ' web-index queries, up to 10 results each. This is not a direct broker database search or a full Internet scan. '
                'A missing result does not mean the number is absent online. Indexed results can be stale.'),
            'removal_notice': 'No removal was submitted or verified by ScanPlus. Manual progress is only your own checklist, not independent evidence.',
            'privacy_notice': 'This report may contain personal information in listing URLs. Save it only where you intend. Downloads remain on your device after this session is cleared or expires.',
            'payment_notice': 'No checkout or payment is part of this local self-test.'}


def update_manual_action(report, candidate_id, action):
    if not isinstance(candidate_id, str) or action not in ('confirm_mine', 'not_mine', 'reset', 'record_manual_request'):
        raise ValueError('Choose a supported listing review action.')
    candidate = next((c for s in report['sources'] for c in s['candidates'] if c['id'] == candidate_id), None)
    if candidate is None:
        raise ValueError('Listing is not in this session’s report.')
    if action == 'record_manual_request':
        if candidate['match_review'] != 'confirmed_by_user':
            raise ValueError('Confirm this listing is yours before recording a manual request.')
        candidate['manual_action'] = 'user_recorded_request'
    elif action != 'confirm_mine' or candidate['match_review'] != 'confirmed_by_user':
        candidate['match_review'] = {'confirm_mine': 'confirmed_by_user', 'not_mine': 'not_mine', 'reset': 'needs_confirmation'}[action]
        candidate['manual_action'] = 'not_started'
    candidate['removal_eligible'] = False
    candidate['removal_verified'] = False


def report_text(report):
    labels = {'match_needs_confirmation': 'Potential match: confirmation needed',
              'not_found_in_checked_sources': 'No exact phone match in checked index results',
              'source_unavailable': 'Source unavailable: no absence conclusion'}
    lines = ['SCANPLUS PRIVATE SELF-TEST REPORT' if report.get('test_scope') == 'private_owner' else 'SCANPLUS LOCAL SEARCH REPORT', 'Report: ' + report['report_id'],
             'Created: ' + report['created_at'], 'Number ending: ' + str(report['last_four']),
             'Search provider: ' + report['search_provider'],
             str(report['sources_checked']) + ' of ' + str(len(report['sources'])) + ' source queries returned usable responses.',
             '', report['coverage'], report['removal_notice'], report['payment_notice'], '', report['privacy_notice']]
    for source in report['sources']:
        guide = source['guide']
        lines += ['', guide['name'] + ' (' + source['site'] + ')', labels[source['status']],
                  'Query not attempted' if source.get('query_attempted') is False else 'Checked: ' + source['checked_at']]
        diagnostic = search_diagnostic_text(source.get('search_diagnostic'))
        if diagnostic: lines.append(diagnostic)
        if source.get('reason'): lines.append('Reason: ' + source['reason'].replace('_', ' '))
        for index, candidate in enumerate(source['candidates'], 1):
            lines += ['', 'Listing ' + str(index) + ': ' + candidate['source_url'], candidate['evidence'],
                      'Your review: ' + candidate['match_review'].replace('_', ' '),
                      'Your checklist: ' + candidate['manual_action'].replace('_', ' '),
                      'Removal verified by ScanPlus: no']
        lines += ['', 'Official manual path (workflow not verified): ' + guide['url'], guide['verification_notice'],
                  'Destination evidence: California Data Broker Registry, updated ' + guide['registry_updated'] + ' (broker ' + guide['registry_broker_id'] + '). ' + guide['source_url'], guide['safety_notice']]
        lines += [str(index) + '. ' + step for index, step in enumerate(guide['steps'], 1)]
        lines += [guide['follow_up'], guide['automation_notice']]
    return '\n'.join(lines) + '\n'
