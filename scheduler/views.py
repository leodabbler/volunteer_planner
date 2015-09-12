import json
import datetime

from django.core.urlresolvers import reverse, reverse_lazy
from django.contrib import messages
from django.http.response import HttpResponseRedirect, JsonResponse, Http404
from django.shortcuts import render, get_object_or_404
from django.utils.decorators import method_decorator
from django.views.generic import TemplateView, FormView
from django.views.generic.edit import UpdateView
from django.contrib.auth.decorators import login_required, permission_required
from django.contrib.auth.models import User
from django.utils.translation import ugettext as _

from .models import Location, Need
from notifications.models import Notification
from registration.models import RegistrationProfile
from .forms import RegisterForNeedForm


class LoginRequiredMixin(object):

    @method_decorator(login_required())
    def dispatch(self, *args, **kwargs):
        return super(LoginRequiredMixin, self).dispatch(*args, **kwargs)


class HomeView(TemplateView):
    template_name = "home.html"

    def get(self, request, *args, **kwargs):
        if self.request.user.is_authenticated():
            return HttpResponseRedirect(reverse('helpdesk'))
        context = self.get_context_data(**kwargs)
        return self.render_to_response(context)

    def get_context_data(self, **kwargs):

        if 'locations' not in kwargs:
            kwargs['locations'] = Location.objects.all()

        if 'notifications' not in kwargs:
            kwargs['notifications'] = Notification.objects.all()

        if 'statistics' not in kwargs:
            kwargs['statistics'] = Location.objects.all()

        return kwargs


class HelpDesk(LoginRequiredMixin, TemplateView):
    template_name = "helpdesk.html"

    def get_context_data(self, **kwargs):
        if 'locations' not in kwargs:
            kwargs['locations'] = Location.objects.all()

        if 'need_dates_by_location' not in kwargs:
            locations = Location.objects.all()
            the_dates = []
            for loc in locations:
                dates = {loc: loc.get_dates_of_needs()}
                the_dates.append(dates)
            kwargs['need_dates_by_location'] = the_dates

        if 'notifications' not in kwargs:
            kwargs['notifications'] = Notification.objects.all()

        return kwargs


class ProfileView(UpdateView):
    model = User
    fields = ['first_name', 'last_name', 'email']
    template_name = "profile_edit.html"
    success_url = reverse_lazy('profile_edit')

    def get_object(self, queryset=None):
        """
        Returns the object the view is displaying.

        By default this requires `self.queryset` and a `pk` or `slug` argument
        in the URLconf, but subclasses can override this to return any object.
        """
        # Use a custom queryset if provided; this is required for subclasses
        # like DateDetailView
        if queryset is None:
            queryset = self.get_queryset()

        # Next, try looking up by primary key.
        pk = self.request.user.pk
        if pk is not None:
            queryset = queryset.filter(pk=pk)

        try:
            # Get the single item from the filtered queryset
            obj = queryset.get()
        except queryset.model.DoesNotExist:
            raise Http404(_("No %(verbose_name)s found matching the query") %
                          {'verbose_name': queryset.model._meta.verbose_name})
        return obj


class PlannerView(LoginRequiredMixin, FormView):
    """
    View that gets shown to volunteers when they browse a specific day.
    It'll show all the available needs, and they can add and remove
    themselves from needs.
    """
    template_name = "helpdesk_single.html"
    form_class = RegisterForNeedForm

    def get_context_data(self, **kwargs):
        context = super(PlannerView, self).get_context_data(**kwargs)
        context['needs'] = Need.objects.filter(location__pk=self.kwargs['pk'])\
                .filter(time_period_to__date_time__year=self.kwargs['year'],
                        time_period_to__date_time__month=self.kwargs['month'],
                        time_period_to__date_time__day=self.kwargs['day'])\
                .order_by('topic', 'time_period_to__date_time')
        return context

    def form_invalid(self, form):
        messages.error(self.request, 'The submitted data was invalid.')
        return super(PlannerView, self).form_invalid(form)

    def form_valid(self, form):
        reg_profile = self.request.user.registrationprofile
        need = form.cleaned_data['need']
        if form.cleaned_data['action'] == RegisterForNeedForm.ADD:
            reg_profile.needs.add(need)
        elif form.cleaned_data['action'] == RegisterForNeedForm.REMOVE:
            reg_profile.needs.remove(need)
        reg_profile.save()
        return super(PlannerView, self).form_valid(form)

    def get_success_url(self):
        """
        Redirect to the same page.
        """
        return reverse('planner_by_location', kwargs=self.kwargs)


@login_required(login_url='/auth/login/')
@permission_required('location.can_view')
def volunteer_list(request, **kwargs):
    """
    Show list of volunteers for current shift
    """
    today = datetime.date.today()
    loc = get_object_or_404(Location, id=kwargs.get('loc_pk'))
    needs = Need.objects.filter(location=loc, time_period_to__date_time__contains=today)
    data = list(RegistrationProfile.objects.filter(needs__in=needs).distinct().values_list('user__email', flat=True))
    # add param ?type=json in url to get JSON data
    if request.GET.get('type') == 'json':
        return JsonResponse(data, safe=False)
    return render(request, 'volunteer_list.html', {'data': json.dumps(data), 'location': loc, 'today': today})
