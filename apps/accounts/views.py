from django.contrib import messages
from django.contrib.auth import login
from django.contrib.auth import views as auth_views
from django.contrib.auth.decorators import login_required
from django.shortcuts import redirect, render
from django.urls import reverse_lazy
from django.utils.http import url_has_allowed_host_and_scheme
from django.views.decorators.http import require_http_methods

from apps.notifications.services import notify

from .forms import LoginForm, ProfileForm, SignUpForm, TutorProfileForm


def _safe_next(request, default):
    nxt = request.POST.get('next') or request.GET.get('next')
    if nxt and url_has_allowed_host_and_scheme(nxt, allowed_hosts={request.get_host()},
                                               require_https=request.is_secure()):
        return nxt
    return default


@require_http_methods(['GET', 'POST'])
def signup(request):
    if request.user.is_authenticated:
        return redirect('core:dashboard')
    form = SignUpForm(request.POST or None)
    if request.method == 'POST' and form.is_valid():
        user = form.save()
        login(request, user, backend='apps.accounts.backends.EmailBackend')
        notify(
            user,
            title='Welcome to Catch Up',
            body='Your account is ready. Every course has free preview lessons, so start one now.',
            url=reverse_lazy('courses:catalog'),
            email_template='emails/welcome',
        )
        messages.success(request, f'Welcome, {user.first_name}! Your account is ready.')
        return redirect(_safe_next(request, 'core:dashboard'))
    return render(request, 'accounts/signup.html', {'form': form, 'next': request.GET.get('next', '')})


class LoginView(auth_views.LoginView):
    form_class = LoginForm
    template_name = 'accounts/login.html'
    redirect_authenticated_user = True

    def form_valid(self, form):
        response = super().form_valid(form)
        if not form.cleaned_data.get('remember'):
            self.request.session.set_expiry(0)
        return response


@login_required
@require_http_methods(['GET', 'POST'])
def profile(request):
    form_class = TutorProfileForm if request.user.is_tutor else ProfileForm
    form = form_class(request.POST or None, request.FILES or None, instance=request.user)
    if request.method == 'POST' and form.is_valid():
        form.save()
        messages.success(request, 'Your profile has been saved.')
        return redirect('accounts:profile')
    return render(request, 'accounts/profile.html', {
        'form': form,
        'parent_links': request.user.parent_links.select_related('parent'),
        'child_links': request.user.child_links.select_related('student'),
    })


class PasswordChangeView(auth_views.PasswordChangeView):
    template_name = 'accounts/password_change.html'
    success_url = reverse_lazy('accounts:profile')

    def form_valid(self, form):
        messages.success(self.request, 'Your password has been changed.')
        return super().form_valid(form)
