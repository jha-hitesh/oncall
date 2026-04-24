import functools
import html
import json
import os
import random
import re
import string
import time
from contextlib import contextmanager
from functools import reduce

import factory
import markdown2
from bs4 import BeautifulSoup
from celery.utils.log import get_task_logger
from celery.utils.time import get_exponential_backoff_interval
from django.core.cache import cache
from django.core.exceptions import ValidationError
from django.core.validators import URLValidator
from django.utils.html import urlize
from jinja2 import TemplateAssertionError, TemplateSyntaxError, meta
from jinja2.exceptions import SecurityError, UndefinedError
from jinja2.sandbox import SandboxedEnvironment

logger = get_task_logger(__name__)

PHONE_CALL_TEMPLATE_FORMAT_FIELDS = {
    "acknowledge_button",
    "resolve_button",
    "silence_button",
    "repeat_button",
    "silence_in_minutes",
}
ALERT_GROUP_PHONE_CALL_TEMPLATE_FORMAT_FIELDS = {"integration_name", "title", "alert_count"}
PHONE_CALL_BUTTON_CONFIG_KEYS = (
    "acknowledge_button",
    "resolve_button",
    "silence_button",
    "repeat_button",
)
PHONE_CALL_INTEGER_CONFIG_KEYS = ("wait_time_for_user_action", "silence_in_minutes")
PHONE_CALL_MESSAGE_CONFIG_KEYS = ("acknowledge_message", "resolve_message", "silence_message")
PHONE_CALL_INSTRUCTIONS_TEMPLATE_SAMPLE_CONTEXT = {
    "acknowledge_button": "1",
    "resolve_button": "2",
    "silence_button": "3",
    "repeat_button": "0",
    "silence_in_minutes": 30,
}
NOTIFICATION_BUNDLE_PHONECALL_TEMPLATE_SAMPLE_CONTEXT = {
    "total_alert_groups": 2,
    "total_channels": 2,
    "channel_names": ["Grafana", "PagerDuty"],
    "alert_group_names": ["CPU high", "Memory high"],
    "alert_group_codes": ["#1", "#2"],
    "stack_slug": "test-stack",
}
# NOTE: bundled SMS and bundled phone-call templates share the same rendering context.
NOTIFICATION_BUNDLE_SMS_TEMPLATE_SAMPLE_CONTEXT = dict(NOTIFICATION_BUNDLE_PHONECALL_TEMPLATE_SAMPLE_CONTEXT)
SETTINGS_JINJA_TEMPLATE_ENV = SandboxedEnvironment()


# Faker that always returns unique values
class UniqueFaker(factory.Faker):
    def __init__(self, provider, **kwargs):
        if provider == "pyint":
            # https://faker.readthedocs.io/en/master/providers/faker.providers.python.html#faker.providers.python.Provider.pyint
            # https://raintank-corp.slack.com/archives/C06K1MQ07GS/p1728589562495709?thread_ts=1728586969.283779&cid=C06K1MQ07GS
            kwargs["max_value"] = 9_999_999

        super().__init__(provider, **kwargs)

    @classmethod
    def _get_faker(cls, locale=None):
        return super()._get_faker(locale).unique


