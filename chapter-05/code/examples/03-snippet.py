import sqlite3

conn = sqlite3.connect(":memory:")
conn.execute("CREATE TABLE users (email TEXT, name TEXT)")
conn.execute("INSERT INTO users VALUES ('ada@example.com', 'Ada'), ('bo@example.com', 'Bo')")

user_input = "nobody' OR '1'='1"      # what an attacker types into a login box

# DANGEROUS: building SQL with string formatting
bad_query = f"SELECT * FROM users WHERE email = '{user_input}'"
print(conn.execute(bad_query).fetchall())            # returns EVERY user!

# SAFE: parameterized query - the driver treats input purely as data
safe = conn.execute("SELECT * FROM users WHERE email = ?", (user_input,)).fetchall()
print(safe)                                           # []
