from django.conf import settings
from django.core.mail import send_mail

from ..models import RequestNull


def send_notification_to_staff(request_object: RequestNull):
    subject = f"New notification from Zetom CRM, request №{request_object.id} from {request_object.company_name}"

    message = (
        f"Check new request №{request_object.id}\n"
        f"Company: {request_object.company_name}\n"
        f"For more detailed information please check it in CRM.\n"
    )

    send_mail(
        subject,
        message,
        settings.EMAIL_HOST_USER,  # здесь переменная от которой отправляется
        ["tymirapps@gmail.com"],  # это стафф кому отправляется
        fail_silently=False,
    )

def send_notification_approve_null(request_object: RequestNull):
    subject = f"Request - {request_object.id} was fully approved, you can now start your work!"

    message = (
        f"Check your messages at Zetom CRM to view new request for work!\n"
    )

    send_mail(
        subject,
        message,
        settings.EMAIL_HOST_USER,
        ["tymirapps@gmail.com"],  # это стафф кому отправляется
        fail_silently=False,
    )
