from django.db import migrations
from crm.zetom.models import DepartmentsVariants


def migrate_department(apps, schema_editor):
    Department = apps.get_model("zetom", "Department")
    for code, name in DepartmentsVariants.choices:
        Department.objects.create(code=code, name=name)


def unmigrate_department(apps, schema_editor):
    Department = apps.get_model("zetom", "Department")
    Department.objects.filter(code__in=DepartmentsVariants.values).delete()


class Migration(migrations.Migration):

    dependencies = [
        ("zetom", "0023_department"),
    ]

    operations = [
        migrations.RunPython(migrate_department, unmigrate_department),
    ]
