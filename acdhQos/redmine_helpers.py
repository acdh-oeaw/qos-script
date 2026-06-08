def format_container_description(container_info: dict) -> str:
    """Format container info into a readable string for logs or plain text."""
    mapping = [
        ("Name", "name"),
        ("Endpoint", "endpoint"),
        ("Tech Stack", "techStack"),
        ("Server", "server"),
        ("Project", "project"),
        ("Type", "type"),
    ]

    lines = []
    for label, key in mapping:
        value = container_info.get(key)
        if value is not None and str(value).strip() != "":
            lines.append(f"{label}: {value}")

    users_raw = container_info.get("users", "")
    if users_raw:
        user_lines = [u.strip() for u in users_raw.strip().split("\n") if u.strip()]
        if user_lines:
            lines.append("Users:")
            lines.extend(user_lines)

    return "\n".join(lines)


def format_container_description_textile(container_info: dict) -> str:
    """Render container info as a Redmine-friendly textile list."""
    mapping = [
        ("Name", "name"),
        ("Endpoint", "endpoint"),
        ("Tech Stack", "techStack"),
        ("Server", "server"),
        ("Project", "project"),
        ("Type", "type"),
    ]

    lines = []
    for label, key in mapping:
        value = container_info.get(key)
        if value is not None and str(value).strip() != "":
            lines.append(f"* *{label}:* {value}")

    users_raw = container_info.get("users", "")
    if users_raw:
        user_list = [u.strip() for u in users_raw.strip().split("\n") if u.strip()]
        if user_list:
            lines.append("* *Users:*")
            for user in user_list:
                lines.append(f"** {user}")

    return "\n".join(lines)
