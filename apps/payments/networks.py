"""Zambian mobile money networks and phone number handling."""
import re

MTN = 'MTN'
AIRTEL = 'AIRTEL'
ZAMTEL = 'ZAMTEL'

NETWORKS = {
    MTN: {'label': 'MTN MoMo', 'pawapay': 'MTN_MOMO_ZMB', 'prefixes': ('96', '76')},
    AIRTEL: {'label': 'Airtel Money', 'pawapay': 'AIRTEL_OAPI_ZMB', 'prefixes': ('97', '77', '57')},
    ZAMTEL: {'label': 'Zamtel Money', 'pawapay': 'ZAMTEL_ZMB', 'prefixes': ('95', '75')},
}
NETWORK_CHOICES = [(code, info['label']) for code, info in NETWORKS.items()]


def normalise_msisdn(raw):
    """Return the number as 260XXXXXXXXX (12 digits), or '' if it is not a
    valid Zambian mobile number. Accepts 0971234567, 971234567,
    +260 97 123 4567, 260971234567 and similar."""
    digits = re.sub(r'\D', '', raw or '')
    if digits.startswith('260'):
        digits = digits[3:]
    elif digits.startswith('0'):
        digits = digits[1:]
    if len(digits) != 9 or digits[0] not in '579':
        return ''
    return '260' + digits


def detect_network(raw):
    """Guess the network from the number prefix. Returns '' when unknown."""
    msisdn = normalise_msisdn(raw)
    if not msisdn:
        return ''
    prefix = msisdn[3:5]
    for code, info in NETWORKS.items():
        if prefix in info['prefixes']:
            return code
    return ''


def display_msisdn(msisdn):
    """260971234567 -> 097 123 4567"""
    if not msisdn or len(msisdn) != 12:
        return msisdn or ''
    local = '0' + msisdn[3:]
    return f'{local[:3]} {local[3:6]} {local[6:]}'
