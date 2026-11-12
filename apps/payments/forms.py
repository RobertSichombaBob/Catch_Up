from django import forms

from .networks import NETWORK_CHOICES, detect_network, normalise_msisdn


class CheckoutForm(forms.Form):
    network = forms.ChoiceField(choices=NETWORK_CHOICES, widget=forms.RadioSelect)
    phone = forms.CharField(max_length=20, label='Mobile money number',
                            widget=forms.TextInput(attrs={'inputmode': 'tel', 'autocomplete': 'tel',
                                                          'placeholder': '097 123 4567'}))

    def __init__(self, *args, children=None, **kwargs):
        super().__init__(*args, **kwargs)
        if children:
            self.fields['student'] = forms.ModelChoiceField(
                queryset=type(children[0]).objects.filter(pk__in=[c.pk for c in children]),
                label='Who is this course for?', empty_label=None)
            self.order_fields(['student', 'network', 'phone'])

    def clean(self):
        data = super().clean()
        phone, network = data.get('phone'), data.get('network')
        if phone is None:
            return data
        if not normalise_msisdn(phone):
            self.add_error('phone', 'Enter a Zambian mobile number, for example 0971234567.')
            return data
        guessed = detect_network(phone)
        if network and guessed and guessed != network:
            labels = dict(NETWORK_CHOICES)
            self.add_error('phone', f'This looks like a {labels[guessed]} number, but you chose '
                                    f'{labels[network]}. Pick the network your number is on.')
        return data
