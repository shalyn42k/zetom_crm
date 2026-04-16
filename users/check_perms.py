import os

import django

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "dcrm.settings")
django.setup()

from django.contrib.auth.models import User

from users.models import Role, UserProfile
from users.permissions import ROLES_CONFIG

user = User.objects.get(username="TEST142")
profile = user.profile

print(f"User: {user}")
print(f"Profile: {profile}")
print(f"Role Code: {profile.role.code if profile.role else None}")
print(f"Role: {profile.role}")

cfg = profile.get_role_config()
print(f"\n=== ROLE CONFIG ===")
print(f"Label: {cfg.get('label')}")
print(f"Modules: {cfg.get('modules')}")
print(f"Can Edit: {cfg.get('can_edit_models')}")
print(f"Readonly: {cfg.get('readonly_models')}")
print(f"Hidden: {cfg.get('hidden_models')}")

print(f"\n=== PERMISSION CHECKS ===")
print(f"can_see_module('requests'): {profile.can_see_module('requests')}")
print(f"can_see_module('zetom'): {profile.can_see_module('zetom')}")
print(f"can_edit_model('requestnull'): {profile.can_edit_model('requestnull')}")
print(f"is_model_readonly('requestnull'): {profile.is_model_readonly('requestnull')}")
print(f"is_model_hidden('requestnull'): {profile.is_model_hidden('requestnull')}")
