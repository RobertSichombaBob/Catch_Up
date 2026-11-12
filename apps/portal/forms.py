from django import forms
from django.conf import settings
from django.contrib.auth import get_user_model
from django.contrib.auth.forms import UserCreationForm

from apps.accounts.models import ParentLink, TutorProfile
from apps.courses.models import Subject
from apps.payments.networks import normalise_msisdn

User = get_user_model()


def check_size(upload):
    if upload and getattr(upload, 'size', 0) > settings.MAX_UPLOAD_MB * 1024 * 1024:
        raise forms.ValidationError(f'This file is larger than {settings.MAX_UPLOAD_MB} MB.')
    return upload


class _RoleSignUpForm(UserCreationForm):
    """Shared sign-up for parents and tutors. Students use accounts.SignUpForm."""
    role = None
    first_name = forms.CharField(max_length=150)
    last_name = forms.CharField(max_length=150)
    email = forms.EmailField()
    phone = forms.CharField(max_length=20, label='Mobile number', help_text='e.g. 0971234567')
    agree = forms.BooleanField(label='I agree to the Terms and Privacy Policy')

    class Meta:
        model = User
        fields = ('first_name', 'last_name', 'email', 'phone')

    def clean_email(self):
        email = self.cleaned_data['email'].strip().lower()
        if User.objects.filter(email__iexact=email).exists():
            raise forms.ValidationError('An account with this email already exists. Try signing in.')
        return email

    def clean_phone(self):
        phone = self.cleaned_data['phone'].strip()
        if not normalise_msisdn(phone):
            raise forms.ValidationError('Enter a Zambian mobile number, for example 0971234567.')
        return phone

    def save(self, commit=True):
        d = self.cleaned_data
        return User.objects.create_user(
            email=d['email'], password=d['password1'], first_name=d['first_name'].strip(),
            last_name=d['last_name'].strip(), phone=d['phone'], role=self.role)


class ParentSignUpForm(_RoleSignUpForm):
    role = User.Role.PARENT


class TutorSignUpForm(_RoleSignUpForm):
    role = User.Role.TUTOR

    def save(self, commit=True):
        user = super().save(commit)
        TutorProfile.objects.create(user=user, payout_phone=user.phone)
        return user


class TutorVerificationForm(forms.ModelForm):
    headline = forms.CharField(max_length=150, required=False,
                               help_text='One line shown on your courses, e.g. "A-level Physics teacher, 8 years"')
    bio = forms.CharField(widget=forms.Textarea(attrs={'rows': 4}), required=False,
                          help_text='Tell students and parents about your teaching')

    class Meta:
        model = TutorProfile
        fields = ('tcz_number', 'nrc_number', 'qualification', 'degree_title', 'degree_institution',
                  'graduation_year', 'specialisations', 'years_experience', 'current_school',
                  'tcz_certificate', 'degree_certificate', 'id_document', 'cv', 'payout_phone')
        widgets = {'specialisations': forms.CheckboxSelectMultiple}
        help_texts = {
            'tcz_number': 'Your Teaching Council of Zambia registration number',
            'tcz_certificate': 'PDF or photo of your TCZ practising certificate',
            'degree_certificate': 'PDF or photo of your degree or diploma certificate',
            'id_document': 'PDF or photo of your NRC or passport',
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['specialisations'].queryset = Subject.objects.all()
        user = self.instance.user
        self.fields['headline'].initial = user.headline
        self.fields['bio'].initial = user.bio

    def clean_tcz_certificate(self):
        return check_size(self.cleaned_data.get('tcz_certificate'))

    def clean_degree_certificate(self):
        return check_size(self.cleaned_data.get('degree_certificate'))

    def clean_id_document(self):
        return check_size(self.cleaned_data.get('id_document'))

    def clean_cv(self):
        return check_size(self.cleaned_data.get('cv'))

    def clean_payout_phone(self):
        phone = self.cleaned_data.get('payout_phone', '').strip()
        if phone and not normalise_msisdn(phone):
            raise forms.ValidationError('Enter a Zambian mobile number, for example 0971234567.')
        return phone

    def save(self, commit=True):
        profile = super().save(commit)
        user = profile.user
        user.headline = self.cleaned_data.get('headline', '')
        user.bio = self.cleaned_data.get('bio', '')
        user.save(update_fields=['headline', 'bio'])
        return profile


class LinkChildForm(forms.Form):
    code = forms.CharField(max_length=8, label="Your child's invite code",
                           help_text='Your child finds this 6-character code on their profile page.')
    relationship = forms.ChoiceField(choices=[('Mother', 'Mother'), ('Father', 'Father'), ('Guardian', 'Guardian'),
                                              ('Sponsor', 'Sponsor'), ('Other', 'Other')])

    def __init__(self, *args, parent=None, **kwargs):
        self.parent = parent
        super().__init__(*args, **kwargs)

    def clean_code(self):
        code = self.cleaned_data['code'].strip().upper().replace(' ', '')
        student = User.objects.filter(invite_code=code, role=User.Role.STUDENT, is_active=True).first()
        if not student:
            raise forms.ValidationError('We could not find a student with that code. Check it and try again.')
        if ParentLink.objects.filter(parent=self.parent, student=student).exists():
            raise forms.ValidationError(f'You are already linked to {student.display_name}.')
        self.student = student
        return code


class TutorReviewForm(forms.Form):
    decision = forms.ChoiceField(choices=[('approve', 'Approve: the tutor can publish and be paid'),
                                          ('reject', 'Ask for changes')], widget=forms.RadioSelect)
    note = forms.CharField(widget=forms.Textarea(attrs={'rows': 3}), required=False,
                           help_text='Required when asking for changes. The tutor sees this.')

    def clean(self):
        data = super().clean()
        if data.get('decision') == 'reject' and not data.get('note', '').strip():
            self.add_error('note', 'Tell the tutor what needs to change.')
        return data
