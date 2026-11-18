from core import rbac
from config.urls import collect_routes          # a small helper that walks the router: {"GET /conversations": "conversation.read", ...}

def test_every_route_has_a_known_required_action():
    assert rbac.matrix_gaps(collect_routes()) == []

def test_every_action_is_used_by_some_route():
    assert rbac.unused_actions(collect_routes()) == []      # an action nobody checks is a permission nobody enforces

def test_roles_form_a_ladder():
    assert rbac.privilege_ladder_ok()