# Context manager for tasks that are intended to retry
# It will rerun the whole task if exception(s) exc has happened
class OkToRetry:
    def __init__(self, task, exc, num_retries=None, compute_countdown=None, allow_jitter=True):
        self.task = task
        self.num_retries = num_retries
        self.compute_countdown = compute_countdown
        self.allow_jitter = allow_jitter

        if not isinstance(exc, (list, tuple)):
            exc = [exc]
        self.exc = exc

    def __enter__(self):
        pass

    def __exit__(self, exc_type, exc_val, exc_tb):
        if exc_type is not None and any(issubclass(exc_type, exc) for exc in self.exc):
            if self.num_retries is None or self.task.request.retries + 1 <= self.num_retries:
                countdown = self.get_countdown(exc_val)

                logger.warning(
                    f"Retrying task gracefully in {countdown} seconds due to {exc_type.__name__}. "
                    f"args: {self.task.request.args}, kwargs: {self.task.request.kwargs}"
                )
                self.rerun_task(countdown)

                return True

    def get_countdown(self, exc_val):
        if self.compute_countdown is not None:
            countdown = self.compute_countdown(exc_val)
            if self.allow_jitter is True:
                countdown = countdown + random.uniform(0, 2)
        else:
            countdown = get_exponential_backoff_interval(
                factor=self.task.retry_backoff, retries=self.task.request.retries, maximum=600, full_jitter=True
            )
        return countdown

    def rerun_task(self, countdown):
        self.task.apply_async(
            self.task.request.args,
            kwargs=self.task.request.kwargs,
            retries=self.task.request.retries + 1,
            countdown=countdown,
        )


LOCK_EXPIRE = 60 * 10  # Lock expires in 10 minutes


# Context manager for tasks that are intended to run once at a time
# (ie. no parallel instances of the same task running)
# based on https://docs.celeryq.dev/en/stable/tutorials/task-cookbook.html#ensuring-a-task-is-only-executed-one-at-a-time
@contextmanager
def task_lock(lock_id, oid):
    timeout_at = time.monotonic() + LOCK_EXPIRE - 3
    # cache.add returns False if the key already exists
    status = cache.add(lock_id, oid, LOCK_EXPIRE)
    try:
        yield status
    finally:
        # cache delete may be slow, but we have to use it to take
        # advantage of using add() for atomic locking
        if time.monotonic() < timeout_at and status:
            # don't release the lock if we exceeded the timeout
            # to lessen the chance of releasing an expired lock
            # owned by someone else
            # also don't release the lock if we didn't acquire it
            cache.delete(lock_id)


# lru cache version with addition of timeout.
# Timeout added to not to occupy memory with too old values
def timed_lru_cache(timeout: int, maxsize: int = 128, typed: bool = False):
    def wrapper_cache(func):
        func = functools.lru_cache(maxsize=maxsize, typed=typed)(func)
        func.delta = timeout * 10**9
        func.expiration = time.monotonic_ns() + func.delta

        @functools.wraps(func)
        def wrapped_func(*args, **kwargs):
            if time.monotonic_ns() >= func.expiration:
                func.cache_clear()
                func.expiration = time.monotonic_ns() + func.delta
            return func(*args, **kwargs)

        wrapped_func.cache_info = func.cache_info
        wrapped_func.cache_clear = func.cache_clear
        return wrapped_func

    return wrapper_cache


def getenv_boolean(variable_name: str, default: bool) -> bool:
    value = os.environ.get(variable_name)
    if value is None:
        return default

    return value.lower() in ("true", "1")


def getenv_integer(variable_name: str, default: int | None) -> int | None:
    value = os.environ.get(variable_name)
    if value is None:
        return default
    try:
        return int(value)
    except ValueError:
        return default


def getenv_float(variable_name: str, default: float) -> float:
    value = os.environ.get(variable_name)
    if value is None:
        return default
    try:
        return float(value)
    except ValueError:
        return default


def getenv_list(variable_name: str, default: list) -> list:
    value = os.environ.get(variable_name)
    if value is None:
        return default

    return json.loads(value)


def get_notification_channels_to_bundle() -> list[str]:
    allowed_values = {"SMS", "PHONE_CALL"}
    channels = [
        channel.strip().upper()
        for channel in os.environ.get("FEATURE_NOTIFICATION_CHANNELS_TO_BUNDLE", "SMS").split(",")
    ]
    channels = [channel for channel in channels if channel]

    invalid_channels = sorted(set(channels) - allowed_values)
    if invalid_channels:
        raise ValueError(
            "Invalid FEATURE_NOTIFICATION_CHANNELS_TO_BUNDLE env variable values: "
            f"{', '.join(invalid_channels)}. Allowed values are: SMS, PHONE_CALL"
        )

    return channels


