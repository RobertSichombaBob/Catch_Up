from django import forms

from .models import School


class SchoolForm(forms.ModelForm):
    class Meta:
        model = School
        fields = ('name', 'kind', 'town', 'province', 'contact_name', 'contact_email', 'contact_phone',
                  'student_count_estimate', 'about', 'logo')
        widgets = {'about': forms.Textarea(attrs={'rows': 3})}


class JoinForm(forms.Form):
    code = forms.CharField(max_length=12, label='School join code',
                           help_text='Your school administrator gives you this code.')
    class_name = forms.CharField(max_length=60, required=False, label='Your class (optional)',
                                 help_text='e.g. Form 6A or BSc Year 1')
