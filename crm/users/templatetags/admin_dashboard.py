from django import template

from crm.notification.utils import unread_count
from crm.users.utils import user_has_perm


register = template.Library()


@register.simple_tag
def has_crm_perm(user, perm_code):
    return user_has_perm(user, perm_code)


@register.simple_tag
def unread_inapp_count(user):
    return unread_count(user)