def _get_invalid_template_variable_error(invalid_fields: set[str], allowed_fields: set[str]) -> str:
    invalid_variables = ", ".join(sorted(invalid_fields))
    allowed_variables = ", ".join(sorted(allowed_fields))
    suffix = "s" if len(invalid_fields) > 1 else ""
    return f"Invalid template variable{suffix}: {invalid_variables}. Allowed variables are: {allowed_variables}"


def validate_format_template(template: str, *, allowed_fields: set[str], sample_context: dict[str, object]) -> str | None:
    if not isinstance(template, str):
        return "Must be a string"

    formatter = string.Formatter()

    try:
        invalid_fields = set()
        for _, field_name, _, _ in formatter.parse(template):
            if field_name is None:
                continue
            if field_name == "":
                return "Positional placeholders are not supported"

            root_field_name = field_name.split(".", 1)[0].split("[", 1)[0]
            if root_field_name not in allowed_fields:
                invalid_fields.add(root_field_name)

        if invalid_fields:
            return _get_invalid_template_variable_error(invalid_fields, allowed_fields)

        template.format(**sample_context)
    except (KeyError, IndexError, ValueError) as err:
        return f"Invalid format template: {err}"

    return None


def validate_jinja_template(
    template: str,
    *,
    allowed_variables: set[str],
    sample_context: dict[str, object],
) -> str | None:
    if not isinstance(template, str):
        return "Must be a string"

    try:
        parsed_template = SETTINGS_JINJA_TEMPLATE_ENV.parse(template)
        available_variables = allowed_variables | set(SETTINGS_JINJA_TEMPLATE_ENV.globals)
        invalid_variables = meta.find_undeclared_variables(parsed_template) - available_variables
        if invalid_variables:
            return _get_invalid_template_variable_error(invalid_variables, allowed_variables)

        SETTINGS_JINJA_TEMPLATE_ENV.from_string(template).render(**sample_context)
    except SecurityError as err:
        return f"Invalid Jinja template: {err}"
    except (TemplateAssertionError, TemplateSyntaxError) as err:
        return f"Invalid Jinja template: {err}"
    except (TypeError, KeyError, ValueError, UndefinedError) as err:
        return f"Invalid Jinja template: {err}"

    return None


def _get_valid_integer_value(value) -> int | None:
    if value is None:
        return None
    if isinstance(value, int) and not isinstance(value, bool):
        return value
    if isinstance(value, str) and value.isdigit():
        return int(value)
    return None


def parse_phone_call_instructions_config(config: str | dict | None) -> tuple[dict | None, str | None]:
    if isinstance(config, str):
        try:
            config = json.loads(config)
        except json.JSONDecodeError as err:
            return None, f"Invalid JSON: {err.msg}"

    if not isinstance(config, dict):
        return None, "Must be a JSON object"

    for key in PHONE_CALL_BUTTON_CONFIG_KEYS:
        if key not in config or config[key] is None:
            continue
        if not is_valid_phone_call_button(config[key]):
            return None, f"Invalid value for {key}: expected a digit, '*' or '#'"

    for key in PHONE_CALL_INTEGER_CONFIG_KEYS:
        if key not in config or config[key] is None:
            continue
        if _get_valid_integer_value(config[key]) is None:
            return None, f"Invalid value for {key}: expected an integer"

    for key in PHONE_CALL_MESSAGE_CONFIG_KEYS:
        if key not in config or config[key] is None:
            continue
        if not isinstance(config[key], str):
            return None, f"Invalid value for {key}: expected a string"

    configured_buttons: dict[str, list[str]] = {}
    for key in PHONE_CALL_BUTTON_CONFIG_KEYS:
        value = config.get(key)
        if value is None:
            continue
        configured_buttons.setdefault(str(value), []).append(key)

    duplicate_buttons = {button: keys for button, keys in configured_buttons.items() if len(keys) > 1}
    if duplicate_buttons:
        duplicate_button, duplicate_keys = sorted(duplicate_buttons.items())[0]
        joined_keys = ", ".join(duplicate_keys)
        return None, f"Invalid value for button configuration: {duplicate_button} is used by {joined_keys}"

    return config, None


