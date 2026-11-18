Plan (do not edit yet) how to add roles and permissions to the conversations API using the matrix in @core/rbac.py.

I want: a single `HasAction` permission class that reads `required_actions` on the view; deny when an action is missing from the map;
a test that lists every route and fails if a route has no required action (use `core.rbac.matrix_gaps`);
tests for each role on each action (viewer, member, admin, owner); no role checks scattered inside views.
List the files you will change and the risks you see. Wait for my approval.
