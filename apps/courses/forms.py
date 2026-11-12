from decimal import Decimal

from django import forms
from django.conf import settings

from .materials import ACCEPTED, detect_kind
from .models import Course, CourseMaterial, Lesson, Subject


class LessonForm(forms.ModelForm):
    class Meta:
        model = Lesson
        fields = ('module', 'title', 'order', 'is_preview', 'content')
        widgets = {'content': forms.Textarea(attrs={'rows': 22, 'class': 'code-input'})}
        help_texts = {'content': 'HTML: headings, paragraphs, lists, tables, images, <details> for answers. '
                                 'Maths: write \\( x^2 \\) inline or \\[ x^2 \\] on its own line.'}

    def __init__(self, *args, course, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['module'].queryset = course.modules.all()
        self.fields['module'].empty_label = None


class CourseForm(forms.ModelForm):
    class Meta:
        model = Course
        fields = ('title', 'subject', 'level', 'year', 'summary', 'description', 'outcomes', 'price', 'cover',
                  'school', 'is_published')
        widgets = {
            'description': forms.Textarea(attrs={'rows': 6}),
            'outcomes': forms.Textarea(attrs={'rows': 4}),
            'summary': forms.TextInput(),
        }
        help_texts = {
            'summary': 'One or two sentences shown on the course card',
            'price': 'Students pay this every month by mobile money. You receive 50% after payment fees.',
            'is_published': 'Students can find and buy the course',
        }

    def __init__(self, *args, user, **kwargs):
        super().__init__(*args, **kwargs)
        self.user = user
        # A school teacher who is not a verified public tutor may only create
        # courses that are private to their school.
        self.school_only = not user.is_verified_tutor and not user.is_tutor
        if not user.is_platform_admin and not self.school_only:
            profile = getattr(user, 'tutor_profile', None)
            allowed = profile.specialisations.all() if profile else Subject.objects.none()
            self.fields['subject'].queryset = allowed
            self.fields['subject'].help_text = 'Only the subjects you were verified to teach'
        from apps.schools.models import School
        self.fields['school'].queryset = School.objects.filter(
            members__user=user, members__role__in=['admin', 'teacher']) if not user.is_platform_admin \
            else School.objects.all()
        self.fields['school'].required = False
        self.fields['school'].empty_label = 'Public: anyone can find and buy it'
        self.fields['school'].label = 'Who is this course for?'
        if self.school_only:
            self.fields['school'].required = True
            self.fields['school'].empty_label = None
            self.fields['school'].help_text = 'School teachers publish to their own school'

    def clean_price(self):
        price = self.cleaned_data['price']
        low, high = Decimal(settings.MIN_COURSE_PRICE), Decimal(settings.MAX_COURSE_PRICE)
        if not self.user.is_platform_admin and not (low <= price <= high):
            raise forms.ValidationError(f'Monthly prices must be between K{low:.0f} and K{high:.0f}.')
        return price

    def clean_cover(self):
        cover = self.cleaned_data.get('cover')
        if cover and getattr(cover, 'size', 0) > 5 * 1024 * 1024:
            raise forms.ValidationError('Cover photos must be under 5 MB.')
        return cover

    def clean_is_published(self):
        publish = self.cleaned_data.get('is_published')
        if publish and self.school_only:
            return publish  # visible only inside the school
        if publish and not self.user.is_verified_tutor:
            raise forms.ValidationError('You can publish once your tutor verification is approved.')
        return publish


class MaterialForm(forms.ModelForm):
    class Meta:
        model = CourseMaterial
        fields = ('title', 'category', 'file', 'lesson', 'description', 'allow_download', 'is_preview')
        help_texts = {'file': 'PDF, Word (.docx), PowerPoint (.pptx), Excel (.xlsx), HTML or an image. '
                              'Up to 25 MB.'}

    def __init__(self, *args, course, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['lesson'].queryset = course.lessons()
        self.fields['lesson'].required = False
        self.fields['file'].widget.attrs['accept'] = ACCEPTED

    def clean_file(self):
        upload = self.cleaned_data['file']
        if hasattr(upload, 'content_type'):  # a new upload, not the existing file
            self.detected_kind = detect_kind(upload)
        return upload
