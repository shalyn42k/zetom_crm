ROLE_PERMISSIONS = {
    "admin": [
        "change_status",
        "assign_record",
        "view_logs",
        "delete_record",
    ],
    "department_head": [
        "change_status",
        "assign_record",
        "delete_record",
    ],
    "specialist": [
        "change_status",
        "delete_record",
    ],
    "auditor": [
        "view_logs",
    ],
    "all_seeing": ["*"],
}