def validate_phone_call_instructions_config(config: str | dict | None) -> str | None:
    _, error = parse_phone_call_instructions_config(config)
    return error


def validate_phone_call_instructions_template(template: str) -> str | None:
    return validate_format_template(
        template,
        allowed_fields=PHONE_CALL_TEMPLATE_FORMAT_FIELDS,
        sample_context=PHONE_CALL_INSTRUCTIONS_TEMPLATE_SAMPLE_CONTEXT,
    )


def validate_alert_group_phone_call_template(template: str) -> str | None:
    return validate_format_template(
        template,
        allowed_fields=ALERT_GROUP_PHONE_CALL_TEMPLATE_FORMAT_FIELDS,
        sample_context={"integration_name": "Grafana", "title": "CPU high", "alert_count": 3},
    )


def validate_notification_bundle_phonecall_template(template: str) -> str | None:
    return validate_jinja_template(
        template,
        allowed_variables=set(NOTIFICATION_BUNDLE_PHONECALL_TEMPLATE_SAMPLE_CONTEXT),
        sample_context=NOTIFICATION_BUNDLE_PHONECALL_TEMPLATE_SAMPLE_CONTEXT,
    )


def validate_notification_bundle_sms_template(template: str) -> str | None:
    return validate_jinja_template(
        template,
        allowed_variables=set(NOTIFICATION_BUNDLE_SMS_TEMPLATE_SAMPLE_CONTEXT),
        sample_context=NOTIFICATION_BUNDLE_SMS_TEMPLATE_SAMPLE_CONTEXT,
    )


def is_valid_phone_call_button(value) -> bool:
    if value is None:
        return False
    value = str(value)
    return value.isdigit() or value in {"*", "#"}


def get_default_phone_call_instructions_template(config: dict) -> str:
    action_phrases = []
    acknowledge_button = config.get("acknowledge_button")
    if is_valid_phone_call_button(acknowledge_button):
        action_phrases.append(f"Press {{acknowledge_button}} to acknowledge")

    resolve_button = config.get("resolve_button")
    if is_valid_phone_call_button(resolve_button):
        action_phrases.append("{resolve_button} to resolve")

    silence_button = config.get("silence_button")
    if is_valid_phone_call_button(silence_button):
        action_phrases.append("{silence_button} to silence for {silence_in_minutes} minutes")

    repeat_button = config.get("repeat_button")
    if is_valid_phone_call_button(repeat_button):
        action_phrases.append("{repeat_button} to repeat this message")

    if not action_phrases:
        return "No phone call actions are configured"
    if len(action_phrases) == 1:
        return action_phrases[0]
    if len(action_phrases) == 2:
        return " and ".join(action_phrases)
    return ", ".join(action_phrases[:-1]) + f" and {action_phrases[-1]}"


def batch_queryset(qs, batch_size=1000):
    qs_count = qs.count()
    for start in range(0, qs_count, batch_size):
        end = min(start + batch_size, qs_count)
        yield qs[start:end]


def is_regex_valid(regex) -> bool:
    try:
        re.compile(regex)
        return True
    except re.error:
        return False


def isoformat_with_tz_suffix(value):
    """
    Default python datetime.isoformat() return tz offset like +00:00 instead of military tz suffix (e.g.Z for UTC)".
    On the other hand DRF returns datetime with military tz suffix.
    This utility function exists to return consistent datetime string in api.
    It is copied from DRF DateTimeField.to_representation
    """
    value = value.isoformat()
    if value.endswith("+00:00"):
        value = value[:-6] + "Z"
    return value


