"""
Mobile money providers.

Each provider has two operations:
    start(payment)  -> ProviderResult   ask the customer's phone to approve the payment
    check(payment)  -> ProviderResult   ask the provider for the payment's current status

The rest of the app never talks to a provider directly, so a different
aggregator can be added later by writing one more class here.
"""
import logging
from dataclasses import dataclass, field

import requests
from django.conf import settings

from .networks import NETWORKS

logger = logging.getLogger(__name__)

PENDING, COMPLETED, FAILED = 'pending', 'completed', 'failed'


@dataclass
class ProviderResult:
    state: str                      # pending / completed / failed
    provider_status: str = ''
    reference: str = ''
    failure_code: str = ''
    failure_message: str = ''
    raw: dict = field(default_factory=dict)
    # True when the provider could not be reached or answered with an error we
    # cannot interpret. The payment stays pending and is checked again later.
    uncertain: bool = False


class ProviderError(Exception):
    pass


FRIENDLY_FAILURES = {
    'PAYER_NOT_FOUND': 'This number is not registered for mobile money on the network you chose.',
    'PAYMENT_NOT_APPROVED': 'The payment was not approved on the phone, or the prompt timed out.',
    'PAYER_LIMIT_REACHED': 'This wallet has reached its transaction limit.',
    'WALLET_LIMIT_REACHED': 'This wallet has reached its transaction limit.',
    'INSUFFICIENT_BALANCE': 'There was not enough money in the wallet.',
    'PAYMENT_IN_PROGRESS': 'Another payment is already waiting on this phone. Finish or cancel it first.',
    'INVALID_PHONE_NUMBER': 'That phone number is not valid for the network you chose.',
    'PROVIDER_TEMPORARILY_UNAVAILABLE': 'The mobile money network is temporarily unavailable. Please try again shortly.',
    'INVALID_PROVIDER': 'That network is not available right now.',
    'AMOUNT_OUT_OF_BOUNDS': 'This amount is outside what the network allows.',
}


def friendly_failure(code, fallback=''):
    return FRIENDLY_FAILURES.get(code) or fallback or 'The payment could not be completed. Please try again.'


class SimulatorProvider:
    """
    For development and demos only: no money moves.

    The payment stays pending until someone presses "Approve" or "Decline" on
    the simulator panel of the payment status page, which stands in for the
    prompt a real customer gets on their phone. Numbers ending in 13 are
    rejected straight away, so the failure path can be tried too.
    """
    name = 'simulator'

    def start(self, payment):
        if payment.msisdn.endswith('13'):
            return ProviderResult(FAILED, 'REJECTED', failure_code='PAYER_NOT_FOUND',
                                  failure_message=friendly_failure('PAYER_NOT_FOUND'))
        return ProviderResult(PENDING, 'ACCEPTED', reference=f'SIM-{payment.id.hex[:10]}')

    def check(self, payment):
        return ProviderResult(PENDING, payment.provider_status or 'ACCEPTED')

    def payout(self, payout):
        return ProviderResult(COMPLETED, 'COMPLETED', reference=f'SIMPAY-{payout.id.hex[:10]}')

    def check_payout(self, payout):
        return ProviderResult(COMPLETED, 'COMPLETED', reference=payout.provider_reference)


