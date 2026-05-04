import sqlite3
conn = sqlite3.connect('hotnews.db')
c = conn.cursor()
c.execute("SELECT title, source_name FROM articles WHERE source_name LIKE '%36%' OR title LIKE '%36%' LIMIT 5")
for row in c.fetchall():
    print('Title bytes:', row[0].encode('utf-8'))
    print('Title:', row[0])
    print('Source:', row[1])
    print()
conn.close()
