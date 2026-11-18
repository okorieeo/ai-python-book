from django.conf import settings
from django.db.models import Sum
from django.utils import timezone
from rest_framework.exceptions import APIException

from chat.models import UsageRecord

class QuotaExceeded(APIException):
    status_code = 402
    default_code = "quota_exceeded"
    default_detail = "Your daily AI usage limit is used up."

def tokens_used_today(user):
    totals = UsageRecord.objects.filter(
        user=user, created_at__date=timezone.localdate()
    ).aggregate(i=Sum("input_tokens"), o=Sum("output_tokens"))
    return (totals["i"] or 0) + (totals["o"] or 0)

def check_quota(user):
    if tokens_used_today(user) >= settings.CHAT_DAILY_TOKEN_LIMIT:
        raise QuotaExceeded()
