ROLES_CONFIG = {
    "admin": {
        "label": "Администратор",
        "modules": ["requests"],
        "can_edit_models": ["requestnull", "requestmain", "oferta"],
        "readonly_models": [],
        "hidden_models": [],
    },
    "department_head": {
        "label": "Руководитель отдела",
        "modules": ["requests"],
        "can_edit_models": ["requestmain"],
        "readonly_models": ["requestnull", "oferta"],
        "hidden_models": [],
    },
    "specialist": {
        "label": "Специалист",
        "modules": ["requests"],
        "can_edit_models": [],
        "readonly_models": ["requestnull", "requestmain", "oferta"],
        "hidden_models": [],
    },
    "auditor": {
        "label": "Аудитор",
        "modules": ["requests"],
        "can_edit_models": [],
        "readonly_models": ["requestnull", "requestmain", "oferta"],
        "hidden_models": [],
    },
    "custom_role": {
        "label": "Всевидящий",
        "modules": ["*"],
        "can_edit_models": ["*"],
        "readonly_models": [],
        "hidden_models": [],
    },
}
