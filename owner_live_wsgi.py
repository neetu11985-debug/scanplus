"""Separate opt-in entrypoint. Existing render_wsgi demo deployment is unchanged."""
from hosted_self_test import OwnerTestApplication, configuration

application = OwnerTestApplication(configuration())
