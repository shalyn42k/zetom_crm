from django.core.mail import send_mail
from django.conf import settings
from ..models import Record

def send_request(subject, message, receipt_list):
    send_mail(subject,message,settings.EMAIL_HOST_USER,receipt_list)