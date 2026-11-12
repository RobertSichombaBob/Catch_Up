from django import forms
from django.contrib.auth import get_user_model
from django.contrib.auth.forms import AuthenticationForm, UserCreationForm

from apps.payments.networks import normalise_msisdn

User = get_user_model()


class SignUpForm(UserCreationForm):
    first_name = forms.CharField(max_length=150)
    last_name = forms.CharField(max_length=150)
    email = forms.EmailField()
    level = forms.ChoiceField(choices=[('', 'Choose your level')] + list(User.Level.choices))
    year = forms.ChoiceField(choices=[('', 'Year of study (optional)')] + list(User.Year.choices), required=False,
                             label='Year of study')
    agree = forms.BooleanField(label='I agree to the Terms and Privacy Policy')

    class Meta:
        model = User
        fields = ('first_name', 'last_name', 'email', 'level')

    def clean_email(self):
        email = self.cleaned_data['email'].strip().lower()
        if User.objects.filter(email__iexact=email).exists():
            raise forms.ValidationError('An account with this email already exists. Try signing in.')
        return email

    def save(self, commit=True):
        data = self.cleaned_data
        user = User.objects.create_user(
            email=data['email'], password=data['password1'],
            first_name=data['first_name'].strip(), last_name=data['last_name'].strip(),
            level=data['level'], role=User.Role.STUDENT,
        )
        if data.get('year'):
            user.year = data['year']
            user.save(update_fields=['year'])
        return user


class LoginForm(AuthenticationForm):
    username = forms.EmailField(label='Email', widget=forms.EmailInput(attrs={'autofocus': True, 'autocomplete': 'email'}))
    remember = forms.BooleanField(required=False, initial=True, label='Keep me signed in')

    error_messages = {
        'invalid_login': 'That email and password do not match. Please try again.',
        'inactive': 'This account is inactive. Contact support.',
    }


class ProfileForm(forms.ModelForm):
    class Meta:
        model = User
        fields = ('photo', 'first_name', 'last_name', 'phone', 'level', 'year', 'institution', 'email_notifications')
        labels = {'phone': 'Mobile money number', 'email_notifications': 'Email me about payments and new lessons'}

    def clean_photo(self):
        photo = self.cleaned_data.get('photo')
        if photo and getattr(photo, 'size', 0) > 3 * 1024 * 1024:
            raise forms.ValidationError('Photos must be under 3 MB.')
        return photo

    def clean_phone(self):
        phone = self.cleaned_data.get('phone', '').strip()
        if phone and not normalise_msisdn(phone):
            raise forms.ValidationError('Enter a Zambian mobile number, for example 0971234567.')
        return phone


class TutorProfileForm(ProfileForm):
    class Meta(ProfileForm.Meta):
        fields = ProfileForm.Meta.fields + ('headline', 'bio')
