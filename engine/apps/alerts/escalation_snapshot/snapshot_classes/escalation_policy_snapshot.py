import datetime
import typing
from collections import namedtuple

from celery import Task
from django.db import transaction
from django.utils import timezone

from apps.alerts.constants import NEXT_ESCALATION_DELAY
from apps.alerts.escalation_snapshot.utils import eta_for_escalation_step_notify_if_time
from apps.alerts.incident_appearance.renderers.constants import DEFAULT_BACKUP_TITLE
from apps.alerts.models.alert_group_log_record import AlertGroupLogRecord
from apps.alerts.models.escalation_policy import EscalationPolicy
from apps.alerts.tasks import (
    custom_webhook_result,
    declare_incident,
    notify_all_task,
    notify_group_task,
    notify_user_task,
    resolve_by_last_step_task,
)
from apps.google.client import (
    GoogleCalendarAPIClient,
    GoogleCalendarGenericHTTPError,
    GoogleCalendarRefreshError,
    GoogleCalendarUnauthorizedHTTPError,
)
from apps.labels.alert_group_labels import gather_alert_labels
from apps.alerts.utils import is_declare_incident_step_enabled
from apps.schedules.ical_utils import list_users_to_notify_from_ical

if typing.TYPE_CHECKING:
    from apps.alerts.models.alert import Alert
    from apps.alerts.models.alert_group import AlertGroup
    from apps.alerts.models.escalation_chain import EscalationChain
    from apps.schedules.models import OnCallSchedule
    from apps.slack.models import SlackUserGroup
    from apps.user_management.models import Team, User
    from apps.webhooks.models import Webhook


