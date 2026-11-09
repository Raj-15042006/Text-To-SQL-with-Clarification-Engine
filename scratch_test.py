import sqlite3

conn = sqlite3.connect(':memory:')
conn.execute('CREATE TABLE sample_players (player_name TEXT, runs INTEGER, strike_rate REAL);')
cur = conn.cursor()
cur.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%';")
tables = [row[0] for row in cur.fetchall()]
print("Tables:", tables)

for tbl in tables:
    cur.execute(f'PRAGMA table_info("{tbl}");')
    cols = cur.fetchall()
    print(f"Cols for {tbl}:", cols)
