"""Separate sandbox routes: demo checkout cannot unlock a Stripe test report."""
import time
from stripe_checkout import StripeCheckout, StripeError
from providers import FixtureDiscovery
from scan_report_pdf import demo_report_pdf
from encrypted_storage import SecureStorageError
import secure_reports

class StripeRoutes:
    def stripe_webhook(self, store):
        try:
            if self.headers.get('Transfer-Encoding'):
                raise ValueError()
            n = int(self.headers.get('Content-Length', '0'))
            if not 0 < n <= 65536:
                raise ValueError()
            raw = self.rfile.read(n)
            if len(raw) != n:
                raise ValueError()
            result = StripeCheckout(store).webhook(raw, self.headers.get('Stripe-Signature', ''))
            return self.reply(200, result)
        except (ValueError, TypeError):
            return self.reply(400, {'error': 'Stripe test webhook rejected.'})

    def stripe_get(self, store):
        if self.headers.get('Origin') not in (None, self.origin()):
            return self.reply(403, {'error': 'Same-origin request required.'})
        s = self.session()
        if not s or not s['verified'] or s['verified_until'] <= time.time():
            return self.reply(403, {'error': 'Current synthetic verification required.'})
        if not store.allow('session:' + self.sid, 60):
            return self.reply(429, {'error': 'Too many requests.'})
        try:
            gateway = StripeCheckout(store)
            status = gateway.status(self.sid, s)
            if self.path == '/api/stripe/status':
                return self.reply(200, status)
            if status['state'] != 'paid':
                return self.reply(403, {'error': 'Server-verified Stripe sandbox payment required.'})
            if self.path == '/api/stripe/report/download':
                text = secure_reports.REPORTS.download(self.sid, s, gateway.order(self.sid))
                if text is None:
                    return self.reply(404, {'error': 'Report unavailable. Save the paid report first.'})
                report = secure_reports.pdf_bundle(text, gateway.order(self.sid)['encrypted_report_id'])
                raw = demo_report_pdf(report)
                # Rendering must not carry an expired/revoked owner or stored
                # report across the authorization boundary into the download.
                current = self.session()
                if not current or not current['verified'] or current['verified_until'] <= time.time():
                    return self.reply(403, {'error': 'Current synthetic verification required.'})
                current_order = gateway.order(self.sid)
                current_text = secure_reports.REPORTS.download(self.sid, current, current_order)
                if current_text is None:
                    return self.reply(404, {'error': 'Report unavailable. Save the paid report first.'})
                if current_order.get('encrypted_report_id') != report['report_id'] or current_text != text:
                    raise SecureStorageError('Saved report changed during rendering.')
                self.send_response(200); self.headers_common()
                self.send_header('Content-Type', 'application/pdf')
                self.send_header('Content-Disposition', 'attachment; filename="scanplus-sandbox-report.pdf"')
                self.send_header('Content-Length', str(len(raw)))
                self.end_headers(); self.wfile.write(raw)
                return
            return self.reply(200, {'demo': True, 'test_mode': True, 'report_id': s['report_id'],
                                    'providers': FixtureDiscovery().discover(), 'live_sources_checked': 0,
                                    'encrypted_storage_available': secure_reports.enabled()})
        except StripeError as e:
            return self.reply(503, {'error': str(e)})
        except SecureStorageError:
            return self.reply(503, {'error': 'Encrypted report unavailable. Payment was not repeated.'})

    def stripe_post(self, store, session, data):
        try:
            gateway = StripeCheckout(store)
            if self.path == '/api/stripe/checkout':
                if data.get('accept_test') is not True:
                    raise StripeError('Confirm sandbox-only Checkout. Never enter real payment details.')
                if set(data) != {'accept_test'}:
                    raise StripeError('Checkout price and order are server-controlled; no extra fields accepted.')
                result = gateway.create(self.sid, session)
            elif self.path == '/api/stripe/reconcile':
                if data:
                    raise StripeError('No payment or owner overrides are accepted.')
                result = gateway.reconcile(self.sid)
            elif self.path == '/api/stripe/report/save':
                if data != {'confirm_synthetic': True}:
                    raise StripeError('Confirm synthetic encrypted report storage; no extra fields accepted.')
                order = gateway.order(self.sid)
                if not order or order.get('state') != 'paid':
                    return self.reply(402, {'error': 'Reconcile the Stripe sandbox payment before saving.'})
                result = secure_reports.REPORTS.fulfill(self.sid, session, order)
                order['encrypted_report_id'] = result['report_id']
                gateway.save(order)
            else:
                return self.reply(404, {'error': 'Endpoint not found.'})
            return self.reply(200, result)
        except StripeError as e:
            # Commit any pending order reservation even if the remote result is uncertain.
            return self.reply(400, {'error': str(e)})
        except SecureStorageError:
            return self.reply(503, {'error': 'Encrypted delivery was not confirmed. Retry Save report using this session; do not pay again.'})
