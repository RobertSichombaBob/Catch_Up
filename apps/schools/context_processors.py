def schools(request):
    user = getattr(request, 'user', None)
    if not user or not user.is_authenticated:
        return {}
    from .models import School
    return {'my_schools': list(School.objects.filter(members__user=user)[:5])}
