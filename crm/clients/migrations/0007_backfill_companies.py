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


class Migration(migrations.Migration):
    dependencies = [
        ("clients", "0006_company_companypersonlink"),
        ("zetom", "0013_historicalrequestmain_company_requestmain_company"),
    ]
    # claude — реверс сделан no-op: старый backwards() необратимо удалял
    # все Company/CompanyPersonLink и обнулял RequestMain.company.
    operations = [migrations.RunPython(forwards, migrations.RunPython.noop)]