def is_string_with_visible_characters(string):
    return type(string) is str and not string.isspace() and not string == ""


def str_or_backup(string, backup):
    return string if is_string_with_visible_characters(string) else backup


def clean_html(text):
    text = "".join(BeautifulSoup(text, features="html.parser").find_all(string=True))
    return text


def validate_url(url: str):
    validate_url = URLValidator()
    try:
        validate_url(url)
    except ValidationError:
        return None
    return url


def convert_slack_md_to_html(text):
    text = re.sub(r"\*", "**", text)
    return convert_md_to_html(text)


def convert_md_to_html(text):
    # Markdown expects two or more spaces at the end of a line to indicate a line break.
    # Adding two spaces to any line break to support templates that were built without this in mind.
    # https://daringfireball.net/projects/markdown/syntax#p
    text = text.replace("\n", "  \n")

    extras = {
        "cuddled-lists",
        "code-friendly",  # Disable _ and __ for em and strong.
        # This gives us <pre> and <code> tags for ```-fenced blocks
        "fenced-code-blocks",
        "pyshell",
        "nl2br",
        "target-blank-links",
        "nofollow",
        "pymdownx.emoji",
        "pymdownx.magiclink",
        "tables",
    }
    try:
        text = markdown2.markdown(
            text,
            extras=extras,
        )
    except AssertionError:
        # markdown2 raises an AssertionError when using the "cuddled-lists" extra and passing strings with "- - " in it.
        # If the initial attempt fails, try again without the "cuddled-lists" extra.
        text = markdown2.markdown(
            text,
            extras=extras - {"cuddled-lists"},
        )

    return text.strip()


def clean_markup(text):
    html = markdown2.markdown(text, extras=["cuddled-lists", "fenced-code-blocks", "pyshell"]).strip()
    cleaned = clean_html(html)
    stroke_matches = re.findall(r"~\w+~", cleaned)
    for stroke_match in stroke_matches:
        cleaned_match = stroke_match.strip("~")
        cleaned = cleaned.replace(stroke_match, cleaned_match)
    return cleaned


def escape_html(text):
    return html.escape(text, quote=False) if text else text


def urlize_with_respect_to_a(html):
    """
    Wrap links into <a> tag if not already
    """
    soup = BeautifulSoup(html, features="html.parser")
    textNodes = soup.find_all(string=True)
    for textNode in textNodes:
        if textNode.parent and getattr(textNode.parent, "name", None) == "a":
            continue
        urlizedText = urlize(textNode)
        textNode.replaceWith(BeautifulSoup(urlizedText, features="html.parser"))

    return str(soup)


