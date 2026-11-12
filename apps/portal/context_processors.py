"""The mobile bottom bar and the account menu change with the user's role."""
from django.urls import reverse


def _item(label, icon, url_name, match, *args):
    return {'label': label, 'icon': icon, 'url': reverse(url_name, args=args), 'match': match}


def navigation(request):
    user = getattr(request, 'user', None)
    path = request.path
    if not user or not user.is_authenticated:
        items = [
            _item('Home', 'home', 'core:home', '/'),
            _item('Courses', 'book-open', 'courses:catalog', '/courses/'),
            _item('Tutors', 'users', 'portal:tutors', '/tutors/'),
            _item('Schools', 'graduation', 'schools:index', '/schools/'),
            _item('Sign in', 'user', 'portal:choose', '/portal/'),
        ]
    elif user.is_platform_admin or user.is_staff:
        items = [
            _item('Overview', 'chart', 'portal:admin_home', '/control/'),
            _item('Tutors', 'shield', 'portal:admin_tutors', '/control/tutors/'),
            _item('Courses', 'book-open', 'courses:catalog', '/courses/'),
            _item('Alerts', 'bell', 'notifications:inbox', '/notifications/'),
            _item('Me', 'user', 'accounts:profile', '/accounts/'),
        ]
    elif user.is_tutor:
        items = [
            _item('Studio', 'grid', 'core:tutor_dashboard', '/tutor/'),
            _item('Classes', 'calendar', 'classroom:tutor_home', '/classroom/'),
            _item('Earnings', 'wallet', 'ledger:earnings', '/earnings/'),
            _item('Alerts', 'bell', 'notifications:inbox', '/notifications/'),
            _item('Me', 'user', 'accounts:profile', '/accounts/'),
        ]
    elif user.is_parent:
        items = [
            _item('Home', 'home', 'portal:parent_home', '/parent/'),
            _item('Link child', 'link', 'portal:parent_link', '/parent/link/'),
            _item('Courses', 'book-open', 'courses:catalog', '/courses/'),
            _item('Alerts', 'bell', 'notifications:inbox', '/notifications/'),
            _item('Me', 'user', 'accounts:profile', '/accounts/'),
        ]
    else:
        items = [
            _item('Home', 'home', 'core:dashboard', '/dashboard/'),
            _item('Courses', 'book-open', 'courses:catalog', '/courses/'),
            _item('Classes', 'calendar', 'classroom:my_classes', '/classroom/'),
            _item('Alerts', 'bell', 'notifications:inbox', '/notifications/'),
            _item('Me', 'user', 'accounts:profile', '/accounts/'),
        ]
    # Only the most specific match is highlighted (e.g. /parent/link/ over /parent/).
    hits = [i for i in items if (path == i['match'] if i['match'] == '/' else path.startswith(i['match']))]
    best = max(hits, key=lambda i: len(i['match']), default=None)
    for item in items:
        item['active'] = item is best
    return {'bottom_nav': items}
