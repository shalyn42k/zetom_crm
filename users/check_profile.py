import os

import django

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "dcrm.settings")
django.setup()

from django.contrib.auth.models import User

from users.models import Role, UserProfile

user = User.objects.get(username="TEST142")
print(f"User: {user}, is_staff: {user.is_staff}")

try:
    profile = user.profile
    print(f"✓ Profile Found: {profile}, Role: {profile.role}")
except UserProfile.DoesNotExist:
    print("❌ NO PROFILE FOUND - Creating...")
    specialist_role = Role.objects.get(code="specialist")
    profile = UserProfile.objects.create(user=user, role=specialist_role)
    print(f"✓ Profile Created: {profile}")
