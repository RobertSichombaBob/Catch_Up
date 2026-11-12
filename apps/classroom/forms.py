from django import forms
from django.utils import timezone

from .models import Announcement, Assessment, Booking, ClassGroup, Question, Session

DT = forms.DateTimeInput(attrs={'type': 'datetime-local'}, format='%Y-%m-%dT%H:%M')


class ClassGroupForm(forms.ModelForm):
    class Meta:
        model = ClassGroup
        fields = ('name', 'description', 'capacity', 'meeting_url', 'is_open')


class SessionForm(forms.ModelForm):
    notify_students = forms.BooleanField(required=False, initial=True, label='Notify students by email and in the app')

    class Meta:
        model = Session
        fields = ('title', 'kind', 'class_group', 'starts_at', 'duration_minutes', 'meeting_url', 'location',
                  'agenda', 'recording_url')
        widgets = {'starts_at': DT, 'agenda': forms.Textarea(attrs={'rows': 3})}

    def __init__(self, *args, course, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['class_group'].queryset = course.class_groups.all()
        self.fields['starts_at'].input_formats = ['%Y-%m-%dT%H:%M']

    def clean_starts_at(self):
        value = self.cleaned_data['starts_at']
        if not self.instance.pk and value < timezone.now():
            raise forms.ValidationError('Choose a time in the future.')
        return value


class AssessmentForm(forms.ModelForm):
    class Meta:
        model = Assessment
        fields = ('title', 'kind', 'lesson', 'instructions', 'due_at', 'time_limit_minutes', 'max_attempts',
                  'pass_mark', 'weight', 'required_to_progress', 'must_pass_to_progress', 'allow_file_upload',
                  'show_answers_after', 'is_published')
        widgets = {'due_at': DT, 'instructions': forms.Textarea(attrs={'rows': 4})}

    def __init__(self, *args, course, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['lesson'].queryset = course.lessons()
        self.fields['due_at'].input_formats = ['%Y-%m-%dT%H:%M']


class QuestionForm(forms.ModelForm):
    class Meta:
        model = Question
        fields = ('kind', 'text', 'choices', 'answer', 'tolerance', 'marks', 'explanation', 'order')
        widgets = {'text': forms.Textarea(attrs={'rows': 3}), 'choices': forms.Textarea(attrs={'rows': 4}),
                   'explanation': forms.Textarea(attrs={'rows': 2})}

    def clean(self):
        data = super().clean()
        kind = data.get('kind')
        answer = (data.get('answer') or '').strip()
        if kind == Question.Kind.MCQ:
            options = [c for c in (data.get('choices') or '').splitlines() if c.strip()]
            if len(options) < 2:
                self.add_error('choices', 'Give at least two options, one per line.')
            elif not answer.isdigit() or not 1 <= int(answer) <= len(options):
                self.add_error('answer', f'Enter the number of the correct option, 1 to {len(options)}.')
        elif kind == Question.Kind.NUMERIC:
            try:
                float(answer.replace(',', ''))
            except ValueError:
                self.add_error('answer', 'Enter the correct number.')
        elif kind == Question.Kind.SHORT and not answer:
            self.add_error('answer', 'Enter at least one accepted answer.')
        return data


class AnnouncementForm(forms.ModelForm):
    class Meta:
        model = Announcement
        fields = ('title', 'body', 'class_group', 'notify_parents')
        widgets = {'body': forms.Textarea(attrs={'rows': 4})}

    def __init__(self, *args, course, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['class_group'].queryset = course.class_groups.all()
        self.fields['class_group'].empty_label = 'Every student in the course'
        self.fields['class_group'].required = False


class BookingForm(forms.ModelForm):
    class Meta:
        model = Booking
        fields = ('preferred_start', 'duration_minutes', 'topic', 'message')
        widgets = {'preferred_start': DT, 'message': forms.Textarea(attrs={'rows': 3})}
        labels = {'preferred_start': 'Preferred date and time'}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['preferred_start'].input_formats = ['%Y-%m-%dT%H:%M']

    def clean_preferred_start(self):
        value = self.cleaned_data['preferred_start']
        if value < timezone.now() + timezone.timedelta(hours=2):
            raise forms.ValidationError('Give your tutor at least 2 hours\' notice.')
        return value


class BookingReplyForm(forms.Form):
    decision = forms.ChoiceField(choices=[('confirm', 'Confirm'), ('decline', 'Decline')], widget=forms.RadioSelect)
    starts_at = forms.DateTimeField(required=False, widget=DT, input_formats=['%Y-%m-%dT%H:%M'],
                                    help_text='Leave empty to keep the student\'s preferred time')
    meeting_url = forms.URLField(required=False, label='Meeting link')
    reply = forms.CharField(max_length=300, required=False, label='Message to the student')


class CheckInForm(forms.Form):
    code = forms.CharField(max_length=4, label='4-digit code from your tutor',
                           widget=forms.TextInput(attrs={'inputmode': 'numeric', 'autocomplete': 'off'}))
