"""Original read-only WindowManager focus parser; no runtime entry."""
import re

def focus_metadata(raw):
    focus_lines = [line.strip() for line in raw.splitlines() if 'mCurrentFocus=' in line]
    app_lines = [line.strip() for line in raw.splitlines() if 'mFocusedApp=' in line]
    focus = re.findall(r'mCurrentFocus=Window\{([0-9a-fA-F]+)\s+u(\d+)\s+([A-Za-z0-9_.]+)/([A-Za-z0-9_.$]+)', raw)
    app = re.findall(r'mFocusedApp=ActivityRecord\{[^\n]*?\bu(\d+)\s+([A-Za-z0-9_.]+)/([A-Za-z0-9_.$]+)\s+t(\d+)\b', raw)
    if len(set(focus_lines)) != 1 or len(set(app_lines)) != 1 or len(set(focus)) != 1 or len(set(app)) != 1:
        return {'verified': False, 'reason': 'FOCUS_OR_ACTIVITY_NOT_UNIQUE',
                'focus_lines': focus_lines + app_lines}
    token, user, package, activity = focus[0]
    app_user, app_package, app_activity, task = app[0]
    return {'verified': user == app_user == '0' and package == app_package,
            'package': package, 'activity': activity, 'window_token': token.lower(),
            'focused_activity': app_activity, 'task': int(task), 'user': int(user)}
