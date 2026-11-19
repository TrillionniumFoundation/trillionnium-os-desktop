"""Pure original semantic selector and native-click ACK assessments."""

FIELDS = {'id': 'resource-id', 'text': 'text', 'desc': 'content-desc', 'class': 'class',
          'focused': 'focused', 'editable': 'editable'}

NODE_KEYS = tuple(FIELDS.values()) + ('package', 'hint', 'bounds_array', 'enabled', 'visible', 'clickable', 'password')

def require(value, reason):
    if not value:
        raise RuntimeError(reason)

def candidates(nodes, selector, package):
    require(isinstance(selector, dict) and selector and not set(selector) - set(FIELDS), 'EXACT_SELECTOR_REQUIRED')
    require(any(k in selector for k in ('id', 'text', 'desc')), 'SEMANTIC_IDENTITY_REQUIRED')
    for key, value in selector.items():
        require(type(value) is bool if key in ('focused', 'editable') else
                isinstance(value, str) and 0 < len(value.encode()) <= 4096, 'SELECTOR_VALUE_INVALID')
    return [n for n in nodes if n.get('package') == package and n.get('visible') is True
            and n.get('enabled') is True and all(n.get(FIELDS[k]) == v for k, v in selector.items())]

def node_identity(node):
    return {key: node.get(key) for key in NODE_KEYS}

def post_capture_only(response, acknowledgements, op):
    """The exact installed helper's successful native-click/post-capture split."""
    if op != 'click' or len(acknowledgements) != 1:
        return False
    ack = acknowledgements[0]
    return (ack.get('ok') is True and ack.get('performed') == 'click'
            and ack.get('outcome_unknown') is not True
            and ack.get('accessibility_mode_restoration_verified') is True
            and isinstance(ack.get('target'), dict) and isinstance(ack.get('actual_target'), dict)
            and response.get('ok') is True and response.get('performed') == 'click'
            and response.get('outcome_unknown') is True
            and response.get('post_action_observation_available') is False)

def clickable_container(nodes, label, package):
    bounds = label.get('bounds_array')
    require(isinstance(bounds, list) and len(bounds) == 4
            and all(type(x) is int for x in bounds), 'DEVICE_LABEL_BOUNDS_INVALID')
    containers = []
    for node in nodes:
        box = node.get('bounds_array')
        if (node.get('package') == package and node.get('window_id') == label.get('window_id')
                and node.get('visible') is True and node.get('enabled') is True
                and node.get('clickable') is True and isinstance(box, list) and len(box) == 4
                and all(type(x) is int for x in box)
                and box[0] <= bounds[0] < bounds[2] <= box[2]
                and box[1] <= bounds[1] < bounds[3] <= box[3]):
            containers.append(node_identity(node))
    require(len(containers) == 1, 'DEVICE_LABEL_CLICKABLE_CONTAINER_NOT_UNIQUE')
    return containers[0]
