"""Separate, explicitly enabled owner-only Stripe TEST integration entrypoint."""
from hosted_owner_checkout import OwnerCheckoutApplication, checkout_configuration

application = OwnerCheckoutApplication(checkout_configuration())