url_re = re.compile(
    r"""(?i)\b((?:https?:(?:/{1,3}|[a-z0-9%])|[a-z0-9.\-]+[.](?:com|net|org|edu|gov|mil|aero|asia|biz|cat|coop|info|int|jobs|mobi|museum|name|post|pro|tel|travel|xxx|ac|ad|ae|af|ag|ai|al|am|an|ao|aq|ar|as|at|au|aw|ax|az|ba|bb|bd|be|bf|bg|bh|bi|bj|bm|bn|bo|br|bs|bt|bv|bw|by|bz|ca|cc|cd|cf|cg|ch|ci|ck|cl|cm|cn|co|cr|cs|cu|cv|cx|cy|cz|dd|de|dj|dk|dm|do|dz|ec|ee|eg|eh|er|es|et|eu|fi|fj|fk|fm|fo|fr|ga|gb|gd|ge|gf|gg|gh|gi|gl|gm|gn|gp|gq|gr|gs|gt|gu|gw|gy|hk|hm|hn|hr|ht|hu|id|ie|il|im|in|io|iq|ir|is|it|je|jm|jo|jp|ke|kg|kh|ki|km|kn|kp|kr|kw|ky|kz|la|lb|lc|li|lk|lr|ls|lt|lu|lv|ly|ma|mc|md|me|mg|mh|mk|ml|mm|mn|mo|mp|mq|mr|ms|mt|mu|mv|mw|mx|my|mz|na|nc|ne|nf|ng|ni|nl|no|np|nr|nu|nz|om|pa|pe|pf|pg|ph|pk|pl|pm|pn|pr|ps|pt|pw|py|qa|re|ro|rs|ru|rw|sa|sb|sc|sd|se|sg|sh|si|sj|Ja|sk|sl|sm|sn|so|sr|ss|st|su|sv|sx|sy|sz|tc|td|tf|tg|th|tj|tk|tl|tm|tn|to|tp|tr|tt|tv|tw|tz|ua|ug|uk|us|uy|uz|va|vc|ve|vg|vi|vn|vu|wf|ws|ye|yt|yu|za|zm|zw)/)(?:[^\s()<>{}\[\]]+|\([^\s()]*?\([^\s()]+\)[^\s()]*?\)|\([^\s]+?\))+(?:\([^\s()]*?\([^\s()]+\)[^\s()]*?\)|\([^\s]+?\)|[^\s`!()\[\]{};:'".,<>?«»“”‘’])|(?:(?<!@)[a-z0-9]+(?:[.\-][a-z0-9]+)*[.](?:com|net|org|edu|gov|mil|aero|asia|biz|cat|coop|info|int|jobs|mobi|museum|name|post|pro|tel|travel|xxx|ac|ad|ae|af|ag|ai|al|am|an|ao|aq|ar|as|at|au|aw|ax|az|ba|bb|bd|be|bf|bg|bh|bi|bj|bm|bn|bo|br|bs|bt|bv|bw|by|bz|ca|cc|cd|cf|cg|ch|ci|ck|cl|cm|cn|co|cr|cs|cu|cv|cx|cy|cz|dd|de|dj|dk|dm|do|dz|ec|ee|eg|eh|er|es|et|eu|fi|fj|fk|fm|fo|fr|ga|gb|gd|ge|gf|gg|gh|gi|gl|gm|gn|gp|gq|gr|gs|gt|gu|gw|gy|hk|hm|hn|hr|ht|hu|id|ie|il|im|in|io|iq|ir|is|it|je|jm|jo|jp|ke|kg|kh|ki|km|kn|kp|kr|kw|ky|kz|la|lb|lc|li|lk|lr|ls|lt|lu|lv|ly|ma|mc|md|me|mg|mh|mk|ml|mm|mn|mo|mp|mq|mr|ms|mt|mu|mv|mw|mx|my|mz|na|nc|ne|nf|ng|ni|nl|no|np|nr|nu|nz|om|pa|pe|pf|pg|ph|pk|pl|pm|pn|pr|ps|pt|pw|py|qa|re|ro|rs|ru|rw|sa|sb|sc|sd|se|sg|sh|si|sj|Ja|sk|sl|sm|sn|so|sr|ss|st|su|sv|sx|sy|sz|tc|td|tf|tg|th|tj|tk|tl|tm|tn|to|tp|tr|tt|tv|tw|tz|ua|ug|uk|us|uy|uz|va|vc|ve|vg|vi|vn|vu|wf|ws|ye|yt|yu|za|zm|zw)\b/?(?!@)))""",  # noqa: E501
    re.IGNORECASE,
)


def trim_if_needed(text, default=150):
    if len(text) > default:
        text = text[:default]
        text += "..."
    return text


class NoDefaultProvided(object):
    pass


def getattrd(obj, name, default=NoDefaultProvided):
    """
    Same as getattr(), but allows dot notation lookup
    Discussed in:
    http://stackoverflow.com/questions/11975781
    """

    try:
        return reduce(getattr, name.split("."), obj)
    except AttributeError as e:
        if default != NoDefaultProvided:
            return default
        raise e
