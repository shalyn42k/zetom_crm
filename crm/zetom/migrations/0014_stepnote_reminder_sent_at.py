from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("zetom", "0013_historicalrequestmain_company_requestmain_company"),
    ]

    operations = [
        migrations.AddField(
            model_name="stepnote",
            name="reminder_sent_at",
            field=models.DateTimeField(blank=True, null=True, verbose_name="Reminder sent at"),
        ),
    ]
