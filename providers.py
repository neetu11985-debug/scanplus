"""Provider contracts. No adapter in this MVP makes outbound requests."""
from dataclasses import dataclass
from typing import Protocol

@dataclass(frozen=True)
class Provider:
    id: str
    name: str
    url: str
    steps: tuple[str, ...]
    verified: bool = False
    automation: bool = False

CATALOG = [
    Provider('spokeo', 'Spokeo', 'https://www.spokeo.com/optout', (
        'Open Spokeo’s official opt-out page.',
        'Follow its current instructions to identify your own listing and complete any required verification.',
        'Save the confirmation and check the listing again after Spokeo’s stated processing period.',
        'If the form fails, use the contact options at https://www.spokeo.com/contact.')),
    Provider('whitepages', 'Whitepages', 'https://www.whitepages.com/privacy/consumer-rights', (
        'Open Whitepages’ official Consumer Privacy Rights page.',
        'Choose its current listing-removal or opt-out option.',
        'Supply only what is required to identify your own listing and complete the displayed verification.',
        'Save the confirmation and follow the page’s instructions if the listing remains.')),
    Provider('truepeople', 'TruePeopleSearch', 'https://www.truepeoplesearch.com/privacy', (
        'Open TruePeopleSearch’s official privacy page.',
        'Follow the current opt-out instructions or the site footer’s Do Not Sell My Personal Information link.',
        'Complete the displayed identification and verification steps for your own record.',
        'Save the confirmation and check again after the site’s stated processing period.')),
]


class DiscoveryAdapter(Protocol):
    def discover(self) -> list[dict]: ...

class RemovalAdapter(Protocol):
    def submit(self, provider_id: str, authorized: bool) -> dict: ...

class FixtureDiscovery:
    def discover(self):
        return [dict(id=p.id, name=p.name, url=p.url, steps=p.steps,
                     status='example_listing' if i < 2 else 'not_checked',
                     source_url=None, link_verified=p.verified, automation=p.automation)
                for i, p in enumerate(CATALOG)]

class DisabledRemoval:
    def submit(self, provider_id, authorized):
        if not authorized:
            raise ValueError('Explicit authorization is required.')
        raise ValueError('Live removal integrations are disabled. Use official guided actions.')

class FixtureRemoval:
    """Only a synthetic provider exercises automatic submission and polling."""
    def submit(self, provider_id, authorized):
        if provider_id != 'fixture' or not authorized:
            raise ValueError('Only the authorized synthetic provider is supported.')
        return {'status': 'request_submitted', 'demo': True}
