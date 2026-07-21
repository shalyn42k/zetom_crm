# claude
from django.db import migrations

from crm.clients.backfill import backfill_companies


def forwards(apps, schema_editor):
    backfill_companies(
        apps.get_model("clients", "Client"),
        apps.get_model("clients", "Company"),
        apps.get_model("clients", "CompanyPersonLink"),
        apps.get_model("zetom", "RequestMain"),
        apps.get_model("zetom", "RequestClientLink"),
    )


def backwards(apps, schema_editor):
    # Реверс: снять company с заявок, удалить связи и компании.
    apps.get_model("zetom", "RequestMain").objects.update(company=None)
    apps.get_model("clients", "CompanyPersonLink").objects.all().delete()
    apps.get_model("clients", "Company").objects.all().delete()


class Migration(migrations.Migration):
    dependencies = [
        ("clients", "0006_company_companypersonlink"),
        ("zetom", "0013_historicalrequestmain_company_requestmain_company"),
    ]
    operations = [migrations.RunPython(forwards, backwards)]
