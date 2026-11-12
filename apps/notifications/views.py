from django.contrib.auth.decorators import login_required
from django.shortcuts import get_object_or_404, redirect, render
from django.utils.http import url_has_allowed_host_and_scheme
from django.views.decorators.http import require_POST

from .models import Notification


@login_required
def inbox(request):
    notes = request.user.notifications.all()[:100]
    return render(request, 'notifications/inbox.html', {'notes': notes})


@login_required
@require_POST
def open_notification(request, pk):
    note = get_object_or_404(Notification, pk=pk, user=request.user)
    if not note.is_read:
        note.is_read = True
        note.save(update_fields=['is_read'])
    if note.url and url_has_allowed_host_and_scheme(note.url, allowed_hosts={request.get_host()}):
        return redirect(note.url)
    return redirect('notifications:inbox')


@login_required
@require_POST
def mark_all_read(request):
    request.user.notifications.filter(is_read=False).update(is_read=True)
    return redirect(request.POST.get('next') if url_has_allowed_host_and_scheme(
        request.POST.get('next'), allowed_hosts={request.get_host()}) else 'notifications:inbox')
