python api_check.py
 expected output
PASS  missing token returns 401
PASS  creating a conversation returns 201
PASS  blank message returns 422 + details
PASS  sending a message returns 201
PASS  history holds question + answer
PASS  a retry returns the same message
PASS  the retry is flagged as a replay
PASS  no duplicate was created (4 messages)
PASS  pages of 8 cover 24 messages: [8, 8, 8]
PASS  no duplicates, newest first
PASS  bad limit returns 400
PASS  plan limit returns 429 + Retry-After
PASS  error code is plan_limit_reached
PASS  rename returns 200
PASS  delete returns 204
PASS  deleted conversation returns 404

All rules hold.