class EscalationPolicySnapshot:
    __slots__ = (
        "id",
        "order",
        "step",
        "wait_delay",
        "notify_to_users_queue",
        "last_notified_user",
        "from_time",
        "to_time",
        "num_alerts_in_window",
        "num_minutes_in_window",
        "invitees",
        "custom_webhook",
        "notify_schedule",
        "notify_to_group",
        "notify_to_team_members",
        "severity",
        "escalation_counter",
        "passed_last_time",
        "pause_escalation",
    )

    StepExecutionResultData = namedtuple(
        "StepExecutionResultData",
        ["eta", "stop_escalation", "start_from_beginning", "pause_escalation"],
    )

    StepExecutionFunc = typing.Callable[["AlertGroup", str], typing.Optional[StepExecutionResultData]]

    def __init__(
        self,
        id: int,
        order: int,
        step: int,
        wait_delay: typing.Optional[datetime.timedelta],
        notify_to_users_queue: typing.Optional[typing.Sequence["User"]],
        last_notified_user: typing.Optional["User"],
        from_time: typing.Optional[datetime.time],
        to_time: typing.Optional[datetime.time],
        num_alerts_in_window: typing.Optional[int],
        num_minutes_in_window: typing.Optional[int],
        invitees: typing.Optional[str],
        custom_webhook: typing.Optional["Webhook"],
        notify_schedule: typing.Optional["OnCallSchedule"],
        notify_to_group: typing.Optional["SlackUserGroup"],
        escalation_counter: int,
        passed_last_time: typing.Optional[datetime.datetime],
        pause_escalation: bool,
        notify_to_team_members: typing.Optional["Team"] = None,
        severity: typing.Optional[str] = None,
    ):
        self.id = id
        self.order = order
        self.step = step
        self.wait_delay = wait_delay
        self.notify_to_users_queue = notify_to_users_queue
        self.last_notified_user = last_notified_user
        self.from_time = from_time
        self.to_time = to_time
        self.num_alerts_in_window = num_alerts_in_window
        self.num_minutes_in_window = num_minutes_in_window
        self.invitees = invitees
        self.custom_webhook = custom_webhook
        self.notify_schedule = notify_schedule
        self.notify_to_group = notify_to_group
        self.notify_to_team_members = notify_to_team_members
        self.severity = severity
        self.escalation_counter = escalation_counter  # used for STEP_REPEAT_ESCALATION_N_TIMES
        self.passed_last_time = passed_last_time  # used for building escalation plan
        self.pause_escalation = pause_escalation  # used for STEP_NOTIFY_IF_NUM_ALERTS_IN_TIME_WINDOW

    def __str__(self) -> str:
        return f"Escalation link, order: {self.order}, step: '{self.step_display}'"

    @property
    def step_display(self) -> str:
        return EscalationPolicy.STEP_CHOICES[self.step][1]

    @property
    def escalation_policy(self) -> typing.Optional[EscalationPolicy]:
        return EscalationPolicy.objects.filter(pk=self.id).first()

    @property
    def sorted_users_queue(self) -> typing.List["User"]:
        return sorted(self.notify_to_users_queue, key=lambda user: (user.username or "", user.pk))

    @property
    def next_user_in_sorted_queue(self) -> "User":
        users_queue = self.sorted_users_queue
        try:
            last_user_index = users_queue.index(self.last_notified_user)
        except ValueError:
            last_user_index = -1
        next_user = users_queue[(last_user_index + 1) % len(users_queue)]
        return next_user

    def execute(self, alert_group: "AlertGroup", reason: str) -> StepExecutionResultData:
        action_map: typing.Dict[typing.Optional[int], EscalationPolicySnapshot.StepExecutionFunc] = {
            EscalationPolicy.STEP_WAIT: self._escalation_step_wait,
            EscalationPolicy.STEP_FINAL_NOTIFYALL: self._escalation_step_notify_all,
            EscalationPolicy.STEP_REPEAT_ESCALATION_N_TIMES: self._escalation_step_repeat_escalation_n_times,
            EscalationPolicy.STEP_FINAL_RESOLVE: self._escalation_step_resolve,
            EscalationPolicy.STEP_NOTIFY_GROUP: self._escalation_step_notify_user_group,
            EscalationPolicy.STEP_NOTIFY_GROUP_IMPORTANT: self._escalation_step_notify_user_group,
            EscalationPolicy.STEP_NOTIFY_TEAM_MEMBERS: self._escalation_step_notify_team_members,
            EscalationPolicy.STEP_NOTIFY_TEAM_MEMBERS_IMPORTANT: self._escalation_step_notify_team_members,
            EscalationPolicy.STEP_NOTIFY_SCHEDULE: self._escalation_step_notify_on_call_schedule,
            EscalationPolicy.STEP_NOTIFY_SCHEDULE_IMPORTANT: self._escalation_step_notify_on_call_schedule,
            EscalationPolicy.STEP_TRIGGER_CUSTOM_WEBHOOK: self._escalation_step_trigger_custom_webhook,
            EscalationPolicy.STEP_NOTIFY_USERS_QUEUE: self._escalation_step_notify_users_queue,
            EscalationPolicy.STEP_NOTIFY_USERS_QUEUE_IMPORTANT: self._escalation_step_notify_users_queue,
            EscalationPolicy.STEP_NOTIFY_IF_TIME: self._escalation_step_notify_if_time,
            EscalationPolicy.STEP_NOTIFY_IF_NUM_ALERTS_IN_TIME_WINDOW: self._escalation_step_notify_if_num_alerts_in_time_window,
            EscalationPolicy.STEP_NOTIFY_MULTIPLE_USERS: self._escalation_step_notify_multiple_users,
            EscalationPolicy.STEP_NOTIFY_MULTIPLE_USERS_IMPORTANT: self._escalation_step_notify_multiple_users,
            EscalationPolicy.STEP_DECLARE_INCIDENT: self._escalation_step_declare_incident,
            EscalationPolicy.STEP_CREATE_CALENDAR_INVITE: self._escalation_step_create_calendar_invite,
            None: self._escalation_step_not_configured,
        }
        result = action_map[self.step](alert_group, reason)
        self.passed_last_time = timezone.now()  # used for building escalation plan
        # if step doesn't have data to return, return default values
        return result if result is not None else self._get_result_tuple()

    def _escalation_step_wait(self, alert_group: "AlertGroup", _reason: str) -> StepExecutionResultData:
        if self.wait_delay is not None:
            log_record = AlertGroupLogRecord(
                type=AlertGroupLogRecord.TYPE_ESCALATION_TRIGGERED,
                alert_group=alert_group,
                reason="wait",
                escalation_policy=self.escalation_policy,
                escalation_policy_step=self.step,
            )
        else:
            log_record = AlertGroupLogRecord(
                type=AlertGroupLogRecord.TYPE_ESCALATION_FAILED,
                alert_group=alert_group,
                reason="wait",
                escalation_policy=self.escalation_policy,
                escalation_error_code=AlertGroupLogRecord.ERROR_ESCALATION_WAIT_STEP_IS_NOT_CONFIGURED,
                escalation_policy_step=self.step,
            )
        wait_delay = self.wait_delay or EscalationPolicy.DEFAULT_WAIT_DELAY
        eta = timezone.now() + wait_delay
        log_record.save()
        return self._get_result_tuple(eta=eta)

    def _escalation_step_notify_all(self, alert_group: "AlertGroup", _reason: str) -> None:
        tasks = []
        notify_all = notify_all_task.signature(
            args=(alert_group.pk,),
            kwargs={"escalation_policy_snapshot_order": self.order},
            immutable=True,
        )
        tasks.append(notify_all)
        self._execute_tasks(tasks)

    def _escalation_step_notify_users_queue(self, alert_group: "AlertGroup", reason: str) -> None:
        tasks = []
        escalation_policy = self.escalation_policy
        if len(self.notify_to_users_queue) > 0:
            next_user = self.next_user_in_sorted_queue
            self.last_notified_user = next_user
            if escalation_policy is not None:
                escalation_policy.last_notified_user = next_user
                escalation_policy.save(update_fields=["last_notified_user"])

            notify_task = notify_user_task.signature(
                (
                    next_user.pk,
                    alert_group.pk,
                ),
                {
                    "reason": reason,
                    "important": self.step == EscalationPolicy.STEP_NOTIFY_USERS_QUEUE_IMPORTANT,
                },
                immutable=True,
            )

            tasks.append(notify_task)
            log_record = AlertGroupLogRecord(
                type=AlertGroupLogRecord.TYPE_ESCALATION_TRIGGERED,
                author_id=next_user.pk,
                alert_group=alert_group,
                reason=reason,
                escalation_policy=escalation_policy,
                escalation_policy_step=self.step,
            )
        else:
            log_record = AlertGroupLogRecord(
                type=AlertGroupLogRecord.TYPE_ESCALATION_FAILED,
                alert_group=alert_group,
                escalation_policy=escalation_policy,
                escalation_error_code=AlertGroupLogRecord.ERROR_ESCALATION_NOTIFY_QUEUE_NO_RECIPIENTS,
                escalation_policy_step=self.step,
            )
        log_record.save()
        self._execute_tasks(tasks)

    def _escalation_step_notify_multiple_users(self, alert_group: "AlertGroup", reason: str) -> None:
        tasks = []
        escalation_policy = self.escalation_policy
        if len(self.notify_to_users_queue) > 0:
            log_record = AlertGroupLogRecord(
                type=AlertGroupLogRecord.TYPE_ESCALATION_TRIGGERED,
                alert_group=alert_group,
                reason=reason,
                escalation_policy=escalation_policy,
                escalation_policy_step=self.step,
            )

            for user in self.notify_to_users_queue:
                notify_task = notify_user_task.signature(
                    (
                        user.pk,
                        alert_group.pk,
                    ),
                    {
                        "reason": reason,
                        "important": self.step == EscalationPolicy.STEP_NOTIFY_MULTIPLE_USERS_IMPORTANT,
                    },
                    immutable=True,
                )

                tasks.append(notify_task)

                AlertGroupLogRecord(
                    type=AlertGroupLogRecord.TYPE_ESCALATION_TRIGGERED,
                    author=user,
                    alert_group=alert_group,
                    reason=reason,
                    escalation_policy=escalation_policy,
                    escalation_policy_step=self.step,
                ).save()
        else:
            log_record = AlertGroupLogRecord(
                type=AlertGroupLogRecord.TYPE_ESCALATION_FAILED,
                alert_group=alert_group,
                escalation_policy=escalation_policy,
                escalation_error_code=AlertGroupLogRecord.ERROR_ESCALATION_NOTIFY_MULTIPLE_NO_RECIPIENTS,
                escalation_policy_step=self.step,
            )
        log_record.save()
        self._execute_tasks(tasks)

    def _escalation_step_notify_on_call_schedule(self, alert_group: "AlertGroup", reason: str) -> None:
        tasks = []
        escalation_policy = self.escalation_policy
        on_call_schedule = self.notify_schedule
        self.notify_to_users_queue = []

        if on_call_schedule is None:
            log_record = AlertGroupLogRecord(
                type=AlertGroupLogRecord.TYPE_ESCALATION_FAILED,
                alert_group=alert_group,
                escalation_policy=escalation_policy,
                escalation_error_code=AlertGroupLogRecord.ERROR_ESCALATION_SCHEDULE_DOES_NOT_SELECTED,
                escalation_policy_step=self.step,
            )
        else:
            notify_to_users_list = list_users_to_notify_from_ical(on_call_schedule)
            if notify_to_users_list is None:
                log_record = AlertGroupLogRecord(
                    type=AlertGroupLogRecord.TYPE_ESCALATION_FAILED,
                    alert_group=alert_group,
                    escalation_policy=escalation_policy,
                    escalation_error_code=AlertGroupLogRecord.ERROR_ESCALATION_ICAL_IMPORT_FAILED,
                    escalation_policy_step=self.step,
                    step_specific_info={"schedule_name": on_call_schedule.name},
                )
            elif len(notify_to_users_list) == 0:
                log_record = AlertGroupLogRecord(
                    type=AlertGroupLogRecord.TYPE_ESCALATION_FAILED,
                    alert_group=alert_group,
                    reason=reason,
                    escalation_policy=escalation_policy,
                    escalation_error_code=AlertGroupLogRecord.ERROR_ESCALATION_ICAL_NO_VALID_USERS,
                    escalation_policy_step=self.step,
                    step_specific_info={"schedule_name": on_call_schedule.name},
                )
            else:
                log_record = AlertGroupLogRecord(
                    type=AlertGroupLogRecord.TYPE_ESCALATION_TRIGGERED,
                    alert_group=alert_group,
                    reason=reason,
                    escalation_policy=escalation_policy,
                    escalation_policy_step=self.step,
                    step_specific_info={"schedule_name": on_call_schedule.name},
                )
                self.notify_to_users_queue = notify_to_users_list

                for notify_to_user in notify_to_users_list:
                    reason = "user is on duty by schedule ({}) defined in iCal".format(on_call_schedule.name)
                    notify_task = notify_user_task.signature(
                        (
                            notify_to_user.pk,
                            alert_group.pk,
                        ),
                        {
                            "reason": reason,
                            "important": self.step == EscalationPolicy.STEP_NOTIFY_SCHEDULE_IMPORTANT,
                        },
                        immutable=True,
                    )

                    tasks.append(notify_task)

                    AlertGroupLogRecord(
                        type=AlertGroupLogRecord.TYPE_ESCALATION_TRIGGERED,
                        author=notify_to_user,
                        alert_group=alert_group,
                        reason=reason,
                        escalation_policy=escalation_policy,
                        escalation_policy_step=self.step,
                    ).save()
        log_record.save()
        self._execute_tasks(tasks)

    def _escalation_step_notify_user_group(self, alert_group: "AlertGroup", reason: str) -> None:
        tasks = []
        self.notify_to_users_queue = []

        if self.notify_to_group is None:
            log_record = AlertGroupLogRecord(
                type=AlertGroupLogRecord.TYPE_ESCALATION_FAILED,
                alert_group=alert_group,
                reason=reason,
                escalation_policy=self.escalation_policy,
                escalation_error_code=AlertGroupLogRecord.ERROR_ESCALATION_NOTIFY_GROUP_STEP_IS_NOT_CONFIGURED,
                escalation_policy_step=self.step,
            )
            log_record.save()
        else:
            notify_group = notify_group_task.signature(
                args=(alert_group.pk,),
                kwargs={
                    "escalation_policy_snapshot_order": self.order,
                },
                immutable=True,
            )
            tasks.append(notify_group)
        self._execute_tasks(tasks)

    def _escalation_step_notify_team_members(self, alert_group: "AlertGroup", reason: str) -> None:
        tasks = []

        if self.notify_to_team_members is None:
            log_record = AlertGroupLogRecord(
                type=AlertGroupLogRecord.TYPE_ESCALATION_FAILED,
                alert_group=alert_group,
                reason=reason,
                escalation_policy=self.escalation_policy,
                escalation_error_code=AlertGroupLogRecord.ERROR_ESCALATION_NOTIFY_TEAM_MEMBERS_STEP_IS_NOT_CONFIGURED,
                escalation_policy_step=self.step,
            )
            log_record.save()
        else:
            log_record = AlertGroupLogRecord(
                type=AlertGroupLogRecord.TYPE_ESCALATION_TRIGGERED,
                alert_group=alert_group,
                reason=reason,
                escalation_policy=self.escalation_policy,
                escalation_policy_step=self.step,
                step_specific_info={"team": self.notify_to_team_members.name},
            )
            log_record.save()
            self.notify_to_users_queue = self.notify_to_team_members.users.all()
            reason = "user belongs to team {}".format(self.notify_to_team_members.name)
            for notify_to_user in self.notify_to_users_queue:
                notify_task = notify_user_task.signature(
                    (
                        notify_to_user.pk,
                        alert_group.pk,
                    ),
                    {
                        "reason": reason,
                        "important": self.step == EscalationPolicy.STEP_NOTIFY_TEAM_MEMBERS_IMPORTANT,
                    },
                    immutable=True,
                )
                tasks.append(notify_task)
                AlertGroupLogRecord.objects.create(
                    type=AlertGroupLogRecord.TYPE_ESCALATION_TRIGGERED,
                    author=notify_to_user,
                    alert_group=alert_group,
                    reason=reason,
                    escalation_policy=self.escalation_policy,
                    escalation_policy_step=self.step,
                )

        self._execute_tasks(tasks)

    def _escalation_step_declare_incident(self, alert_group: "AlertGroup", _reason: str) -> None:
        grafana_declare_incident_enabled = is_declare_incident_step_enabled(
            organization=alert_group.channel.organization
        )
        if not grafana_declare_incident_enabled:
            AlertGroupLogRecord(
                type=AlertGroupLogRecord.TYPE_ESCALATION_FAILED,
                alert_group=alert_group,
                reason="Declare Incident step is not enabled",
                escalation_policy=self.escalation_policy,
                escalation_error_code=AlertGroupLogRecord.ERROR_ESCALATION_DECLARE_INCIDENT_STEP_IS_NOT_ENABLED,
                escalation_policy_step=self.step,
            ).save()
            return
        tasks = []
        declare_incident_task = declare_incident.signature(
            args=(alert_group.pk,),
            kwargs={
                "escalation_policy_pk": self.id,
                "severity": self.severity,
            },
            immutable=True,
        )
        tasks.append(declare_incident_task)
        self._execute_tasks(tasks)

    def _escalation_step_create_calendar_invite(self, alert_group: "AlertGroup", _reason: str) -> None:
        escalation_policy = self.escalation_policy
        invitees = self._get_calendar_invitees(alert_group)
        invitees_label = self._get_invitees_display()
        organization = alert_group.channel.organization

        if self.invitees is None:
            AlertGroupLogRecord.objects.create(
                type=AlertGroupLogRecord.TYPE_ESCALATION_FAILED,
                alert_group=alert_group,
                escalation_policy=escalation_policy,
                escalation_error_code=AlertGroupLogRecord.ERROR_ESCALATION_CREATE_CALENDAR_INVITE_STEP_IS_NOT_CONFIGURED,
                escalation_policy_step=self.step,
            )
            return

        if not organization.has_google_oauth2_organization_connected:
            AlertGroupLogRecord.objects.create(
                type=AlertGroupLogRecord.TYPE_ESCALATION_FAILED,
                alert_group=alert_group,
                escalation_policy=escalation_policy,
                escalation_error_code=AlertGroupLogRecord.ERROR_ESCALATION_CREATE_CALENDAR_INVITE_GOOGLE_CALENDAR_NOT_CONNECTED,
                escalation_policy_step=self.step,
            )
            return

        if not invitees:
            AlertGroupLogRecord.objects.create(
                type=AlertGroupLogRecord.TYPE_ESCALATION_FAILED,
                alert_group=alert_group,
                escalation_policy=escalation_policy,
                escalation_error_code=AlertGroupLogRecord.ERROR_ESCALATION_CREATE_CALENDAR_INVITE_NO_RECIPIENTS,
                escalation_policy_step=self.step,
                step_specific_info={"invitees": invitees_label},
            )
            return

        summary, description = self._render_calendar_event_details(alert_group)
        start = timezone.now()
        end = start + datetime.timedelta(hours=1)

        AlertGroupLogRecord.objects.create(
            type=AlertGroupLogRecord.TYPE_ESCALATION_TRIGGERED,
            alert_group=alert_group,
            escalation_policy=escalation_policy,
            escalation_policy_step=self.step,
            step_specific_info={"invitees": invitees_label},
        )

        google_organization = organization.google_oauth2_organization
        client = GoogleCalendarAPIClient(google_organization.access_token, google_organization.refresh_token)

        try:
            event = client.create_event(
                summary=summary,
                description=description,
                start=start,
                end=end,
                attendees=[user.email for user in invitees],
            )
        except GoogleCalendarUnauthorizedHTTPError:
            failure_reason = "Google Calendar connection is missing required permissions"
        except GoogleCalendarRefreshError:
            organization.reset_google_oauth2_organization_settings()
            failure_reason = "Google Calendar connection expired. Reconnect Google Calendar."
        except GoogleCalendarGenericHTTPError:
            failure_reason = "Google Calendar event creation failed"
        else:
            AlertGroupLogRecord.objects.create(
                type=AlertGroupLogRecord.TYPE_ESCALATION_FINISHED,
                alert_group=alert_group,
                escalation_policy=escalation_policy,
                escalation_policy_step=self.step,
                step_specific_info={
                    "invitees": invitees_label,
                    "google_calendar_event_title": summary,
                    "google_calendar_event_link": event.get("htmlLink"),
                    "google_calendar_meet_link": event.get("hangoutLink"),
                },
            )
            return

        AlertGroupLogRecord.objects.create(
            type=AlertGroupLogRecord.TYPE_ESCALATION_FAILED,
            alert_group=alert_group,
            escalation_policy=escalation_policy,
            escalation_error_code=AlertGroupLogRecord.ERROR_ESCALATION_CREATE_CALENDAR_INVITE_FAILED,
            escalation_policy_step=self.step,
            reason=failure_reason,
            step_specific_info={"invitees": invitees_label},
        )

    def _escalation_step_notify_if_time(self, alert_group: "AlertGroup", _reason: str) -> StepExecutionResultData:
        eta = None

        if self.from_time is None or self.to_time is None:
            log_record = AlertGroupLogRecord(
                type=AlertGroupLogRecord.TYPE_ESCALATION_FAILED,
                alert_group=alert_group,
                escalation_policy=self.escalation_policy,
                escalation_error_code=AlertGroupLogRecord.ERROR_ESCALATION_NOTIFY_IF_TIME_IS_NOT_CONFIGURED,
                escalation_policy_step=self.step,
            )
        else:
            eta = eta_for_escalation_step_notify_if_time(self.from_time, self.to_time)
            log_record = AlertGroupLogRecord(
                type=AlertGroupLogRecord.TYPE_ESCALATION_TRIGGERED,
                author=None,
                alert_group=alert_group,
                reason="notify if time",
                eta=eta,
                escalation_policy=self.escalation_policy,
                escalation_policy_step=self.step,
            )

        log_record.save()
        return self._get_result_tuple(eta=eta)

    def _escalation_step_notify_if_num_alerts_in_time_window(
        self, alert_group: "AlertGroup", _reason: str
    ) -> typing.Optional[StepExecutionResultData]:
        # check if current escalation policy is configured properly, otherwise create an error log
        if self.num_alerts_in_window is None or self.num_minutes_in_window is None:
            AlertGroupLogRecord.objects.create(
                type=AlertGroupLogRecord.TYPE_ESCALATION_FAILED,
                alert_group=alert_group,
                escalation_policy=self.escalation_policy,
                escalation_error_code=AlertGroupLogRecord.ERROR_ESCALATION_NOTIFY_IF_NUM_ALERTS_IN_WINDOW_STEP_IS_NOT_CONFIGURED,
                escalation_policy_step=self.step,
            )
            return None

        # create a log record only when escalation is paused for the first time
        if not self.pause_escalation:
            AlertGroupLogRecord.objects.create(
                type=AlertGroupLogRecord.TYPE_ESCALATION_TRIGGERED,
                author=None,
                alert_group=alert_group,
                reason="continue escalation if >X alerts per Y minutes",
                escalation_policy=self.escalation_policy,
                escalation_policy_step=self.step,
            )

        last_alert = alert_group.alerts.last()

        time_delta = datetime.timedelta(minutes=self.num_minutes_in_window)
        num_alerts_in_window = alert_group.alerts.filter(created_at__gte=last_alert.created_at - time_delta).count()

        # pause escalation if there are not enough alerts in time window
        if num_alerts_in_window <= self.num_alerts_in_window:
            self.pause_escalation = True
            return self._get_result_tuple(pause_escalation=True)
        return None

    def _escalation_step_trigger_custom_webhook(self, alert_group: "AlertGroup", _reason: str) -> None:
        tasks = []
        webhook = self.custom_webhook
        failure_reason = None
        if webhook is not None:
            if webhook.is_webhook_enabled:
                custom_webhook_task = custom_webhook_result.signature(
                    (webhook.pk, alert_group.pk),
                    {
                        "escalation_policy_pk": self.id,
                    },
                    immutable=True,
                )
                tasks.append(custom_webhook_task)
            else:
                failure_reason = AlertGroupLogRecord.ERROR_ESCALATION_TRIGGER_WEBHOOK_IS_DISABLED
        else:
            failure_reason = AlertGroupLogRecord.ERROR_ESCALATION_TRIGGER_WEBHOOK_STEP_IS_NOT_CONFIGURED

        if failure_reason:
            log_record = AlertGroupLogRecord(
                type=AlertGroupLogRecord.TYPE_ESCALATION_FAILED,
                alert_group=alert_group,
                escalation_policy=self.escalation_policy,
                escalation_error_code=failure_reason,
                escalation_policy_step=self.step,
            )
            log_record.save()

        self._execute_tasks(tasks)

    def _escalation_step_repeat_escalation_n_times(
        self, alert_group: "AlertGroup", _reason: str
    ) -> typing.Optional[StepExecutionResultData]:
        if self.escalation_counter < EscalationPolicy.MAX_TIMES_REPEAT:
            log_record = AlertGroupLogRecord(
                type=AlertGroupLogRecord.TYPE_ESCALATION_TRIGGERED,
                author=None,
                alert_group=alert_group,
                reason="repeat escalation",
                escalation_policy=self.escalation_policy,
                escalation_policy_step=self.step,
            )
            log_record.save()
            self.escalation_counter += 1
            return self._get_result_tuple(start_from_beginning=True)
        return None

    def _escalation_step_resolve(self, alert_group: "AlertGroup", _reason: str) -> StepExecutionResultData:
        tasks = []
        log_record = AlertGroupLogRecord(
            type=AlertGroupLogRecord.TYPE_ESCALATION_TRIGGERED,
            author=None,
            alert_group=alert_group,
            reason="final resolve",
            escalation_policy=self.escalation_policy,
            escalation_policy_step=self.step,
        )
        log_record.save()
        resolve_by_last_step = resolve_by_last_step_task.signature((alert_group.pk,), immutable=True)
        tasks.append(resolve_by_last_step)
        self._execute_tasks(tasks)
        return self._get_result_tuple(stop_escalation=True)

    def _escalation_step_not_configured(self, alert_group: "AlertGroup", _reason: str) -> None:
        log_record = AlertGroupLogRecord(
            type=AlertGroupLogRecord.TYPE_ESCALATION_FAILED,
            alert_group=alert_group,
            escalation_policy=self.escalation_policy,
            escalation_error_code=AlertGroupLogRecord.ERROR_ESCALATION_UNSPECIFIED_STEP,
        )
        log_record.save()

    def _execute_tasks(self, tasks: typing.List[Task]) -> None:
        def _apply_tasks() -> None:
            for task in tasks:
                task.apply_async()

        transaction.on_commit(_apply_tasks)

    def _get_calendar_invitees(self, alert_group: "AlertGroup") -> list["User"]:
        if self.invitees == EscalationPolicy.INVITEES_CURRENT_ONCALL_MEMBERS:
            users = self._get_current_oncall_members(alert_group)
        elif self.invitees == EscalationPolicy.INVITEES_CURRENT_ESCALATION_CHAIN_MEMBERS:
            users = self._get_current_escalation_chain_members(alert_group)
        elif self.invitees == EscalationPolicy.INVITEES_CURRENT_TEAM_MEMBERS:
            users = self._get_current_team_members(alert_group)
        else:
            users = []

        deduped_users = {user.pk: user for user in users if getattr(user, "email", None)}
        return sorted(deduped_users.values(), key=lambda user: (user.username or "", user.pk))

    def _get_current_oncall_members(self, alert_group: "AlertGroup") -> list["User"]:
        users: list["User"] = []
        for policy_snapshot in self._get_escalation_policy_snapshots(alert_group):
            if policy_snapshot.notify_schedule is None:
                continue
            users.extend(list_users_to_notify_from_ical(policy_snapshot.notify_schedule) or [])
        return users

    def _get_current_escalation_chain_members(self, alert_group: "AlertGroup") -> list["User"]:
        users = list(self._get_current_oncall_members(alert_group))
        for policy_snapshot in self._get_escalation_policy_snapshots(alert_group):
            users.extend(list(policy_snapshot.notify_to_users_queue or []))
            if policy_snapshot.notify_to_team_members is not None:
                users.extend(policy_snapshot.notify_to_team_members.users.all())
        return users

    def _get_current_team_members(self, alert_group: "AlertGroup") -> list["User"]:
        escalation_chain = self._get_live_escalation_chain(alert_group)
        if escalation_chain is None or escalation_chain.team is None:
            return []
        return list(escalation_chain.team.users.all())

    def _get_escalation_policy_snapshots(self, alert_group: "AlertGroup") -> list["EscalationPolicySnapshot"]:
        escalation_snapshot = alert_group.escalation_snapshot
        if escalation_snapshot is None:
            return []
        return escalation_snapshot.escalation_policies_snapshots

    def _get_live_escalation_chain(self, alert_group: "AlertGroup") -> typing.Optional["EscalationChain"]:
        escalation_policy = self.escalation_policy
        if escalation_policy is not None:
            return escalation_policy.escalation_chain

        from apps.alerts.models import EscalationChain

        escalation_snapshot = alert_group.escalation_snapshot
        if escalation_snapshot is None:
            return None
        return EscalationChain.objects.filter(pk=escalation_snapshot.escalation_chain_snapshot.id).first()

    def _get_first_alert(self, alert_group: "AlertGroup") -> typing.Optional["Alert"]:
        return alert_group.alerts.filter(is_the_first_alert_in_group=True).first() or alert_group.alerts.first()

    def _render_calendar_event_details(self, alert_group: "AlertGroup") -> tuple[str, str | None]:
        from apps.alerts.models.alert import Alert

        channel = alert_group.channel
        first_alert = self._get_first_alert(alert_group)
        raw_request_data = first_alert.raw_request_data if first_alert is not None else {}
        labels = gather_alert_labels(channel, raw_request_data)

        title_template = channel.get_template_attribute("google_calendar", "title") or channel.get_default_template_attribute(
            "google_calendar", "title"
        )
        description_template = channel.get_template_attribute(
            "google_calendar", "description"
        ) or channel.get_default_template_attribute("google_calendar", "description")

        summary = alert_group.web_title_cache or DEFAULT_BACKUP_TITLE
        if title_template is not None:
            summary = (
                Alert._apply_jinja_template_to_alert_payload_and_labels(
                    title_template,
                    "google_calendar_title_template",
                    channel,
                    raw_request_data,
                    labels,
                    use_error_msg_as_fallback=True,
                )
                or summary
            )

        description = None
        if description_template is not None:
            description = Alert._apply_jinja_template_to_alert_payload_and_labels(
                description_template,
                "google_calendar_description_template",
                channel,
                raw_request_data,
                labels,
                use_error_msg_as_fallback=True,
            )

        return summary, description

    def _get_invitees_display(self) -> str:
        return dict(EscalationPolicy.INVITEES_CHOICES).get(self.invitees, "invitees")

    def _get_result_tuple(
        self, eta=None, stop_escalation=False, start_from_beginning=False, pause_escalation=False
    ) -> StepExecutionResultData:
        # use default delay for eta, if eta was not counted by step and escalation was not paused
        if not pause_escalation:
            eta = eta or timezone.now() + datetime.timedelta(seconds=NEXT_ESCALATION_DELAY)
        return self.StepExecutionResultData(eta, stop_escalation, start_from_beginning, pause_escalation)
