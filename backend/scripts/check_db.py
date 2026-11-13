
import sqlite3

conn = sqlite3.connect("lm.db")

tables = conn.execute(
    "SELECT name FROM sqlite_master WHERE type = 'table'"
).fetchall()
print("Tables:", [t[0] for t in tables])

print("Users:")
for row in conn.execute("SELECT id, email, role FROM users"):
    print("  ", row)

print("Rules:")
for row in conn.execute("SELECT rule_id, severity FROM rules"):
    print("  ", row)

conn.close()