class PawaPayProvider:
    """
    pawaPay v2 deposits: one contract for MTN, Airtel and Zamtel in Zambia.
    Docs: https://docs.pawapay.io/v2/api-reference
    """
    name = 'pawapay'
    timeout = 20

    def __init__(self, token=None, base_url=None):
        self.token = token or settings.PAWAPAY_API_TOKEN
        self.base_url = (base_url or settings.PAWAPAY_BASE_URL).rstrip('/')

    def _headers(self):
        return {'Authorization': f'Bearer {self.token}', 'Content-Type': 'application/json'}

    def start(self, payment):
        body = {
            'depositId': str(payment.id),
            'amount': f'{payment.amount:.2f}',
            'currency': payment.currency,
            'payer': {
                'type': 'MMO',
                'accountDetails': {
                    'phoneNumber': payment.msisdn,
                    'provider': NETWORKS[payment.network]['pawapay'],
                },
            },
            'customerMessage': 'Catch Up course',
            'clientReferenceId': payment.reference,
            'metadata': [{'courseId': str(payment.course_id)}, {'userId': str(payment.user_id)}],
        }
        try:
            resp = requests.post(f'{self.base_url}/v2/deposits', json=body, headers=self._headers(),
                                 timeout=self.timeout)
        except requests.RequestException as exc:
            # We do not know whether pawaPay received it. The deposit id makes a
            # retry safe, and the status check settles it.
            logger.warning('pawaPay deposit request failed for %s: %s', payment.id, exc)
            return ProviderResult(PENDING, 'UNREACHABLE', uncertain=True, raw={'error': str(exc)})

        data = _json(resp)
        status = data.get('status', '')
        reason = data.get('failureReason') or {}
        if resp.status_code >= 500:
            # The docs say a 5xx is not a failure: check the status before deciding.
            return ProviderResult(PENDING, f'HTTP_{resp.status_code}', uncertain=True, raw=data)
        if status in ('ACCEPTED', 'DUPLICATE_IGNORED'):
            return ProviderResult(PENDING, status, raw=data)
        if status == 'REJECTED' or resp.status_code >= 400:
            code = reason.get('failureCode', f'HTTP_{resp.status_code}')
            if code in ('NO_AUTHENTICATION', 'AUTHENTICATION_ERROR', 'AUTHORISATION_ERROR', 'DEPOSITS_NOT_ALLOWED'):
                logger.error('pawaPay refused our credentials (%s). Check PAWAPAY_API_TOKEN.', code)
            return ProviderResult(FAILED, 'REJECTED', failure_code=code,
                                  failure_message=friendly_failure(code, reason.get('failureMessage', '')),
                                  raw=data)
        return ProviderResult(PENDING, status or f'HTTP_{resp.status_code}', uncertain=True, raw=data)

    def payout(self, payout):
        """Send a tutor's earnings to their mobile money wallet."""
        body = {
            'payoutId': str(payout.id),
            'amount': f'{payout.amount:.2f}',
            'currency': 'ZMW',
            'recipient': {'type': 'MMO', 'accountDetails': {
                'phoneNumber': payout.msisdn, 'provider': NETWORKS[payout.network]['pawapay']}},
            'customerMessage': 'Catch Up earnings',
        }
        try:
            resp = requests.post(f'{self.base_url}/v2/payouts', json=body, headers=self._headers(),
                                 timeout=self.timeout)
        except requests.RequestException as exc:
            return ProviderResult(PENDING, 'UNREACHABLE', uncertain=True, raw={'error': str(exc)})
        data = _json(resp)
        status = data.get('status', '')
        if resp.status_code < 500 and status in ('ACCEPTED', 'DUPLICATE_IGNORED', 'ENQUEUED'):
            return ProviderResult(PENDING, status, raw=data)
        if status == 'REJECTED' or 400 <= resp.status_code < 500:
            reason = data.get('failureReason') or {}
            code = reason.get('failureCode', f'HTTP_{resp.status_code}')
            return ProviderResult(FAILED, 'REJECTED', failure_code=code,
                                  failure_message=reason.get('failureMessage', '') or code, raw=data)
        return ProviderResult(PENDING, status or f'HTTP_{resp.status_code}', uncertain=True, raw=data)

    def check_payout(self, payout):
        try:
            resp = requests.get(f'{self.base_url}/v2/payouts/{payout.id}', headers=self._headers(),
                                timeout=self.timeout)
        except requests.RequestException as exc:
            return ProviderResult(PENDING, payout.provider_status, uncertain=True, raw={'error': str(exc)})
        data = _json(resp)
        item = data.get('data') or {}
        status = item.get('status', '')
        if status == 'COMPLETED':
            return ProviderResult(COMPLETED, status, reference=item.get('providerTransactionId', ''), raw=data)
        if status == 'FAILED':
            reason = item.get('failureReason') or {}
            return ProviderResult(FAILED, status, failure_code=reason.get('failureCode', 'UNKNOWN_ERROR'),
                                  failure_message=reason.get('failureMessage', ''), raw=data)
        return ProviderResult(PENDING, status or payout.provider_status, raw=data)

    def check(self, payment):
        try:
            resp = requests.get(f'{self.base_url}/v2/deposits/{payment.id}', headers=self._headers(),
                                timeout=self.timeout)
        except requests.RequestException as exc:
            logger.warning('pawaPay status check failed for %s: %s', payment.id, exc)
            return ProviderResult(PENDING, payment.provider_status, uncertain=True, raw={'error': str(exc)})
        data = _json(resp)
        if resp.status_code != 200:
            return ProviderResult(PENDING, payment.provider_status, uncertain=True, raw=data)
        if data.get('status') == 'NOT_FOUND':
            return ProviderResult(PENDING, 'NOT_FOUND', raw=data)
        deposit = data.get('data') or {}
        status = deposit.get('status', '')
        if status == 'COMPLETED':
            return ProviderResult(COMPLETED, status, reference=deposit.get('providerTransactionId', ''), raw=data)
        if status == 'FAILED':
            reason = deposit.get('failureReason') or {}
            code = reason.get('failureCode', 'UNKNOWN_ERROR')
            return ProviderResult(FAILED, status, failure_code=code,
                                  failure_message=friendly_failure(code, reason.get('failureMessage', '')),
                                  raw=data)
        # ACCEPTED, PROCESSING, IN_RECONCILIATION (and SUBMITTED in sandbox)
        return ProviderResult(PENDING, status, raw=data)


def _json(resp):
    try:
        data = resp.json()
        return data if isinstance(data, dict) else {'body': data}
    except ValueError:
        return {'body': resp.text[:500]}


def get_provider(name=None):
    name = name or settings.PAYMENT_PROVIDER
    if name == 'pawapay':
        return PawaPayProvider()
    if name == 'simulator':
        return SimulatorProvider()
    raise ProviderError(f'Unknown payment provider: {name}')
