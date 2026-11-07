"""Owner-run expiry cleanup. No external connection without explicit opt-in.

This deletes only rows whose authenticated encrypted expiry has passed. It does
not delete unexpired reports, enlarge quotas or remove provider backup copies.
Run with the same keyring and intended Neon branch as the sandbox service.
"""
import os
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


def main(factory=None):
    if (os.environ.get('SCANPLUS_ENCRYPTED_MAINTENANCE') != '1'
            or os.environ.get('SCANPLUS_RELEASE_PROFILE') != 'sandbox'):
        print('NOT RUN: confirm the sandbox target and explicitly enable encrypted maintenance.')
        return 2
    store = None
    try:
        if factory is None:
            from neon_storage import PostgresEncryptedStore, settings_from_environment
            store = PostgresEncryptedStore(settings_from_environment())
        else:
            store = factory()
        removed = store.prune()
        print('Expired encrypted rows removed: ' + str(removed))
        return 0
    except Exception:
        print('FAILED: encrypted cleanup was not confirmed. Check target and configuration privately.')
        return 1
    finally:
        if store is not None:
            store.close()


if __name__ == '__main__':
    raise SystemExit(main())
