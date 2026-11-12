"""Existing tutors were added by the platform before verification existed,
so they start as verified; review their documents in the control room.
Existing students get an invite code for linking a parent."""
import secrets

from django.db import migrations

ALPHABET = 'ABCDEFGHJKLMNPQRSTUVWXYZ23456789'


def forwards(apps, schema_editor):
    User = apps.get_model('accounts', 'User')
    TutorProfile = apps.get_model('accounts', 'TutorProfile')
    for tutor in User.objects.filter(role='tutor'):
        TutorProfile.objects.get_or_create(user=tutor, defaults={
            'status': 'approved', 'review_note': 'Added before verification was introduced.'})
    for student in User.objects.filter(role='student', invite_code=''):
        student.invite_code = ''.join(secrets.choice(ALPHABET) for _ in range(6))
        student.save(update_fields=['invite_code'])


class Migration(migrations.Migration):
    dependencies = [('accounts', '0002_user_invite_code_user_photo_user_year_and_more')]
    operations = [migrations.RunPython(forwards, migrations.RunPython.noop)]
