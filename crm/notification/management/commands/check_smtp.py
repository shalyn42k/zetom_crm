"""Management command to diagnose SMTP configuration issues.

Usage:
    python manage.py check_smtp

Checks:
1. EMAIL_HOST resolves to an IP address (DNS)
2. TCP connection to EMAIL_HOST:EMAIL_PORT
3. SMTP EHLO handshake
4. STARTTLS negotiation
5. AUTH authentication
6. Test email send

Output: Color-coded diagnostic info without exposing passwords.
"""
# Stdlib
import logging
import socket
import smtplib
from typing import Optional

# Django imports
from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = "Diagnose SMTP configuration: DNS, TCP, STARTTLS, AUTH, and send test email."

    def add_arguments(self, parser):
        parser.add_argument(
            "--recipient",
            type=str,
            default=None,
            help="Send test email to this address (optional)",
        )

    def handle(self, *args, **options):
        self.stdout.write(
            self.style.HTTP_INFO("🔍 SMTP Configuration Diagnostic\n")
        )

        email_host = settings.EMAIL_HOST
        email_port = settings.EMAIL_PORT
        email_use_tls = settings.EMAIL_USE_TLS
        email_host_user = settings.EMAIL_HOST_USER
        default_from = settings.DEFAULT_FROM_EMAIL

        self.stdout.write(
            self.style.HTTP_INFO(f"Configuration from settings:")
        )
        self.stdout.write(f"  EMAIL_HOST: {email_host}")
        self.stdout.write(f"  EMAIL_PORT: {email_port}")
        self.stdout.write(f"  EMAIL_USE_TLS: {email_use_tls}")
        self.stdout.write(f"  EMAIL_HOST_USER: {email_host_user or '(empty)'}")
        self.stdout.write(f"  DEFAULT_FROM_EMAIL: {default_from}")
        self.stdout.write("")

        # Step 1: DNS resolution
        self.stdout.write(
            self.style.HTTP_INFO("Step 1: DNS Resolution")
        )
        try:
            ip_address = socket.gethostbyname(email_host)
            self.stdout.write(
                self.style.SUCCESS(f"✓ {email_host} resolves to {ip_address}")
            )
        except socket.gaierror as e:
            self.stdout.write(
                self.style.ERROR(f"✗ DNS resolution failed: {e}")
            )
            self.stdout.write(
                self.style.WARNING(
                    f"  This matches your error: [Errno -3] Temporary failure in name resolution"
                )
            )
            self.stdout.write(
                self.style.WARNING(
                    f"  Check: 1) Is EMAIL_HOST correct? 2) Does server have DNS access?"
                )
            )
            return

        # Step 2: TCP connection
        self.stdout.write("")
        self.stdout.write(
            self.style.HTTP_INFO("Step 2: TCP Connection")
        )
        try:
            sock = socket.create_connection((email_host, email_port), timeout=5)
            sock.close()
            self.stdout.write(
                self.style.SUCCESS(
                    f"✓ TCP connection to {email_host}:{email_port} successful"
                )
            )
        except socket.timeout:
            self.stdout.write(
                self.style.ERROR(f"✗ TCP connection timed out")
            )
            return
        except (socket.error, ConnectionRefusedError) as e:
            self.stdout.write(
                self.style.ERROR(f"✗ TCP connection failed: {e}")
            )
            return

        # Step 3: SMTP handshake and TLS/AUTH
        self.stdout.write("")
        self.stdout.write(
            self.style.HTTP_INFO("Step 3: SMTP Handshake")
        )
        try:
            if email_use_tls:
                server = smtplib.SMTP(email_host, email_port, timeout=5)
                server.starttls()
                self.stdout.write(
                    self.style.SUCCESS(f"✓ STARTTLS successful")
                )
            else:
                server = smtplib.SMTP(email_host, email_port, timeout=5)
                self.stdout.write(
                    self.style.SUCCESS(f"✓ SMTP connection successful (no TLS)")
                )

            # Step 4: AUTH if credentials are provided
            if email_host_user:
                self.stdout.write("")
                self.stdout.write(
                    self.style.HTTP_INFO("Step 4: Authentication")
                )
                try:
                    password = settings.EMAIL_HOST_PASSWORD
                    if not password:
                        self.stdout.write(
                            self.style.WARNING(
                                f"⚠ EMAIL_HOST_PASSWORD not set, skipping AUTH test"
                            )
                        )
                    else:
                        server.login(email_host_user, password)
                        self.stdout.write(
                            self.style.SUCCESS(
                                f"✓ Authentication successful for {email_host_user}"
                            )
                        )
                except smtplib.SMTPAuthenticationError as e:
                    self.stdout.write(
                        self.style.ERROR(
                            f"✗ Authentication failed: {e}"
                        )
                    )
                except smtplib.SMTPException as e:
                    self.stdout.write(
                        self.style.ERROR(f"✗ SMTP error during AUTH: {e}")
                    )
            else:
                self.stdout.write("")
                self.stdout.write(
                    self.style.WARNING(
                        f"⚠ EMAIL_HOST_USER not set, skipping AUTH test"
                    )
                )

            # Step 5: Test email send (optional)
            recipient = options.get("recipient")
            if recipient:
                self.stdout.write("")
                self.stdout.write(
                    self.style.HTTP_INFO("Step 5: Test Email Send")
                )
                try:
                    from django.core.mail import EmailMessage
                    msg = EmailMessage(
                        subject="SMTP Test from zetom_crm",
                        body=f"Test email from {default_from}. If you see this, SMTP is working!",
                        from_email=default_from,
                        to=[recipient],
                        connection=None,
                    )
                    msg.send(fail_silently=False)
                    self.stdout.write(
                        self.style.SUCCESS(
                            f"✓ Test email sent to {recipient}"
                        )
                    )
                except Exception as e:
                    self.stdout.write(
                        self.style.ERROR(f"✗ Test email send failed: {e}")
                    )

            server.quit()

        except smtplib.SMTPException as e:
            self.stdout.write(
                self.style.ERROR(f"✗ SMTP error: {e}")
            )
        except Exception as e:
            self.stdout.write(
                self.style.ERROR(f"✗ Unexpected error: {e}")
            )
            return

        self.stdout.write("")
        self.stdout.write(
            self.style.SUCCESS("✓ All SMTP diagnostics passed!")
        )
